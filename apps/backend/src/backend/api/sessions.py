"""설명 학습 API. 자료 업로드/개념 추출과 독립적으로 기존 개념을 사용한다."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, StringConstraints, ValidationError

from backend.api.deps import CurrentUser, DbSession, require_profile
from backend.errors import AppError
from backend.llm import LLMProvider
from backend.llm.provider import openai_provider
from backend.services import sessions

router = APIRouter(tags=["learning"])
ProfileUser = Annotated[CurrentUser, Depends(require_profile)]


@dataclass(frozen=True)
class Evaluator:
    provider: LLMProvider
    model_id: str
    lease_seconds: float = sessions.DEFAULT_LEASE_SECONDS


async def get_evaluator() -> AsyncIterator[Evaluator]:
    try:
        async with openai_provider() as provider:
            settings = provider.settings
            lease = sessions.evaluation_lease_seconds()
            yield Evaluator(provider, settings.llm_assessment_model, lease)
    except ValidationError:
        raise AppError(502, "llm_failed", "assessment provider is not configured") from None


class AnswerInput(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


@router.get("/projects/{project_id}/concepts")
async def list_concepts(
    project_id: uuid.UUID, current: ProfileUser, db: DbSession
) -> dict[str, Any]:
    return await sessions.list_concepts(db, current.user.id, project_id)


@router.post("/concepts/{concept_id}/sessions", status_code=status.HTTP_201_CREATED)
async def start_session(
    concept_id: uuid.UUID, current: ProfileUser, db: DbSession
) -> dict[str, Any]:
    return await sessions.start_session(db, current.user.id, concept_id)


@router.get("/sessions/{session_id}")
async def get_session(session_id: uuid.UUID, current: ProfileUser, db: DbSession) -> dict[str, Any]:
    return await sessions.session_view(db, current.user.id, session_id)


@router.post("/sessions/cleanup", status_code=status.HTTP_204_NO_CONTENT)
async def cleanup_on_home(current: ProfileUser, db: DbSession) -> Response:
    await sessions.cleanup_on_home(db, current.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/{session_id}/answers")
async def submit_answer(
    session_id: uuid.UUID,
    body: AnswerInput,
    current: ProfileUser,
    db: DbSession,
    evaluator: Annotated[Evaluator, Depends(get_evaluator)],
) -> dict[str, Any]:
    return await sessions.submit_answer(
        db,
        current.user.id,
        session_id,
        body.text,
        evaluator.provider,
        model_id=evaluator.model_id,
        lease_seconds=evaluator.lease_seconds,
    )


@router.post("/sessions/{session_id}/abort")
async def abort_session(
    session_id: uuid.UUID, current: ProfileUser, db: DbSession
) -> dict[str, Any]:
    return await sessions.abort_session(db, current.user.id, session_id)


@router.get("/sessions/{session_id}/result")
async def get_result(session_id: uuid.UUID, current: ProfileUser, db: DbSession) -> dict[str, Any]:
    return await sessions.session_view(db, current.user.id, session_id, result=True)
