import pytest
import tiktoken
from pydantic import ValidationError

from backend.rag.chunking import PageText, split_pages
from backend.rag.config import RAGSettings


def config(size: int = 20, overlap: int = 4) -> RAGSettings:
    return RAGSettings(rag_chunk_tokens=size, rag_chunk_overlap_tokens=overlap)


def test_pages_keep_boundaries_and_skip_blank_pages() -> None:
    chunks = split_pages(
        [PageText(1, "첫 번째 쪽"), PageText(2, " \n"), PageText(3, "마지막 슬라이드")],
        settings=config(),
    )
    assert [(c.ordinal, c.page_start, c.page_end, c.text) for c in chunks] == [
        (0, 1, 1, "첫 번째 쪽"),
        (1, 3, 3, "마지막 슬라이드"),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "한글 설명과 이모지 👩‍💻😀 자료를 나눕니다. " * 30,
        "가나다라마바사아자차카타파하" * 30,
        "<|endoftext|> user material " * 30,
        "a " * 500,
    ],
)
def test_no_unicode_or_text_is_lost_without_overlap(text: str) -> None:
    chunks = split_pages([PageText(1, text)], settings=config(overlap=0))
    assert "".join(c.text for c in chunks) == text
    encoding = tiktoken.get_encoding("cl100k_base")
    assert all(c.token_count == len(encoding.encode_ordinary(c.text)) <= 20 for c in chunks)
    assert all("�" not in c.text for c in chunks)


def test_overlap_is_bounded_and_makes_progress() -> None:
    text = "한글 자료의 중요한 내용을 연결해 기억합니다. " * 30
    chunks = split_pages([PageText(1, text)], settings=config())
    encoding = tiktoken.get_encoding("cl100k_base")
    position = 0
    for chunk in chunks:
        start = text.find(chunk.text, max(0, position - 10))
        assert start >= 0
        assert len(encoding.encode_ordinary(text[start:position])) <= 4
        assert start + len(chunk.text) > position
        position = start + len(chunk.text)
    assert position == len(text)


@pytest.mark.parametrize("numbers", [[0], [1, 1], [2, 1]])
def test_invalid_page_numbers_are_rejected(numbers: list[int]) -> None:
    with pytest.raises(ValueError, match="Page numbers"):
        split_pages([PageText(n, "내용") for n in numbers], settings=config())


def test_invalid_overlap_is_rejected() -> None:
    with pytest.raises(ValidationError):
        config(20, 20)


def test_empty_input_has_no_chunks() -> None:
    assert split_pages([], settings=config()) == []


def test_bpe_token_crossing_character_boundary_does_not_block_small_chunks() -> None:
    chunks = split_pages([PageText(1, "놤큶")], settings=config(4, 0))
    assert "".join(c.text for c in chunks) == "놤큶"
    assert all(0 < c.token_count <= 4 for c in chunks)


def test_small_budget_does_not_emit_overlap_only_chunks() -> None:
    text = "솞셏놤큶"
    chunks = split_pages([PageText(1, text)], settings=config(4, 2))
    covered = 0
    for chunk in chunks:
        start = text.index(chunk.text)
        assert start <= covered < start + len(chunk.text)
        covered = start + len(chunk.text)
    assert covered == len(text)
