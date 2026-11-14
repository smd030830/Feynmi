"""내부 작업 엔드포인트 (architecture 7.1, 8.1 `/internal`).

Cloud Tasks만 부른다. Firebase 로그인 대신 Cloud Tasks가 붙인 OIDC 토큰을 확인한다.
`QUEUE_MODE=inline`이면 쓰지 않으므로 없는 경로(404)로 둔다.
"""

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel

from backend.errors import AppError
from backend.services.analysis import analyze_material

router = APIRouter(prefix="/internal/tasks", tags=["internal"], include_in_schema=False)


async def require_task_token(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> None:
    verify = request.app.state.task_token_verifier
    if verify is None:  # inline 모드: 외부에서 부를 수 있는 작업 경로를 열지 않는다
        raise AppError(404, "not_found", "not found")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AppError(401, "unauthenticated", "missing task token")
    await asyncio.to_thread(verify, token)


class AnalyzeMaterialTask(BaseModel):
    material_id: uuid.UUID
    attempt: int


@router.post("/analyze-material", dependencies=[Depends(require_task_token)])
async def run_analyze_material(body: AnalyzeMaterialTask, request: Request) -> dict[str, str]:
    """분석을 끝까지 실행하고 2xx를 돌려준다.

    사용자 원인 실패(형식·쪽수·글자 없음)와 LLM 최종 실패는 자료에 `failed`로 기록되고 2xx라서
    Cloud Tasks가 다시 보내지 않는다. 다른 시도이거나 이미 끝난 작업은 그냥 무시한다 (7.1 멱등성).
    """
    state = request.app.state
    await analyze_material(
        state.session_factory,
        state.storage,
        body.material_id,
        body.attempt,
        llm_settings=state.llm_settings,
        ocr_factory=state.ocr_factory,
    )
    return {"status": "done"}
