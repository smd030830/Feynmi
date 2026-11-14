"""학습자료 API (architecture 7.1, 8.1).

업로드는 세 단계다: `upload-url`(검사 후 업로드 주소 발급) → 브라우저가 저장소에 직접 PUT
→ `upload-complete`(원본 확인 후 분석 작업 등록). 백엔드는 원본 바이트를 받지 않는다.
분석 작업은 `QUEUE_MODE`에 따라 같은 프로세스(inline) 또는 Cloud Tasks로 전달한다.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, DbSession, require_profile
from backend.db.models import Material
from backend.domain.enums import FailureCode, FileType, MaterialStatus
from backend.queue import inline
from backend.services import materials

logger = logging.getLogger(__name__)

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


class UploadUrlRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=1000)
    size: int
    # 브라우저가 알려 준 형식. 서명에는 서버가 확장자로 정한 형식을 쓴다
    # (HWP·HEIC는 브라우저가 형식을 모른다)
    content_type: str = ""


class UploadUrlResponse(BaseModel):
    material_id: uuid.UUID
    upload_url: str
    # PUT 요청에 그대로 붙여야 하는 헤더 (서명에 포함된 값)
    required_headers: dict[str, str]
    material: MaterialResponse


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


async def _schedule(
    request: Request, tasks: BackgroundTasks, material: Material, db: AsyncSession
) -> None:
    """분석 작업을 넘긴다. 큐 등록에 실패하면 자료를 실패로 돌려 재시도 버튼이 보이게 한다."""
    state = request.app.state
    if state.analysis_queue is None:  # QUEUE_MODE=inline
        inline.schedule(tasks, state, material)
        return
    try:
        await asyncio.to_thread(
            state.analysis_queue.enqueue, material.id, material.analysis_attempt
        )
    except Exception:
        logger.exception("could not enqueue analysis for material %s", material.id)
        await materials.mark_failed(db, material, FailureCode.INTERNAL_ERROR)


@router.post("/projects/{project_id}/materials/upload-url")
async def request_upload_url(
    project_id: uuid.UUID,
    body: UploadUrlRequest,
    request: Request,
    current: ProfileUser,
    db: DbSession,
) -> UploadUrlResponse:
    material, target = await materials.request_upload(
        db, request.app.state.storage, current.user, project_id, body.filename, body.size
    )
    return UploadUrlResponse(
        material_id=material.id,
        upload_url=target.url,
        required_headers=target.headers,
        material=_response(material),
    )


@router.post("/materials/{material_id}/upload-complete", status_code=status.HTTP_202_ACCEPTED)
async def complete_upload(
    material_id: uuid.UUID,
    request: Request,
    tasks: BackgroundTasks,
    current: ProfileUser,
    db: DbSession,
) -> MaterialResponse:
    material, enqueue = await materials.complete_upload(
        db, request.app.state.storage, current.user.id, material_id
    )
    if enqueue:
        await _schedule(request, tasks, material, db)
    return _response(material)


@router.get("/projects/{project_id}/materials")
async def list_materials(
    project_id: uuid.UUID, request: Request, current: ProfileUser, db: DbSession
) -> MaterialListResponse:
    deadline = request.app.state.analysis_deadline_minutes
    summaries = await materials.list_materials(db, current.user.id, project_id, deadline)
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
    await _schedule(request, tasks, material, db)
    return _response(material)
