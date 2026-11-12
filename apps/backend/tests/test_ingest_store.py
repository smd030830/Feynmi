"""파싱 → 청킹 → 임베딩 → 실제 pgvector 저장 (FM-051). 테스트 DB가 필요하다."""

import io
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from pptx import Presentation
from pptx.util import Inches
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from backend.db.models import Chunk, Material, Project, User
from backend.db.session import make_session_factory
from backend.errors import AppError
from backend.ingest import extract_pages
from backend.llm import LLMProvider
from backend.rag.chunking import split_pages
from backend.rag.store import EmbeddedChunk, embed_chunks, save_chunks

pytestmark = pytest.mark.usefixtures("migrated_db")


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with make_session_factory(engine)() as session:
        yield session
        await session.rollback()


async def owned_material(db: AsyncSession, uid: str) -> tuple[User, Material]:
    user = User(firebase_uid=uid, email=f"{uid}@example.com", sign_in_provider="password")
    db.add(user)
    await db.flush()
    project = Project(user_id=user.id, name=uid, color="indigo")
    db.add(project)
    await db.flush()
    material = Material(
        project_id=project.id,
        title="강의자료",
        file_type="pptx",
        gcs_path="test.pptx",
        size_bytes=1,
        status="extracting",
    )
    db.add(material)
    await db.flush()
    return user, material


def pptx(slides: list[str]) -> bytes:
    presentation = Presentation()
    for text in slides:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        if text:
            box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(3))
            box.text_frame.text = text
    out = io.BytesIO()
    presentation.save(out)
    return out.getvalue()


async def prepared(data: bytes) -> list[EmbeddedChunk]:
    provider = AsyncMock(spec=LLMProvider)

    async def embed(texts: list[str]) -> list[list[float]]:
        return [[float(i + 1)] + [0.0] * 1535 for i in range(len(texts))]

    provider.embed.side_effect = embed
    return await embed_chunks(split_pages(extract_pages(data, "pptx")), provider)


async def test_parsed_material_is_stored_with_pages_and_vectors(db: AsyncSession) -> None:
    user, material = await owned_material(db, "alice")
    chunks = await prepared(pptx(["프로세스 정의", "", "스레드와 프로세스의 차이"]))
    await save_chunks(db, user_id=user.id, material_id=material.id, chunks=chunks)

    rows = list(
        await db.scalars(
            select(Chunk).where(Chunk.material_id == material.id).order_by(Chunk.ordinal)
        )
    )
    assert [(r.ordinal, r.page_start, r.page_end, r.text) for r in rows] == [
        (0, 1, 1, "프로세스 정의"),
        (1, 3, 3, "스레드와 프로세스의 차이"),
    ]
    assert all(r.project_id == material.project_id for r in rows)
    assert [len(r.embedding) for r in rows] == [1536, 1536]
    assert [float(r.embedding[0]) for r in rows] == [1.0, 2.0]


async def test_other_users_material_and_duplicate_save_are_rejected(db: AsyncSession) -> None:
    owner, material = await owned_material(db, "owner")
    other, _ = await owned_material(db, "other")
    chunks = await prepared(pptx(["본문"]))
    with pytest.raises(AppError):
        await save_chunks(db, user_id=other.id, material_id=material.id, chunks=chunks)
    with pytest.raises(AppError):
        await save_chunks(db, user_id=owner.id, material_id=uuid.uuid4(), chunks=chunks)

    await save_chunks(db, user_id=owner.id, material_id=material.id, chunks=chunks)
    with pytest.raises(ValueError, match="already has chunks"):
        await save_chunks(db, user_id=owner.id, material_id=material.id, chunks=chunks)
