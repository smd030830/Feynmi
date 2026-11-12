"""텍스트 PDF에서 쪽별 텍스트를 추출한다 (pypdf, PRD 9.1)."""

from io import BytesIO

from pypdf import PdfReader

from backend.domain.enums import FailureCode
from backend.ingest.base import (
    IngestError,
    check_page_count,
    check_size,
    ensure_extractable,
    normalize_text,
)
from backend.rag.chunking import PageText

# PDF 명세는 헤더가 파일 앞 1024바이트 안에 있으면 허용한다.
_HEADER = b"%PDF-"
_HEADER_WINDOW = 1024


def extract_pdf_pages(data: bytes) -> list[PageText]:
    """모든 쪽을 1부터 번호 붙여 반환한다. 텍스트가 없는 쪽도 번호를 유지하려고 포함한다.

    반환 길이가 곧 쪽 수(`materials.page_count`)다.
    """
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

    pages: list[PageText] = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text()
        except Exception as exc:
            raise IngestError(FailureCode.CORRUPTED_FILE, f"page {number}") from exc
        pages.append(PageText(number, normalize_text(text)))
    return ensure_extractable(pages)
