"""학습자료 업로드(Signed URL)·목록·재시도 (PRD FR-1.1~1.3, FR-1.7, FR-1.8, architecture 7.1).

모든 조회는 `user_id`로 범위를 좁힌다. 다른 사용자의 자료는 없는 것처럼 404로 처리한다 (5.2-7).
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePath

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Chunk, Concept, ConceptElement, Material, Project, User
from backend.domain.enums import FailureCode, FileType, MaterialStatus
from backend.errors import AppError
from backend.ingest import MAX_FILE_BYTES
from backend.storage import CONTENT_TYPES, MaterialStorage, UploadTarget, material_key

# 확장자 → materials.file_type. 실제 형식은 분석할 때 파일 앞 바이트로 다시 확인한다.
EXTENSIONS = {
    "pdf": FileType.PDF,
    "pptx": FileType.PPTX,
    "png": FileType.PNG,
    "jpg": FileType.JPG,
    "jpeg": FileType.JPG,
    "txt": FileType.TXT,
    "docx": FileType.DOCX,
    "hwp": FileType.HWP,
    "hwpx": FileType.HWPX,
    "heic": FileType.HEIC,
    "heif": FileType.HEIC,
}
TITLE_MAX_LENGTH = 200


@dataclass(frozen=True)
class MaterialSummary:
    material: Material
    chunk_count: int
    concept_count: int = 0
    element_count: int = 0


async def _owned_project(db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    if project is None:
        raise AppError(404, "not_found", "project not found")
    return project


async def owned_material(
    db: AsyncSession, user_id: uuid.UUID, material_id: uuid.UUID, *, lock: bool = False
) -> Material:
    statement = (
        select(Material)
        .join(Project, Project.id == Material.project_id)
        .where(Material.id == material_id, Project.user_id == user_id)
    )
    if lock:
        statement = statement.with_for_update(of=Material)
    material = await db.scalar(statement)
    if material is None:
        raise AppError(404, "not_found", "material not found")
    return material


def _file_type(filename: str) -> tuple[FileType, str]:
    ext = PurePath(filename).suffix.lower().lstrip(".")
    if ext not in EXTENSIONS:
        raise AppError(400, "unsupported_format", f"extension {ext!r} is not supported")
    return EXTENSIONS[ext], ext


def _title(filename: str) -> str:
    title = PurePath(filename).name.strip() or "이름 없는 자료"
    return title[:TITLE_MAX_LENGTH]


async def request_upload(
    db: AsyncSession,
    storage: MaterialStorage,
    user: User,
    project_id: uuid.UUID,
    filename: str,
    size: int,
) -> tuple[Material, UploadTarget]:
    """사전 검증(형식·용량·동의) 후 `pending_upload` 자료와 업로드 주소를 만든다 (7.1 ①)."""
    project = await _owned_project(db, user.id, project_id)
    if user.ai_consent_at is None:  # FR-1.8: 첫 업로드 전 외부 AI 전송 동의
        raise AppError(403, "consent_required", "AI processing consent is required")
    file_type, ext = _file_type(filename)
    if size > MAX_FILE_BYTES:
        raise AppError(413, "file_too_large", f"{size} bytes")
    if size <= 0:
        raise AppError(400, "empty_file", "file is empty")

    material_id = uuid.uuid4()
    key = material_key(user.id, project.id, material_id, ext)
    target = await asyncio.to_thread(
        storage.upload_target, key, CONTENT_TYPES[file_type], MAX_FILE_BYTES
    )
    material = Material(
        id=material_id,
        project_id=project.id,
        title=_title(filename),
        file_type=file_type.value,
        gcs_path=key,
        size_bytes=size,
        status=MaterialStatus.PENDING_UPLOAD.value,
        analysis_attempt=1,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)
    return material, target


async def complete_upload(
    db: AsyncSession, storage: MaterialStorage, user_id: uuid.UUID, material_id: uuid.UUID
) -> tuple[Material, bool]:
    """올라온 원본을 확인하고 `queued`로 바꾼다 (7.1 ③). 두 번째 값: 작업을 등록해야 하는지.

    같은 요청이 다시 와도 작업을 두 번 등록하지 않는다. GCS가 크기 범위를 강제하지만
    (에뮬레이터는 강제하지 않음) 실제 크기를 한 번 더 확인한다.
    """
    material = await owned_material(db, user_id, material_id, lock=True)
    if material.status != MaterialStatus.PENDING_UPLOAD:
        return material, False
    size = await asyncio.to_thread(storage.size, material.gcs_path)
    if size is None:
        raise AppError(409, "upload_missing", "the file has not been uploaded yet")
    material.size_bytes = size
    if size > MAX_FILE_BYTES:
        material.status = MaterialStatus.FAILED.value
        material.failure_code = FailureCode.FILE_TOO_LARGE.value
        enqueue = False
    else:
        material.status = MaterialStatus.QUEUED.value
        enqueue = True
    await db.commit()
    await db.refresh(material)
    return material, enqueue


async def mark_failed(db: AsyncSession, material: Material, code: FailureCode) -> None:
    material.status = MaterialStatus.FAILED.value
    material.failure_code = code.value
    await db.commit()
    await db.refresh(material)


# 분석이 진행 중인 상태 (멈춤 판정 대상)
_IN_PROGRESS = (
    MaterialStatus.QUEUED.value,
    MaterialStatus.EXTRACTING.value,
    MaterialStatus.GENERATING_CONCEPTS.value,
)


async def _fail_stalled(db: AsyncSession, project_id: uuid.UUID, deadline_minutes: int) -> None:
    """진행 상태로 데드라인을 넘긴 자료는 실패로 바꿔 재시도 버튼이 보이게 한다 (7.1 멈춘 작업)."""
    limit = func.now() - timedelta(minutes=deadline_minutes)
    result = await db.execute(
        update(Material)
        .where(
            Material.project_id == project_id,
            Material.status.in_(_IN_PROGRESS),
            Material.updated_at < limit,
        )
        .values(status=MaterialStatus.FAILED.value, failure_code=FailureCode.INTERNAL_ERROR.value)
    )
    if result.rowcount:  # pyright: ignore[reportAttributeAccessIssue]
        await db.commit()


async def list_materials(
    db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, deadline_minutes: int = 30
) -> list[MaterialSummary]:
    await _owned_project(db, user_id, project_id)
    await _fail_stalled(db, project_id, deadline_minutes)
    materials = (
        await db.scalars(
            select(Material)
            .where(Material.project_id == project_id)
            .order_by(Material.created_at.desc())
        )
    ).all()
    rows = await db.execute(
        select(Chunk.material_id, func.count())
        .where(Chunk.material_id.in_([m.id for m in materials]))
        .group_by(Chunk.material_id)
    )
    counts: dict[uuid.UUID, int] = {mid: n for mid, n in rows}
    concept_rows = await db.execute(
        select(
            Concept.material_id, func.count(Concept.id.distinct()), func.count(ConceptElement.id)
        )
        .outerjoin(ConceptElement, ConceptElement.concept_id == Concept.id)
        .where(Concept.material_id.in_([m.id for m in materials]))
        .group_by(Concept.material_id)
    )
    grading = {
        mid: (concept_count, element_count) for mid, concept_count, element_count in concept_rows
    }
    return [MaterialSummary(m, counts.get(m.id, 0), *grading.get(m.id, (0, 0))) for m in materials]


async def retry_material(db: AsyncSession, user_id: uuid.UUID, material_id: uuid.UUID) -> Material:
    """`failed`일 때만 보관된 원본으로 다시 분석한다 (architecture 7.1 재시도 버튼)."""
    material = await owned_material(db, user_id, material_id, lock=True)
    if material.status != MaterialStatus.FAILED:
        raise AppError(409, "invalid_state", f"material is {material.status}")
    material.status = MaterialStatus.QUEUED.value
    material.failure_code = None
    material.analysis_attempt += 1
    await db.commit()
    await db.refresh(material)
    return material
