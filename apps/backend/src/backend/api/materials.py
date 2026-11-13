"""학습자료 API (architecture 8.1).

architecture 7.1은 Signed URL로 GCS에 직접 올리고 Cloud Tasks로 워커를 부른다.
이 구현은 로컬 개발·시연용으로 백엔드가 파일을 직접 받아 보관하고,
응답 뒤 같은 프로세스에서 분석한다.
목록·재시도의 응답 모양은 7.1 흐름과 같게 둔다.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile, status
from pydantic import BaseModel

from backend.api.deps import CurrentUser, DbSession, require_profile
from backend.db.models import Material
from backend.domain.enums import FailureCode, FileType, MaterialStatus
from backend.errors import AppError
from backend.ingest import MAX_FILE_BYTES, IngestError, read_material
from backend.services import materials
from backend.services.analysis import analyze_material

router = APIRouter(tags=["materials"])

ProfileUser = Annotated[CurrentUser, Depends(require_profile)]


class MaterialResponse(BaseModel):
    id: uuid.UUID
    title: str
    file_type: FileType
    size_bytes: int
    page_count: int | None
    status: MaterialStatus
    failure_code: FailureCode | None
    chunk_count: int  # 임베딩까지 저장된 조각 수 (키가 없으면 0)
    created_at: datetime


class MaterialListResponse(BaseModel):
    items: list[MaterialResponse]


class PageResponse(BaseModel):
    number: int
    text: str


class PagesResponse(BaseModel):
    pages: list[PageResponse]


def _response(material: Material, chunk_count: int = 0) -> MaterialResponse:
    return MaterialResponse(
        id=material.id,
        title=material.title,
        file_type=FileType(material.file_type),
        size_bytes=material.size_bytes,
        page_count=material.page_count,
        status=MaterialStatus(material.status),
        failure_code=FailureCode(material.failure_code) if material.failure_code else None,
        chunk_count=chunk_count,
        created_at=material.created_at,
    )


def _schedule(request: Request, tasks: BackgroundTasks, material: Material) -> None:
    state = request.app.state
    tasks.add_task(
        analyze_material,
        state.session_factory,
        state.storage,
        material.id,
        material.analysis_attempt,
        llm_settings=state.llm_settings,
        ocr_factory=state.ocr_factory,
    )


@router.post("/projects/{project_id}/materials", status_code=status.HTTP_202_ACCEPTED)
async def upload_material(
    project_id: uuid.UUID,
    file: UploadFile,
    request: Request,
    tasks: BackgroundTasks,
    current: ProfileUser,
    db: DbSession,
) -> MaterialResponse:
    # 상한보다 1바이트 더 읽어 초과 여부만 확인한다 (큰 파일 전체를 메모리에 올리지 않는다).
    data = await file.read(MAX_FILE_BYTES + 1)
    material = await materials.create_material(
        db, request.app.state.storage, current.user, project_id, file.filename or "", data
    )
    _schedule(request, tasks, material)
    return _response(material)


@router.get("/projects/{project_id}/materials")
async def list_materials(
    project_id: uuid.UUID, current: ProfileUser, db: DbSession
) -> MaterialListResponse:
    summaries = await materials.list_materials(db, current.user.id, project_id)
    return MaterialListResponse(items=[_response(s.material, s.chunk_count) for s in summaries])


@router.post("/materials/{material_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_material(
    material_id: uuid.UUID,
    request: Request,
    tasks: BackgroundTasks,
    current: ProfileUser,
    db: DbSession,
) -> MaterialResponse:
    material = await materials.retry_material(db, current.user.id, material_id)
    _schedule(request, tasks, material)
    return _response(material)


@router.get("/materials/{material_id}/pages")
async def material_pages(
    material_id: uuid.UUID, request: Request, current: ProfileUser, db: DbSession
) -> PagesResponse:
    """시연용: 분석이 끝난 자료에서 뽑힌 쪽별 글자를 보여준다 (분석 때 저장한 글자)."""
    material = await materials.owned_material(db, current.user.id, material_id)
    if material.status != MaterialStatus.READY:
        raise AppError(409, "invalid_state", f"material is {material.status}")
    if material.page_texts is not None:
        return PagesResponse(
            pages=[
                PageResponse(number=number, text=text)
                for number, text in enumerate(material.page_texts, start=1)
            ]
        )
    # 글자를 저장하기 전에 분석한 자료: 원본을 다시 읽는다
    state = request.app.state
    try:
        data = await asyncio.to_thread(state.storage.load, material.gcs_path)
    except FileNotFoundError as exc:
        raise AppError(409, "original_missing", "original file is no longer in storage") from exc
    try:
        pages = await read_material(data, material.file_type, state.ocr_factory(None))
    except IngestError as exc:
        raise AppError(409, "invalid_state", exc.code.value) from exc
    return PagesResponse(pages=[PageResponse(number=p.number, text=p.text) for p in pages])
