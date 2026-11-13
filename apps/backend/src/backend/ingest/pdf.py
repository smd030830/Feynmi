"""PDF에서 쪽별 텍스트를 추출한다 (pypdf, PRD 9.1).

OCR을 쓸 때는 쪽마다 그림도 내놓는다.
- 글자가 없는 쪽(스캔본): 쪽 전체를 그림으로 그려(pypdfium2) 읽는다.
- 글자가 있는 쪽: 안에 박힌 그림만 꺼내 읽는다.
"""

import logging
from collections.abc import Iterator
from functools import cached_property, partial
from io import BytesIO

import pypdfium2
from PIL import Image
from pypdf import PageObject, PdfReader

from backend.domain.enums import FailureCode
from backend.ingest.base import (
    IngestError,
    RawPage,
    check_page_count,
    check_size,
    ensure_extractable,
    normalize_text,
)
from backend.ingest.image import try_decode
from backend.rag.chunking import PageText

logger = logging.getLogger(__name__)

# PDF 명세는 헤더가 파일 앞 1024바이트 안에 있으면 허용한다.
_HEADER = b"%PDF-"
_HEADER_WINDOW = 1024
# 스캔 쪽을 그릴 해상도와 긴 변 상한 (A4 300dpi ≈ 2480×3508)
_RENDER_DPI = 300
_RENDER_MAX_SIDE = 4000


def _open(data: bytes) -> PdfReader:
    check_size(data)
    if _HEADER not in data[:_HEADER_WINDOW]:
        raise IngestError(FailureCode.UNSUPPORTED_FORMAT, "missing PDF header")
    try:
        reader = PdfReader(BytesIO(data))
        # 열기 암호 없이 권한만 제한한 PDF는 빈 암호로 열린다.
        if reader.is_encrypted and not reader.decrypt(""):
            raise IngestError(FailureCode.CORRUPTED_FILE, "password protected PDF")
        page_count = len(reader.pages)
    except IngestError:
        raise
    except Exception as exc:  # 신뢰할 수 없는 입력이라 pypdf가 내는 모든 오류를 손상으로 본다.
        raise IngestError(FailureCode.CORRUPTED_FILE, "unreadable PDF") from exc
    check_page_count(page_count)
    return reader


def _page_text(page: PageObject, number: int) -> str:
    try:
        return normalize_text(page.extract_text())
    except Exception as exc:
        raise IngestError(FailureCode.CORRUPTED_FILE, f"page {number}") from exc


class _PdfImages:
    """쪽 그림을 필요할 때 하나씩 만든다 (300쪽 그림을 한꺼번에 메모리에 올리지 않는다)."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    @cached_property
    def document(self) -> pypdfium2.PdfDocument:
        return pypdfium2.PdfDocument(self.data)

    def render(self, index: int) -> Iterator[Image.Image]:
        try:
            page = self.document[index]
            width, height = page.get_size()
            scale = min(_RENDER_DPI / 72, _RENDER_MAX_SIDE / max(width, height, 1))
            # pypdfium2 문서상 scale은 float이다 (기본값 1 때문에 int로 추론됨)
            yield page.render(scale=scale).to_pil()  # pyright: ignore[reportArgumentType]
        except Exception:
            logger.info("skip unrenderable PDF page %d", index + 1)

    @staticmethod
    def embedded(page: PageObject, number: int) -> Iterator[Image.Image]:
        try:
            files = list(page.images)
        except Exception:
            logger.info("skip images of PDF page %d", number)
            return
        for file in files:
            try:
                data = file.data
            except Exception:
                continue
            image = try_decode(data, f"PDF page {number}")
            if image is not None:
                yield image


def pdf_raw_pages(data: bytes) -> list[RawPage]:
    """모든 쪽을 1부터 번호 붙여 반환한다. 텍스트가 없는 쪽도 번호를 유지하려고 포함한다."""
    reader = _open(data)
    images = _PdfImages(data)
    pages: list[RawPage] = []
    for number, page in enumerate(reader.pages, start=1):
        text = _page_text(page, number)
        if text:
            loader = partial(images.embedded, page, number)
        else:
            loader = partial(images.render, number - 1)
        pages.append(RawPage(number, text, loader))
    return pages


def extract_pdf_pages(data: bytes) -> list[PageText]:
    """OCR 없이 글자만 뽑는다. 반환 길이가 곧 쪽 수(`materials.page_count`)다."""
    return ensure_extractable([PageText(p.number, p.text) for p in pdf_raw_pages(data)])
