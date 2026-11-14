"""학습자료 원본 → 쪽/슬라이드별 텍스트 (architecture 7.1 `extracting` 단계).

결과는 `backend.rag.chunking.split_pages`의 입력이다.
- `extract_pages`: 글자만 뽑는다 (OCR 없음, PDF/PPTX/TXT/DOCX/HWP/HWPX).
- `read_material`: 그림 속 글자까지 OCR로 읽는다 (PNG/JPG/HEIC, 스캔 PDF, 문서·슬라이드 속 그림).
"""

import asyncio
import logging
import re

from PIL import Image

from backend.domain.enums import FailureCode, FileType
from backend.ingest.base import (
    MAX_FILE_BYTES,
    MAX_PAGES,
    IngestError,
    RawPage,
    ensure_extractable,
    normalize_text,
)
from backend.ingest.config import OCRSettings
from backend.ingest.docx import docx_raw_pages
from backend.ingest.hwp import hwp_raw_pages
from backend.ingest.hwpx import hwpx_raw_pages
from backend.ingest.image import open_image_file
from backend.ingest.ocr import (
    HybridOcr,
    ImageTextReader,
    OcrUnavailableError,
    TesseractEngine,
    is_ocr_target,
)
from backend.ingest.pdf import extract_pdf_pages, pdf_raw_pages
from backend.ingest.pptx import extract_pptx_pages, pptx_raw_pages
from backend.ingest.sections import split_sections
from backend.ingest.text import txt_raw_pages
from backend.rag.chunking import PageText

__all__ = [
    "MAX_FILE_BYTES",
    "MAX_PAGES",
    "HybridOcr",
    "IngestError",
    "OCRSettings",
    "extract_pages",
    "extract_pdf_pages",
    "extract_pptx_pages",
    "has_real_pages",
    "make_ocr",
    "read_material",
]

logger = logging.getLogger(__name__)

# OCR 글자의 이 비율 이상이 이미 쪽 글자에 있으면 중복으로 보고 붙이지 않는다
# (예: 글자 층이 있는 스캔 PDF, 슬라이드 제목을 그대로 담은 캡처)
_DUPLICATE_RATIO = 0.8
_BLANK_LINES = re.compile(r"\n{3,}")


def extract_pages(data: bytes, file_type: str) -> list[PageText]:
    """`materials.file_type`에 맞는 파서로 글자만 뽑는다. 실패하면 IngestError."""
    match file_type:
        case FileType.PDF:
            return extract_pdf_pages(data)
        case FileType.PPTX:
            return extract_pptx_pages(data)
        case FileType.PNG | FileType.JPG | FileType.HEIC:
            raise IngestError(FailureCode.INTERNAL_ERROR, "image files need OCR")
        case FileType.TXT | FileType.DOCX | FileType.HWP | FileType.HWPX:
            raw = _DOCUMENT_READERS[file_type](data)
            pages = [PageText(p.number, p.text) for p in raw]
            return ensure_extractable(_finish(pages, file_type))
        case _:
            raise IngestError(FailureCode.UNSUPPORTED_FORMAT, f"file type {file_type!r}")


def make_ocr(
    ai: ImageTextReader | None = None, settings: OCRSettings | None = None
) -> HybridOcr | None:
    """자료 하나를 읽을 OCR을 만든다. Tesseract가 없으면 None (그림 글자는 건너뛴다).

    `ai`는 이미지 모델(LLM_IMAGE_TEXT_MODEL)과 키가 설정됐을 때만 넘긴다.
    """
    settings = settings or OCRSettings()
    engine = TesseractEngine(settings)
    try:
        engine.check()
    except OcrUnavailableError as exc:
        logger.warning("OCR disabled: %s", exc)
        return None
    return HybridOcr(engine, settings, ai)


# 글자 문서: 쪽 나누기에서만 쪽을 나눈다. DOCX·HWP·HWPX 속 그림은 OCR로 읽는다
_DOCUMENT_READERS = {
    FileType.TXT: txt_raw_pages,
    FileType.DOCX: docx_raw_pages,
    FileType.HWP: hwp_raw_pages,
    FileType.HWPX: hwpx_raw_pages,
}


def has_real_pages(file_type: str) -> bool:
    """PDF·PPTX·이미지는 실제 쪽이다. 글 문서의 "쪽"은 쪽 나누기나 구역이라 머리글이 없다."""
    return file_type not in _DOCUMENT_READERS


def _finish(pages: list[PageText], file_type: str) -> list[PageText]:
    """쪽 정보가 없는 글 문서는 긴 쪽을 구역으로 나눈다. PDF·PPTX·이미지는 실제 쪽 그대로."""
    return pages if has_real_pages(file_type) else split_sections(pages)


def _raw_pages(data: bytes, file_type: str) -> list[RawPage]:
    match file_type:
        case FileType.PDF:
            return pdf_raw_pages(data)
        case FileType.PPTX:
            return pptx_raw_pages(data)
        case FileType.TXT | FileType.DOCX | FileType.HWP | FileType.HWPX:
            return _DOCUMENT_READERS[file_type](data)
        case FileType.PNG | FileType.JPG | FileType.HEIC:
            image = open_image_file(data)
            return [RawPage(1, "", lambda: [image], whole_image=True)]
        case _:
            raise IngestError(FailureCode.UNSUPPORTED_FORMAT, f"file type {file_type!r}")


def _page_images(raw: RawPage) -> list[Image.Image | None]:
    """한 쪽의 그림을 모두 꺼낸다 (쪽 단위로만 메모리에 올린다)."""
    return list(raw.images())


async def _ocr_text(image: Image.Image | None, raw: RawPage, ocr: HybridOcr, page_text: str) -> str:
    """그림 하나를 읽어 쪽에 넣을 글자를 돌려준다. 넣을 게 없으면 빈 문자열."""
    if image is None or not ocr.has_budget():
        return ""
    if not raw.whole_image and not is_ocr_target(image.size, ocr.settings):
        return ""
    outcome = await ocr.read(image, whole_file=raw.whole_image)
    if not outcome.text or _is_duplicate(outcome.text, page_text):
        return ""
    return outcome.text


def _is_duplicate(ocr_text: str, page_text: str) -> bool:
    words = [w for w in ocr_text.split() if len(w) >= 2]
    if not words or not page_text:
        return False
    compact = "".join(page_text.split())
    return sum(w in compact for w in words) / len(words) >= _DUPLICATE_RATIO


async def read_material(data: bytes, file_type: str, ocr: HybridOcr | None) -> list[PageText]:
    """원본을 쪽별 글자로 읽고, 그림 속 글자는 OCR로 읽어 같은 쪽에 넣는다.

    워드·한글 문서는 그림이 있던 문단 바로 뒤에, 그 외에는 쪽 끝에 붙인다.
    쪽 정보가 없는 글 문서의 긴 쪽은 구역으로 나눈다 (`sections.split_sections`).
    `ocr`가 None이면(Tesseract 없음) 그림은 건너뛰고, 이미지 파일은 읽을 수 없어 실패한다.
    반환 길이가 곧 쪽 수(`materials.page_count`)다. 실패하면 IngestError.
    """
    # 파싱·쪽 그리기는 CPU 작업이라 별도 작업 줄에서 돌려 서버가 다른 요청을 계속 받게 한다.
    raw_pages = await asyncio.to_thread(_raw_pages, data, file_type)
    if ocr is None and any(p.whole_image for p in raw_pages):
        raise IngestError(FailureCode.INTERNAL_ERROR, "OCR engine is not available")

    pages: list[PageText] = []
    for raw in raw_pages:
        if ocr is not None and raw.parts is not None:
            text = await _with_inline_images(raw, ocr)
        else:
            parts = [raw.text] if raw.text else []
            if ocr is not None:
                for image in await asyncio.to_thread(_page_images, raw):
                    found = await _ocr_text(image, raw, ocr, "\n".join(parts))
                    if found:
                        parts.append(found)
            text = "\n\n".join(parts)
        pages.append(PageText(raw.number, normalize_text(text)))
    return ensure_extractable(_finish(pages, file_type))


async def _with_inline_images(raw: RawPage, ocr: HybridOcr) -> str:
    """글 줄 사이, 그림이 있던 자리에 그림 글자를 끼워 넣는다 (빈 줄로 앞뒤를 띄운다)."""
    images = await asyncio.to_thread(_page_images, raw)
    out: list[str] = []
    for part in raw.parts or ():
        if isinstance(part, str):
            out.append(part)
            continue
        image = images[part] if part < len(images) else None
        found = await _ocr_text(image, raw, ocr, raw.text)
        if found:
            out.append(f"\n{found}\n")
    return _BLANK_LINES.sub("\n\n", "\n".join(out))
