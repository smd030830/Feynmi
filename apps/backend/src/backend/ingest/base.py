"""자료 파서 공통 규칙: 실패 코드, 업로드 상한, 텍스트 정리 (PRD FR-1.2, FR-1.4)."""

import re
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
    # 그림을 순서대로 낸다. parts를 쓰는 쪽은 못 연 그림 자리에 None을 내어 번호를 맞춘다
    images: Callable[[], Iterable[Image.Image | None]]
    # 업로드한 이미지 파일 자체라면 크기와 상관없이 읽는다
    whole_image: bool = False
    # 글 줄(str)과 그림 번호(int)를 문서에 나온 순서대로 담는다. 있으면 그림 글자를 그 자리에
    # 끼워 넣는다 (워드·한글 문서: 설명 문단 바로 뒤에 그 캡처 글자). 없으면 쪽 끝에 붙인다.
    parts: tuple[str | int, ...] | None = None


class PageParts[T]:
    """문서 한 쪽을 읽으며 글 줄과 그림 자리를 순서대로 모은다 (DOCX·HWP·HWPX).

    `T`는 그림을 다시 찾을 단서(파일 경로, 바이트 등)이고, `RawPage.parts`의 숫자가 그 번호다.
    """

    def __init__(self) -> None:
        self.parts: list[str | int] = []
        self.images: list[T] = []

    def line(self, text: str) -> None:
        if text.strip():
            self.parts.append(text)

    def image(self, ref: T) -> None:
        self.parts.append(len(self.images))
        self.images.append(ref)

    @property
    def empty(self) -> bool:
        return not self.parts

    def text(self) -> str:
        return normalize_text("\n".join(p for p in self.parts if isinstance(p, str)))

    def raw_page(self, number: int, images: Callable[[], Iterable[Image.Image | None]]) -> RawPage:
        return RawPage(number, self.text(), images, parts=tuple(self.parts))


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


# 글자로 의미가 없는 문자: 제어 문자(줄바꿈·탭 제외, NUL은 PostgreSQL text에 저장 불가),
# 글꼴 전용 영역(PDF 장식 기호 U+F000, 한글 문서의 기호 U+F0099 등)
_JUNK_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f-￾￿\U000f0000-\U0010ffff]")


def normalize_text(text: str) -> str:
    """줄바꿈을 통일하고 저장·검색에 쓸모없는 문자를 지운다."""
    return _JUNK_CHARS.sub("", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def ensure_extractable(pages: Sequence[PageText]) -> list[PageText]:
    """모든 쪽에 텍스트가 없으면 스캔 자료로 보고 실패시킨다 (FR-1.4)."""
    if not any(page.text.strip() for page in pages):
        raise IngestError(FailureCode.NO_EXTRACTABLE_TEXT)
    return list(pages)
