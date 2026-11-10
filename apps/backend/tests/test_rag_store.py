"""실제 pgvector의 거리 정렬, 소유권/프로젝트/ready 경계, 필수 근거 병합."""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from backend.db.models import Chunk, Material, Project, User
from backend.db.session import make_session_factory
from backend.errors import AppError
from backend.rag.chunking import TextChunk
from backend.rag.store import EmbeddedChunk, save_chunks, search_chunks

pytestmark = pytest.mark.usefixtures("migrated_db")


def vector(x: float = 1, y: float = 0) -> list[float]:
    return [x, y] + [0.0] * 1534


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with make_session_factory(engine)() as session:
        yield session
        await session.rollback()


async def material(
    db: AsyncSession, uid: str, *, status: str = "ready"
) -> tuple[User, Project, Material]:
    user = User(firebase_uid=uid, email=f"{uid}@example.com", sign_in_provider="password")
    db.add(user)
    await db.flush()
    project = Project(user_id=user.id, name=uid, color="indigo")
    db.add(project)
    await db.flush()
    item = Material(
        project_id=project.id,
        title=uid,
        file_type="pdf",
        gcs_path="test.pdf",
        size_bytes=1,
        status=status,
    )
    db.add(item)
    await db.flush()
    return user, project, item


async def add(
    db: AsyncSession, user: User, item: Material, vectors: list[list[float]]
) -> list[Chunk]:
    return await save_chunks(
        db,
        user_id=user.id,
        material_id=item.id,
        chunks=[
            EmbeddedChunk(TextChunk(i, i + 1, i + 1, f"근거 {i}", 4), v)
            for i, v in enumerate(vectors)
        ],
    )


async def test_cosine_order_required_evidence_deduplication_and_metadata(db: AsyncSession) -> None:
    user, project, item = await material(db, "alice")
    rows = await add(db, user, item, [vector(1, 0), vector(1, 1), vector(0, 1)])
    found = await search_chunks(
        db,
        user_id=user.id,
        project_id=project.id,
        query_embedding=vector(),
        top_k=2,
        evidence_chunk_ids=[rows[0].id, rows[2].id, rows[2].id],
    )
    assert [c.id for c in found] == [rows[0].id, rows[1].id, rows[2].id]
    assert found[2].material_title == "alice"
    assert found[2].page_start == found[2].page_end == 3
    assert found[2].text == "근거 2"


async def test_search_all_ready_materials_but_not_other_project_or_failed(db: AsyncSession) -> None:
    user, project, first = await material(db, "alice")
    rows = await add(db, user, first, [vector(0, 1)])
    second = Material(
        project_id=project.id,
        title="second",
        file_type="pptx",
        gcs_path="s",
        size_bytes=1,
        status="ready",
    )
    failed = Material(
        project_id=project.id,
        title="failed",
        file_type="pdf",
        gcs_path="f",
        size_bytes=1,
        status="failed",
    )
    db.add_all([second, failed])
    await db.flush()
    second_rows = await add(db, user, second, [vector()])
    failed_rows = await add(db, user, failed, [vector()])
    other_user, _, other = await material(db, "bob")
    foreign_rows = await add(db, other_user, other, [vector()])
    own_other = Project(user_id=user.id, name="own-other", color="cyan")
    db.add(own_other)
    await db.flush()
    other_material = Material(
        project_id=own_other.id,
        title="other",
        file_type="pdf",
        gcs_path="o",
        size_bytes=1,
        status="ready",
    )
    db.add(other_material)
    await db.flush()
    own_other_rows = await add(db, user, other_material, [vector()])
    found = await search_chunks(
        db,
        user_id=user.id,
        project_id=project.id,
        query_embedding=vector(),
    )
    assert [c.id for c in found] == [second_rows[0].id, rows[0].id]
    for invalid in [failed_rows[0].id, foreign_rows[0].id, own_other_rows[0].id, uuid.uuid4()]:
        with pytest.raises(ValueError, match="Evidence chunks"):
            await search_chunks(
                db,
                user_id=user.id,
                project_id=project.id,
                query_embedding=vector(),
                evidence_chunk_ids=[invalid],
            )


async def test_foreign_project_and_material_are_not_found(db: AsyncSession) -> None:
    user, _, _ = await material(db, "alice")
    _, foreign_project, foreign_material = await material(db, "bob")
    with pytest.raises(AppError) as error:
        await search_chunks(
            db,
            user_id=user.id,
            project_id=foreign_project.id,
            query_embedding=vector(),
        )
    assert error.value.status_code == 404
    with pytest.raises(AppError):
        await save_chunks(db, user_id=user.id, material_id=foreign_material.id, chunks=[])


async def test_store_does_not_commit_or_overwrite_existing_chunks(db: AsyncSession) -> None:
    user, _, item = await material(db, "alice")
    rows = await add(db, user, item, [vector()])
    with pytest.raises(ValueError, match="already has chunks"):
        await add(db, user, item, [vector(0, 1)])
    assert await db.scalar(select(Chunk.id).where(Chunk.id == rows[0].id)) == rows[0].id
    await db.rollback()
    assert await db.scalar(select(Chunk.id)) is None


async def test_invalid_vectors_and_metadata_are_not_stored(db: AsyncSession) -> None:
    user, _, item = await material(db, "alice")
    for chunk, embedding in [
        (TextChunk(0, 1, 1, "내용", 2), [1.0]),
        (TextChunk(1, 1, 1, "내용", 2), vector()),
        (TextChunk(0, 0, 1, "내용", 2), vector()),
    ]:
        with pytest.raises(ValueError):
            await save_chunks(
                db,
                user_id=user.id,
                material_id=item.id,
                chunks=[EmbeddedChunk(chunk, embedding)],
            )
    assert await db.scalar(select(Chunk.id)) is None
