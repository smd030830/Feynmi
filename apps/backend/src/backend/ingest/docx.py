"""DOCX(워드)에서 쪽별 텍스트를 추출한다 (python-docx).

워드 문서는 쪽이 저장되어 있지 않다(화면 크기에 따라 다시 나뉨). 그래서 사용자가 넣은
쪽 나누기(Ctrl+Enter, "앞에서 쪽 나누기")에서만 쪽을 나누고, 없으면 문서 전체가 1쪽이다.
본문의 문단과 표를 순서대로 읽고, 표는 한 행을 한 줄(" | "로 칸 구분)로 만든다.
머리글·바닥글·각주는 읽지 않는다. OCR을 쓸 때는 문단에 들어간 그림도 내놓는다.
"""

from collections.abc import Iterator
from io import BytesIO
from typing import Any

from docx import Document
from PIL import Image

from backend.domain.enums import FailureCode
from backend.ingest.base import IngestError, RawPage, check_page_count, normalize_text
from backend.ingest.image import try_decode
from backend.ingest.package import open_package

_DOCUMENT_PART = "word/document.xml"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class _Page:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.blobs: list[bytes] = []


def docx_raw_pages(data: bytes) -> list[RawPage]:
    """쪽 나누기로 나눈 쪽을 1부터 번호 붙여 반환한다."""
    open_package(data, _DOCUMENT_PART, "DOCX").close()
    try:
        document: Any = Document(BytesIO(data))
    except ValueError as exc:  # 정상 OOXML이지만 워드 문서가 아님
        raise IngestError(FailureCode.UNSUPPORTED_FORMAT, "not a Word document") from exc
    except Exception as exc:
        raise IngestError(FailureCode.CORRUPTED_FILE, "unreadable DOCX") from exc

    try:
        pages = _split(document)
    except IngestError:
        raise
    except Exception as exc:
        raise IngestError(FailureCode.CORRUPTED_FILE, "unreadable DOCX body") from exc
    check_page_count(len(pages))
    return [
        RawPage(number, normalize_text("\n".join(page.lines)), _images(page.blobs, number))
        for number, page in enumerate(pages, start=1)
    ]


def _split(document: Any) -> list[_Page]:
    related = document.part.related_parts
    pages = [_Page()]
    for block in document.element.body.iterchildren():
        if block.tag == f"{_W}p":
            if block.xpath("./w:pPr/w:pageBreakBefore") and (pages[-1].lines or pages[-1].blobs):
                pages.append(_Page())
            text = _paragraph_text(block)
            if text.strip():
                pages[-1].lines.append(text)
            for rid in block.xpath(".//a:blip/@r:embed"):
                part = related.get(rid)
                if part is not None:
                    pages[-1].blobs.append(part.blob)
            if block.xpath(".//w:br[@w:type='page']"):
                pages.append(_Page())
        elif block.tag == f"{_W}tbl":
            pages[-1].lines.extend(_table_rows(block))
    # 문서 끝의 쪽 나누기로 생긴 빈 쪽은 뺀다
    while len(pages) > 1 and not pages[-1].lines and not pages[-1].blobs:
        pages.pop()
    return pages


def _paragraph_text(paragraph: Any) -> str:
    parts: list[str] = []
    for node in paragraph.iter(f"{_W}t", f"{_W}tab", f"{_W}br", f"{_W}cr"):
        if node.tag == f"{_W}t":
            parts.append(node.text or "")
        elif node.tag == f"{_W}tab":
            parts.append("\t")
        elif node.get(f"{_W}type") != "page":
            parts.append("\n")
    return "".join(parts)


def _table_rows(table: Any) -> Iterator[str]:
    for row in table.xpath("./w:tr"):
        cells = [
            " ".join(_paragraph_text(p).strip() for p in cell.xpath(".//w:p")).strip()
            for cell in row.xpath("./w:tc")
        ]
        if any(cells):
            yield " | ".join(cells)


def _images(blobs: list[bytes], number: int):  # noqa: ANN202 - RawPage.images
    def load() -> Iterator[Image.Image]:
        for blob in blobs:
            image = try_decode(blob, f"DOCX page {number}")
            if image is not None:
                yield image

    return load
