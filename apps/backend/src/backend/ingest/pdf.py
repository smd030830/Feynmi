"""PDF에서 쪽별 텍스트를 추출한다 (PRD 9.1).

파일 검사·암호 확인·박힌 그림은 pypdf, 글자는 PDFium(pypdfium2)으로 읽는다.
PDF 속 띄어쓰기는 공백 글자 없이 글자 간격으로만 들어 있는 경우가 많은데(강의 슬라이드 등),
pypdf는 이를 공백으로 못 바꿔 "적절한권한을가진…"처럼 붙여 버린다. PDFium은 간격을 보고
공백을 넣으며, 2단 문서도 쓰인 순서대로 읽는다. PDFium이 못 읽는 쪽은 pypdf 결과를 쓴다.

OCR을 쓸 때는 쪽마다 그림도 내놓는다.
- 글자가 없는 쪽(스캔본): 쪽 전체를 그림으로 그려(pypdfium2) 읽는다.
- 글자가 있는 쪽: 안에 박힌 그림만 꺼내 읽는다.
"""

import logging
import re
import threading
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
# PDFium은 여러 작업 줄에서 동시에 부르면 안 된다 (자료 여러 개를 동시에 분석할 때)
_PDFIUM_LOCK = threading.Lock()
# 글자로 의미가 없는 문자: 제어 문자(줄바꿈·탭 제외), 글꼴 전용 영역(장식 기호가 U+F000 등으로 나옴)
_JUNK_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f-￾￿]")


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


def _clean(text: str) -> str:
    return normalize_text(_JUNK_CHARS.sub("", text))


def _page_text(page: PageObject, number: int, pdfium: _Pdfium) -> str:
    text = pdfium.text(number - 1)
    if text:
        return text
    try:
        return _clean(page.extract_text())
    except Exception as exc:
        raise IngestError(FailureCode.CORRUPTED_FILE, f"page {number}") from exc


class _Pdfium:
    """PDFium으로 쪽 글자를 읽고, 쪽 그림은 필요할 때 하나씩 만든다.

    300쪽 그림을 한꺼번에 메모리에 올리지 않는다.
    """

    def __init__(self, data: bytes) -> None:
        self.data = data

    @cached_property
    def document(self) -> pypdfium2.PdfDocument:
        return pypdfium2.PdfDocument(self.data)

    def text(self, index: int) -> str:
        """쪽 글자. 못 읽으면 빈 문자열 (pypdf 결과로 대신한다)."""
        try:
            with _PDFIUM_LOCK:
                text = self.document[index].get_textpage().get_text_range()
        except Exception:
            logger.info("PDFium could not read text of page %d", index + 1)
            return ""
        return _clean(text)

    def render(self, index: int) -> Iterator[Image.Image]:
        try:
            with _PDFIUM_LOCK:
                page = self.document[index]
                width, height = page.get_size()
                scale = min(_RENDER_DPI / 72, _RENDER_MAX_SIDE / max(width, height, 1))
                # pypdfium2 문서상 scale은 float이다 (기본값 1 때문에 int로 추론됨)
                image = page.render(scale=scale).to_pil()  # pyright: ignore[reportArgumentType]
        except Exception:
            logger.info("skip unrenderable PDF page %d", index + 1)
            return
        yield image

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
    pdfium = _Pdfium(data)
    pages: list[RawPage] = []
    for number, page in enumerate(reader.pages, start=1):
        text = _page_text(page, number, pdfium)
        if text:
            loader = partial(pdfium.embedded, page, number)
        else:
            loader = partial(pdfium.render, number - 1)
        pages.append(RawPage(number, text, loader))
    return pages


def extract_pdf_pages(data: bytes) -> list[PageText]:
    """OCR 없이 글자만 뽑는다. 반환 길이가 곧 쪽 수(`materials.page_count`)다."""
    return ensure_extractable([PageText(p.number, p.text) for p in pdf_raw_pages(data)])
