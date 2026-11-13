"""학습자료 업로드·목록·재시도 (PRD FR-1.1~1.3, FR-1.7, FR-1.8, architecture 7.1).

모든 조회는 `user_id`로 범위를 좁힌다. 다른 사용자의 자료는 없는 것처럼 404로 처리한다 (5.2-7).
"""

import uuid
from dataclasses import dataclass
from pathlib import PurePath

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Chunk, Material, Project, User
from backend.domain.enums import FileType, MaterialStatus
from backend.errors import AppError
from backend.ingest import MAX_FILE_BYTES
from backend.services.storage import MaterialStorage, material_key

# 확장자 → materials.file_type. 실제 형식은 분석할 때 파일 앞 바이트로 다시 확인한다.
EXTENSIONS = {
    "pdf": FileType.PDF,
    "pptx": FileType.PPTX,
    "png": FileType.PNG,
    "jpg": FileType.JPG,
    "jpeg": FileType.JPG,
}
TITLE_MAX_LENGTH = 200


@dataclass(frozen=True)
class MaterialSummary:
    material: Material
    chunk_count: int


async def _owned_project(db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    if project is None:
        raise AppError(404, "not_found", "project not found")
    return project


async def owned_material(db: AsyncSession, user_id: uuid.UUID, material_id: uuid.UUID) -> Material:
    material = await db.scalar(
        select(Material)
        .join(Project, Project.id == Material.project_id)
        .where(Material.id == material_id, Project.user_id == user_id)
    )
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


async def create_material(
    db: AsyncSession,
    storage: MaterialStorage,
    user: User,
    project_id: uuid.UUID,
    filename: str,
    data: bytes,
) -> Material:
    """사전 검증(형식·용량·동의) 후 원본을 보관하고 `queued` 자료를 만든다."""
    project = await _owned_project(db, user.id, project_id)
    if user.ai_consent_at is None:  # FR-1.8: 첫 업로드 전 외부 AI 전송 동의
        raise AppError(403, "consent_required", "AI processing consent is required")
    file_type, ext = _file_type(filename)
    if len(data) > MAX_FILE_BYTES:
        raise AppError(413, "file_too_large", f"{len(data)} bytes")
    if not data:
        raise AppError(400, "empty_file", "file is empty")

    material_id = uuid.uuid4()
    key = material_key(user.id, project.id, material_id, ext)
    storage.save(key, data)
    material = Material(
        id=material_id,
        project_id=project.id,
        title=_title(filename),
        file_type=file_type.value,
        gcs_path=key,
        size_bytes=len(data),
        status=MaterialStatus.QUEUED.value,
        analysis_attempt=1,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)
    return material


async def list_materials(
    db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> list[MaterialSummary]:
    await _owned_project(db, user_id, project_id)
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
    return [MaterialSummary(m, counts.get(m.id, 0)) for m in materials]


async def retry_material(db: AsyncSession, user_id: uuid.UUID, material_id: uuid.UUID) -> Material:
    """`failed`일 때만 보관된 원본으로 다시 분석한다 (architecture 7.1 재시도 버튼)."""
    material = await owned_material(db, user_id, material_id)
    if material.status != MaterialStatus.FAILED:
        raise AppError(409, "invalid_state", f"material is {material.status}")
    material.status = MaterialStatus.QUEUED.value
    material.failure_code = None
    material.page_texts = None
    material.analysis_attempt += 1
    await db.commit()
    await db.refresh(material)
    return material
