"""학습자료 원본 → 쪽/슬라이드별 텍스트 (architecture 7.1 `extracting` 단계).

결과는 `backend.rag.chunking.split_pages`의 입력이다.
"""

from backend.domain.enums import FailureCode, FileType
from backend.ingest.base import MAX_FILE_BYTES, MAX_PAGES, IngestError
from backend.ingest.pdf import extract_pdf_pages
from backend.ingest.pptx import extract_pptx_pages
from backend.rag.chunking import PageText

__all__ = [
    "MAX_FILE_BYTES",
    "MAX_PAGES",
    "IngestError",
    "extract_pages",
    "extract_pdf_pages",
    "extract_pptx_pages",
]


def extract_pages(data: bytes, file_type: str) -> list[PageText]:
    """`materials.file_type`에 맞는 파서로 원본 바이트를 읽는다. 실패하면 IngestError."""
    match file_type:
        case FileType.PDF:
            return extract_pdf_pages(data)
        case FileType.PPTX:
            return extract_pptx_pages(data)
        case _:
            raise IngestError(FailureCode.UNSUPPORTED_FORMAT, f"file type {file_type!r}")
