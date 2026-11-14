"""쪽 구분이 없는 긴 글 문서를 구역으로 나눈다 (TXT·DOCX·HWP·HWPX).

워드·한글·메모장 문서는 쪽 정보가 저장되지 않아 쪽 나누기가 없으면 문서 전체가 "1쪽"이 된다.
그러면 판정 근거의 위치("n쪽")가 전부 1쪽이라 학습자가 근거를 찾아갈 수 없다.
그래서 긴 쪽은 제목처럼 보이는 줄(◈, ■, 1. , 제1장 …)에서, 없으면 줄 경계에서 잘라
"구역"으로 만들고 1부터 다시 번호를 붙인다. 짧은 문서는 그대로 둔다.
"""

import math
import re

from backend.ingest.base import MAX_PAGES
from backend.rag.chunking import PageText

# 이보다 짧은 쪽은 나누지 않는다. 구역은 대략 이 크기 이상이 된다
SECTION_CHARS = 1500
# 제목 줄을 못 만나도 이만큼 쌓이면 줄 경계에서 자른다
_HARD_RATIO = 5 / 3

_HEADING = re.compile(
    r"""^\s*(?:
        [◈◆◇■□▶▷●○★☆※#＃]          # 기호로 시작하는 제목
      | (?:chapter|part|section)\s*\d   # Chapter 3
      | 제\s*\d+\s*[장절편부강]         # 제3장, 제 2 절
      | \d{1,2}(?:\.\d{1,2})*\.?\s      # 1. 개요 / 2.3 스케줄링
      | \d{1,2}\)\s                     # 1) 개요
      | [IVX]{1,4}\.\s                  # II. 본론
      | [가-하]\.\s                     # 가. 목적
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def is_heading(line: str) -> bool:
    return len(line.strip()) <= 80 and bool(_HEADING.match(line))


def split_sections(pages: list[PageText]) -> list[PageText]:
    """긴 쪽을 구역으로 나누고 번호를 다시 붙인다. 구역 수는 MAX_PAGES를 넘지 않는다."""
    total = sum(len(p.text) for p in pages)
    # 쪽 끝마다 짧은 구역이 하나씩 더 생길 수 있으니 그만큼 빼고 크기를 정한다
    room = max(MAX_PAGES - len(pages), 1)
    target = max(SECTION_CHARS, math.ceil(total / room))
    pieces = [piece for page in pages for piece in _split_page(page.text, target)]
    return [PageText(number, text) for number, text in enumerate(pieces, start=1)]


def _split_page(text: str, target: int) -> list[str]:
    if len(text) <= target:
        return [text]
    hard = int(target * _HARD_RATIO)
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.split("\n"):
        # 구역이 충분히 쌓였으면 제목 줄 앞에서, 너무 커지면 아무 줄 앞에서 자른다
        if size >= target and line.strip() and (is_heading(line) or size + len(line) > hard):
            pieces.append("\n".join(current).strip())
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    pieces.append("\n".join(current).strip())
    return [piece for piece in pieces if piece]
