"""원본 자료 보관소 (architecture 7.1, 11.2).

- 운영·개발용 버킷: 비공개 Cloud Storage 버킷(`GCS_BUCKET`).
  브라우저는 V4 Signed URL로 직접 PUT한다.
- 로컬 에뮬레이터: 버킷 설정이 없을 때 compose의 `gcs` 서비스(fake-gcs-server)를 쓴다.
  서명은 검사하지 않으므로 업로드 주소만 에뮬레이터 형식으로 준다.
  읽기·크기 확인은 같은 코드로 한다.
- 둘 다 없으면 업로드를 "저장소 설정 없음"(503 `storage_unavailable`)으로 막는다.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from backend.config import Settings
from backend.domain.enums import FileType

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


def make_storage(settings: Settings) -> MaterialStorage:
    """`GCS_BUCKET`이 있으면 실제 버킷, 없으면 로컬 에뮬레이터, 둘 다 없으면 설정 없음."""
    from backend.storage.gcs import EmulatorStorage, GcsStorage, UnconfiguredStorage

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
