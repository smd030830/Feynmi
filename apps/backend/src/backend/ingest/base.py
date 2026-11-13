"""자료 파서 공통 규칙: 실패 코드, 업로드 상한, 텍스트 정리 (PRD FR-1.2, FR-1.4)."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from PIL import Image

from backend.domain.enums import FailureCode
from backend.rag.chunking import PageText

MAX_FILE_BYTES = 50 * 1024 * 1024  # PRD FR-1.2: 파일당 50MB
MAX_PAGES = 300  # PRD FR-1.2: PDF 300쪽 / PPTX 300슬라이드


@dataclass(frozen=True)
class RawPage:
    """OCR 전의 한 쪽: 뽑힌 글자와, 필요할 때 그림을 꺼내 주는 함수."""

    number: int
    text: str
    images: Callable[[], Iterable[Image.Image]]
    # 업로드한 이미지 파일 자체라면 크기와 상관없이 읽는다
    whole_image: bool = False


class IngestError(Exception):
    """파싱 실패. 워커는 `code`를 `materials.failure_code`로 기록한다 (architecture 7.1)."""

    def __init__(self, code: FailureCode, message: str = "") -> None:
        super().__init__(message or code.value)
        self.code = code


def check_size(data: bytes) -> None:
    # 업로드 단계에서도 막지만, 파서 입력은 신뢰하지 않는다.
    if len(data) > MAX_FILE_BYTES:
        raise IngestError(FailureCode.FILE_TOO_LARGE, f"{len(data)} bytes")


def check_page_count(count: int) -> None:
    if count > MAX_PAGES:
        raise IngestError(FailureCode.TOO_MANY_PAGES, f"{count} pages")


def normalize_text(text: str) -> str:
    """줄바꿈을 통일하고 PostgreSQL text에 저장할 수 없는 NUL 문자를 지운다."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()


def ensure_extractable(pages: Sequence[PageText]) -> list[PageText]:
    """모든 쪽에 텍스트가 없으면 스캔 자료로 보고 실패시킨다 (FR-1.4)."""
    if not any(page.text.strip() for page in pages):
        raise IngestError(FailureCode.NO_EXTRACTABLE_TEXT)
    return list(pages)
