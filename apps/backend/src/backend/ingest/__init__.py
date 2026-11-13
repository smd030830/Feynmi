"""학습자료 원본 → 쪽/슬라이드별 텍스트 (architecture 7.1 `extracting` 단계).

결과는 `backend.rag.chunking.split_pages`의 입력이다.
- `extract_pages`: 글자만 뽑는다 (OCR 없음, PDF/PPTX).
- `read_material`: 그림 속 글자까지 OCR로 읽는다 (PNG/JPG, 스캔 PDF, PDF·PPTX 속 그림).
"""

import logging

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
    "make_ocr",
    "read_material",
]

logger = logging.getLogger(__name__)

# OCR 글자의 이 비율 이상이 이미 쪽 글자에 있으면 중복으로 보고 붙이지 않는다
# (예: 글자 층이 있는 스캔 PDF, 슬라이드 제목을 그대로 담은 캡처)
_DUPLICATE_RATIO = 0.8


def extract_pages(data: bytes, file_type: str) -> list[PageText]:
    """`materials.file_type`에 맞는 파서로 글자만 뽑는다. 실패하면 IngestError."""
    match file_type:
        case FileType.PDF:
            return extract_pdf_pages(data)
        case FileType.PPTX:
            return extract_pptx_pages(data)
        case FileType.PNG | FileType.JPG:
            raise IngestError(FailureCode.INTERNAL_ERROR, "image files need OCR")
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


def _raw_pages(data: bytes, file_type: str) -> list[RawPage]:
    match file_type:
        case FileType.PDF:
            return pdf_raw_pages(data)
        case FileType.PPTX:
            return pptx_raw_pages(data)
        case FileType.PNG | FileType.JPG:
            image = open_image_file(data)
            return [RawPage(1, "", lambda: [image], whole_image=True)]
        case _:
            raise IngestError(FailureCode.UNSUPPORTED_FORMAT, f"file type {file_type!r}")


def _is_duplicate(ocr_text: str, page_text: str) -> bool:
    words = [w for w in ocr_text.split() if len(w) >= 2]
    if not words or not page_text:
        return False
    compact = "".join(page_text.split())
    return sum(w in compact for w in words) / len(words) >= _DUPLICATE_RATIO


async def read_material(data: bytes, file_type: str, ocr: HybridOcr | None) -> list[PageText]:
    """원본을 쪽별 글자로 읽고, 그림 속 글자는 OCR로 읽어 같은 쪽 뒤에 붙인다.

    `ocr`가 None이면(Tesseract 없음) 그림은 건너뛰고, 이미지 파일은 읽을 수 없어 실패한다.
    반환 길이가 곧 쪽 수(`materials.page_count`)다. 실패하면 IngestError.
    """
    raw_pages = _raw_pages(data, file_type)
    if ocr is None and any(p.whole_image for p in raw_pages):
        raise IngestError(FailureCode.INTERNAL_ERROR, "OCR engine is not available")

    pages: list[PageText] = []
    for raw in raw_pages:
        parts = [raw.text] if raw.text else []
        if ocr is not None:
            for image in raw.images():
                if not ocr.has_budget():
                    break
                if not raw.whole_image and not is_ocr_target(image.size, ocr.settings):
                    continue
                outcome = await ocr.read(image)
                if outcome.text and not _is_duplicate(outcome.text, "\n".join(parts)):
                    parts.append(outcome.text)
        pages.append(PageText(raw.number, normalize_text("\n\n".join(parts))))
    return ensure_extractable(pages)
