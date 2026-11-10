"""임베딩 준비와 DB 작업을 분리한다. 커밋/롤백은 호출 서비스의 책임이다."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Chunk, Material, Project
from backend.domain.enums import MaterialStatus
from backend.errors import AppError
from backend.llm import LLMProvider, validate_embedding
from backend.rag.chunking import TextChunk
from backend.rag.config import RAGSettings


@dataclass(frozen=True)
class EmbeddedChunk:
    chunk: TextChunk
    embedding: list[float]


@dataclass(frozen=True)
class RetrievedChunk:
    id: uuid.UUID
    material_id: uuid.UUID
    material_title: str
    page_start: int
    page_end: int
    text: str


async def embed_chunks(chunks: Sequence[TextChunk], provider: LLMProvider) -> list[EmbeddedChunk]:
    """DB 세션 없이 호출한다. 저장 전에 모든 임베딩이 준비되어야 한다."""
    if not chunks:
        return []
    vectors = await provider.embed([chunk.text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise ValueError("Embedding count must match chunk count")
    return [
        EmbeddedChunk(chunk, validate_embedding(vector))
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


async def save_chunks(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    material_id: uuid.UUID,
    chunks: Sequence[EmbeddedChunk],
) -> list[Chunk]:
    """본인 자료에 청크를 최초 저장한다. 기존 근거를 암묵적으로 삭제하지 않는다.

    호출자는 트랜잭션을 열고 성공 시 커밋한다. 분석 재시도/삭제 정책은 워커 구현 범위다.
    """
    material = await db.scalar(
        select(Material)
        .join(Project, Project.id == Material.project_id)
        .where(Material.id == material_id, Project.user_id == user_id)
        .with_for_update(of=Material)
    )
    if material is None:
        raise AppError(404, "not_found", "material not found")
    if await db.scalar(select(Chunk.id).where(Chunk.material_id == material_id).limit(1)):
        raise ValueError("Material already has chunks")
    rows: list[Chunk] = []
    for ordinal, item in enumerate(chunks):
        chunk = item.chunk
        if (
            chunk.ordinal != ordinal
            or not chunk.text.strip()
            or chunk.token_count <= 0
            or chunk.page_start < 1
            or chunk.page_end < chunk.page_start
        ):
            raise ValueError("Invalid chunk metadata")
        rows.append(
            Chunk(
                material_id=material.id,
                project_id=material.project_id,
                ordinal=chunk.ordinal,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                text=chunk.text,
                token_count=chunk.token_count,
                embedding=validate_embedding(item.embedding),
            )
        )
    db.add_all(rows)
    await db.flush()
    return rows


async def search_chunks(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    query_embedding: list[float],
    evidence_chunk_ids: Sequence[uuid.UUID] = (),
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """본인 프로젝트의 ready 자료를 코사인 거리로 검색하고 필수 근거를 합친다.

    쿼리 임베딩은 DB 세션을 열기 전에 provider.embed로 준비한다.
    필수 근거도 동일한 소유자/프로젝트/ready 필터를 통과해야 한다.
    """
    if top_k is None:
        top_k = RAGSettings().rag_top_k
    if top_k < 1:
        raise ValueError("top_k must be positive")
    vector = validate_embedding(query_embedding)
    owned = await db.scalar(
        select(Project.id).where(Project.id == project_id, Project.user_id == user_id)
    )
    if owned is None:
        raise AppError(404, "not_found", "project not found")
    eligible = (
        select(Chunk, Material.title)
        .join(Material, Material.id == Chunk.material_id)
        .join(Project, Project.id == Material.project_id)
        .where(
            Project.id == project_id,
            Project.user_id == user_id,
            Chunk.project_id == project_id,
            Material.status == MaterialStatus.READY,
        )
    )
    ranked = await db.execute(
        eligible.order_by(Chunk.embedding.cosine_distance(vector), Chunk.id).limit(top_k)
    )
    combined = list(ranked)
    required_ids = set(evidence_chunk_ids)
    if required_ids:
        required = await db.execute(eligible.where(Chunk.id.in_(required_ids)).order_by(Chunk.id))
        required_rows = list(required)
        if {row.id for row, _ in required_rows} != required_ids:
            raise ValueError("Evidence chunks are not available in this project")
        combined.extend(required_rows)
    result: dict[uuid.UUID, RetrievedChunk] = {}
    for row, title in combined:
        result.setdefault(
            row.id,
            RetrievedChunk(
                row.id,
                row.material_id,
                title,
                row.page_start,
                row.page_end,
                row.text,
            ),
        )
    return list(result.values())
