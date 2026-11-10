from unittest.mock import AsyncMock

import pytest

from backend.llm import LLMProvider
from backend.rag.chunking import PageText, split_pages
from backend.rag.store import embed_chunks


async def test_chunk_embedding_preparation_preserves_text_and_order() -> None:
    chunks = split_pages([PageText(1, "첫 설명"), PageText(2, "다음 설명")])
    provider = AsyncMock(spec=LLMProvider)
    vectors = [[1.0] + [0.0] * 1535, [0.0, 1.0] + [0.0] * 1534]
    provider.embed.return_value = vectors
    result = await embed_chunks(chunks, provider)
    provider.embed.assert_awaited_once_with(["첫 설명", "다음 설명"])
    assert [item.chunk for item in result] == chunks
    assert [item.embedding for item in result] == vectors


async def test_empty_chunks_do_not_call_provider() -> None:
    provider = AsyncMock(spec=LLMProvider)
    assert await embed_chunks([], provider) == []
    provider.embed.assert_not_awaited()


@pytest.mark.parametrize("vectors", [[], [[1.0]], [[0.0] * 1536]])
async def test_invalid_provider_results_cannot_be_prepared(vectors: list[list[float]]) -> None:
    provider = AsyncMock(spec=LLMProvider)
    provider.embed.return_value = vectors
    with pytest.raises(ValueError):
        await embed_chunks(split_pages([PageText(1, "내용")]), provider)
