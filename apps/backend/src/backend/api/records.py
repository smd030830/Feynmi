import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.api.deps import CurrentUser, DbSession, require_profile
from backend.services.records import RecordPage, list_records

router = APIRouter(tags=["records"])
ProfileUser = Annotated[CurrentUser, Depends(require_profile)]
Cursor = Annotated[str | None, Query(max_length=512)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("/records")
async def get_records(
    current: ProfileUser, db: DbSession, cursor: Cursor = None, limit: PageSize = 20
) -> RecordPage:
    return await list_records(db, current.user.id, cursor=cursor, limit=limit)


@router.get("/projects/{project_id}/records")
async def get_project_records(
    project_id: uuid.UUID,
    current: ProfileUser,
    db: DbSession,
    cursor: Cursor = None,
    limit: PageSize = 20,
) -> RecordPage:
    return await list_records(
        db, current.user.id, project_id=project_id, cursor=cursor, limit=limit
    )
