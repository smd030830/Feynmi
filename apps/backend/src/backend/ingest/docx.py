"""DOCX(워드)에서 쪽별 텍스트를 추출한다 (python-docx).

워드 문서는 쪽이 저장되어 있지 않다(화면 크기에 따라 다시 나뉨). 그래서 사용자가 넣은
쪽 나누기(Ctrl+Enter, "앞에서 쪽 나누기")에서만 쪽을 나누고, 없으면 문서 전체가 1쪽이다.
본문의 문단과 표를 순서대로 읽고, 표는 한 행을 한 줄(" | "로 칸 구분)로 만든다.
머리글·바닥글·각주는 읽지 않는다. 문단에 들어간 그림은 그 문단 바로 뒤 자리를 기록해 두어,
OCR한 글자가 설명 문단 옆에 들어가게 한다.
"""

from collections.abc import Iterator
from io import BytesIO
from typing import Any

from docx import Document
from PIL import Image

from backend.domain.enums import FailureCode
from backend.ingest.base import IngestError, PageParts, RawPage, check_page_count
from backend.ingest.image import try_decode
from backend.ingest.package import open_package
from backend.ingest.script import Script, scripted

_DOCUMENT_PART = "word/document.xml"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


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
        page.raw_page(number, _images(page.images, number))
        for number, page in enumerate(pages, start=1)
    ]


def _split(document: Any) -> list[PageParts[bytes]]:
    related = document.part.related_parts
    pages: list[PageParts[bytes]] = [PageParts()]
    for block in document.element.body.iterchildren():
        if block.tag == f"{_W}p":
            if block.xpath("./w:pPr/w:pageBreakBefore") and not pages[-1].empty:
                pages.append(PageParts())
            pages[-1].line(_paragraph_text(block))
            for rid in block.xpath(".//a:blip/@r:embed"):
                part = related.get(rid)
                if part is not None:
                    pages[-1].image(part.blob)
            if block.xpath(".//w:br[@w:type='page']"):
                pages.append(PageParts())
        elif block.tag == f"{_W}tbl":
            for row in _table_rows(block):
                pages[-1].line(row)
    # 문서 끝의 쪽 나누기로 생긴 빈 쪽은 뺀다
    while len(pages) > 1 and pages[-1].empty:
        pages.pop()
    return pages


def _run_text(run: Any) -> str:
    parts: list[str] = []
    for node in run.iter(f"{_W}t", f"{_W}tab", f"{_W}br", f"{_W}cr"):
        if node.tag == f"{_W}t":
            parts.append(node.text or "")
        elif node.tag == f"{_W}tab":
            parts.append("\t")
        elif node.get(f"{_W}type") != "page":
            parts.append("\n")
    return "".join(parts)


_SCRIPTS: dict[str, Script] = {"superscript": "super", "subscript": "sub"}


def _run_script(run: Any) -> Script | None:
    mark = run.find(f"{_W}rPr/{_W}vertAlign")
    value = mark.get(f"{_W}val") if mark is not None else None
    return _SCRIPTS.get(value or "")


def _paragraph_text(paragraph: Any) -> str:
    """문단 글자. 위·아래 첨자 표시를 살린다 (2 + 위첨자 12 → 2¹²)."""
    groups: list[tuple[Script | None, str]] = []
    for run in paragraph.iter(f"{_W}r"):
        text, script = _run_text(run), _run_script(run)
        if groups and groups[-1][0] == script:
            # 같은 첨자가 이어지면 합친다 ("1"+"0" → ¹⁰)
            groups[-1] = (script, groups[-1][1] + text)
        else:
            groups.append((script, text))
    return "".join(scripted(text, script) if script else text for script, text in groups)


def _table_rows(table: Any) -> Iterator[str]:
    for row in table.xpath("./w:tr"):
        cells = [
            " ".join(_paragraph_text(p).strip() for p in cell.xpath(".//w:p")).strip()
            for cell in row.xpath("./w:tc")
        ]
        if any(cells):
            yield " | ".join(cells)


def _images(blobs: list[bytes], number: int):  # noqa: ANN202 - RawPage.images
    def load() -> Iterator[Image.Image | None]:
        for blob in blobs:
            yield try_decode(blob, f"DOCX page {number}")  # 못 열면 None으로 자리만 지킨다

    return load
