"""파서가 반환한 쪽/슬라이드 텍스트를 Unicode 손실 없이 토큰 기준으로 나눈다."""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

import tiktoken

from backend.rag.config import RAGSettings


@dataclass(frozen=True)
class PageText:
    number: int
    text: str


@dataclass(frozen=True)
class TextChunk:
    ordinal: int
    page_start: int
    page_end: int
    text: str
    token_count: int


def split_pages(
    pages: Sequence[PageText], *, settings: RAGSettings | None = None
) -> list[TextChunk]:
    """쪽 경계를 유지하고 긴 쪽만 분할한다. ordinal은 자료 안에서 0부터 시작한다.

    토큰이 문자 경계를 가로지를 수 있으므로 UTF-8 문자 경계로 자른 뒤 재토큰화한다.
    오버랩도 문자 경계로 조정하여 설정한 토큰 수를 초과하지 않게 한다.
    """
    settings = settings or RAGSettings()
    encoding = tiktoken.get_encoding("cl100k_base")
    chunks: list[TextChunk] = []
    previous_page = 0
    for page in pages:
        if page.number <= previous_page:
            raise ValueError("Page numbers must be positive and strictly increasing")
        previous_page = page.number
        if not page.text.strip():
            continue
        tokens = encoding.encode_ordinary(page.text)
        raw = page.text.encode("utf-8")
        byte_offsets = [0]
        for token in tokens:
            byte_offsets.append(byte_offsets[-1] + len(encoding.decode_single_token_bytes(token)))
        start = 0
        covered_end = 0
        while start < len(raw):
            token_start = bisect_right(byte_offsets, start) - 1
            token_end = min(len(tokens), token_start + settings.rag_chunk_tokens)
            # start is always a character boundary. Only a partial trailing character is dropped.
            text = raw[start : byte_offsets[token_end]].decode("utf-8", errors="ignore")
            if not text:
                text = raw[start : start + 4].decode("utf-8", errors="ignore")[:1]
            chunk_tokens = encoding.encode_ordinary(text)
            while len(chunk_tokens) > settings.rag_chunk_tokens:
                text = text[:-1]
                chunk_tokens = encoding.encode_ordinary(text)
            count = len(chunk_tokens)
            end = start + len(text.encode("utf-8"))
            if end <= covered_end:
                # With tiny budgets the overlap can consume the whole next window.
                # Drop that overlap rather than emitting a chunk with no new text.
                start = covered_end
                continue
            chunks.append(TextChunk(len(chunks), page.number, page.number, text, count))
            covered_end = end
            if end == len(raw):
                break
            overlap = ""
            if settings.rag_chunk_overlap_tokens:
                overlap = encoding.decode_bytes(
                    chunk_tokens[-settings.rag_chunk_overlap_tokens :]
                ).decode("utf-8", errors="ignore")
                while len(
                    encoding.encode_ordinary(overlap)
                ) > settings.rag_chunk_overlap_tokens or len(overlap) >= len(text):
                    overlap = overlap[1:]
            start = end - len(overlap.encode("utf-8"))
    return chunks
