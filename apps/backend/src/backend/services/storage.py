"""원본 자료 보관소 (architecture 7.1, 11.2).

- 운영·개발용 버킷: 비공개 Cloud Storage 버킷(`GCS_BUCKET`).
  브라우저는 V4 Signed URL로 직접 PUT한다.
- 로컬 에뮬레이터: 버킷 설정이 없을 때 compose의 `gcs` 서비스(fake-gcs-server)를 쓴다.
  서명은 검사하지 않으므로 업로드 주소만 에뮬레이터 형식으로 준다.
  읽기·크기 확인은 같은 코드로 한다.
- 둘 다 없으면 업로드를 "저장소 설정 없음"(503 `storage_unavailable`)으로 막는다.
"""

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import quote

from backend.config import Settings
from backend.domain.enums import FileType
from backend.errors import AppError
from backend.services.cloud import signed_url

# 업로드할 때 서명에 넣는 Content-Type. 브라우저가 형식을 모르는 HWP·HEIC도 서버가 정한다
CONTENT_TYPES = {
    FileType.PDF: "application/pdf",
    FileType.PPTX: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    FileType.PNG: "image/png",
    FileType.JPG: "image/jpeg",
    FileType.TXT: "text/plain",
    FileType.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    FileType.HWP: "application/x-hwp",
    FileType.HWPX: "application/hwp+zip",
    FileType.HEIC: "image/heic",
}

# 에뮬레이터를 쓸 때의 버킷 이름 (로컬 전용)
EMULATOR_BUCKET = "feynmi-local"


@dataclass(frozen=True)
class UploadTarget:
    """브라우저가 원본을 올릴 주소와, PUT에 그대로 붙여야 하는 헤더."""

    url: str
    headers: dict[str, str] = field(default_factory=dict)


class MaterialStorage(Protocol):
    def upload_target(self, key: str, content_type: str, max_bytes: int) -> UploadTarget: ...

    def size(self, key: str) -> int | None:
        """객체 크기. 없으면 None."""
        ...

    def load(self, key: str) -> bytes: ...


def material_key(
    user_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID, ext: str
) -> str:
    """architecture 7.1 객체 경로. 모두 서버가 정한 값이라 경로 조작이 끼어들 수 없다."""
    return f"users/{user_id}/projects/{project_id}/materials/{material_id}/original.{ext}"


def _size_of(bucket: Any, key: str) -> int | None:
    blob = bucket.get_blob(key)
    return None if blob is None else int(blob.size or 0)


def _load(bucket: Any, key: str) -> bytes:
    """원본이 없으면 FileNotFoundError (보관소 종류와 상관없이 같은 예외)."""
    from google.api_core.exceptions import NotFound

    try:
        return bucket.blob(key).download_as_bytes()
    except NotFound as exc:
        raise FileNotFoundError(key) from exc


class GcsStorage:
    """비공개 버킷. Signed URL에 Content-Type과 크기 범위를 서명해 GCS가 용량을 강제한다."""

    def __init__(self, project_id: str, bucket_name: str, signer_email: str = "") -> None:
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.signer_email = signer_email
        self._bucket: Any = None
        self._lock = threading.Lock()

    def _get_bucket(self) -> Any:
        from google.cloud import storage

        with self._lock:
            if self._bucket is None:
                self._bucket = storage.Client(project=self.project_id).bucket(self.bucket_name)
            return self._bucket

    def upload_target(self, key: str, content_type: str, max_bytes: int) -> UploadTarget:
        headers = {"Content-Type": content_type, "x-goog-content-length-range": f"0,{max_bytes}"}
        url = signed_url(
            self._get_bucket().blob(key),
            self.signer_email,
            method="PUT",
            content_type=content_type,
            headers={"x-goog-content-length-range": headers["x-goog-content-length-range"]},
        )
        return UploadTarget(url, headers)

    def size(self, key: str) -> int | None:
        return _size_of(self._get_bucket(), key)

    def load(self, key: str) -> bytes:
        return _load(self._get_bucket(), key)


class EmulatorStorage:
    """로컬 GCS 에뮬레이터 (fake-gcs-server).

    백엔드는 컨테이너 주소로, 브라우저는 공개 주소로 접근한다.
    """

    def __init__(self, internal_url: str, public_url: str, bucket_name: str = EMULATOR_BUCKET):
        self.internal_url = internal_url.rstrip("/")
        self.public_url = public_url.rstrip("/")
        self.bucket_name = bucket_name
        self._bucket: Any = None
        self._lock = threading.Lock()

    def _get_bucket(self) -> Any:
        from google.api_core.exceptions import Conflict
        from google.auth.credentials import AnonymousCredentials
        from google.cloud import storage

        with self._lock:
            if self._bucket is None:
                client = storage.Client(
                    project="feynmi-local",
                    credentials=AnonymousCredentials(),  # type: ignore[no-untyped-call]
                    client_options={"api_endpoint": self.internal_url},
                )
                try:
                    client.create_bucket(self.bucket_name)
                except Conflict:
                    pass  # 이미 있음
                self._bucket = client.bucket(self.bucket_name)
            return self._bucket

    def upload_target(self, key: str, content_type: str, max_bytes: int) -> UploadTarget:
        self._get_bucket()  # 첫 업로드 전에 버킷을 만든다
        name = quote(key, safe="")
        url = f"{self.public_url}/{self.bucket_name}/{name}?uploadType=media&name={name}"
        headers = {"Content-Type": content_type, "x-goog-content-length-range": f"0,{max_bytes}"}
        return UploadTarget(url, headers)

    def size(self, key: str) -> int | None:
        return _size_of(self._get_bucket(), key)

    def load(self, key: str) -> bytes:
        return _load(self._get_bucket(), key)


class UnconfiguredStorage:
    """버킷도 에뮬레이터도 없을 때. 업로드를 분명한 오류로 막는다."""

    def _fail(self) -> AppError:
        return AppError(
            503,
            "storage_unavailable",
            "material storage is not configured: set GCS_BUCKET or run the gcs emulator",
        )

    def upload_target(self, key: str, content_type: str, max_bytes: int) -> UploadTarget:
        raise self._fail()

    def size(self, key: str) -> int | None:
        raise self._fail()

    def load(self, key: str) -> bytes:
        raise self._fail()


def make_storage(settings: Settings) -> MaterialStorage:
    """`GCS_BUCKET`이 있으면 실제 버킷, 없으면 로컬 에뮬레이터, 둘 다 없으면 설정 없음."""
    if settings.gcs_bucket.strip():
        return GcsStorage(
            settings.firebase_project_id,
            settings.gcs_bucket.strip(),
            settings.gcs_signer_service_account.strip(),
        )
    if settings.gcs_emulator_url.strip():
        public = settings.gcs_emulator_public_url.strip() or settings.gcs_emulator_url.strip()
        return EmulatorStorage(settings.gcs_emulator_url.strip(), public)
    return UnconfiguredStorage()
