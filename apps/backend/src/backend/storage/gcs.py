"""GCS 보관소 구현: 실제 버킷(Signed URL), 로컬 에뮬레이터, 설정 없음 (architecture 7.1, 11.2)."""

import threading
from typing import Any
from urllib.parse import quote

from backend.errors import AppError
from backend.services.cloud import signed_url
from backend.storage import EMULATOR_BUCKET, UploadTarget


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


def _delete(bucket: Any, key: str) -> None:
    from google.api_core.exceptions import NotFound

    try:
        bucket.blob(key).delete()
    except NotFound:
        pass  # 원본 삭제 후 DB 커밋이 실패한 경우에도 다시 시도할 수 있다.


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

    def delete(self, key: str) -> None:
        _delete(self._get_bucket(), key)


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

    def delete(self, key: str) -> None:
        _delete(self._get_bucket(), key)


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

    def delete(self, key: str) -> None:
        raise self._fail()
