"""조각을 만들기 전 쪽 글자 정리.

DB의 `materials.page_texts`("글자 보기")에는 원문 그대로 두고, 조각·임베딩에만 적용한다.
"""

import math
import re
from collections import Counter
from collections.abc import Sequence

from backend.rag.chunking import PageText

# 이 쪽 수보다 적은 자료는 머리글을 가려낼 근거가 부족해 그대로 둔다
_MIN_PAGES = 4
# 글자가 있는 쪽의 이 비율 이상에 똑같이 나오는 줄을 머리글·바닥글로 본다
_REPEAT_RATIO = 0.5
_DIGITS = re.compile(r"\d+")


def _key(line: str) -> str:
    # 쪽 번호만 다른 머리글("<4> 컴퓨터 보안", "<5> 컴퓨터 보안")을 같은 줄로 센다
    return _DIGITS.sub("#", " ".join(line.split()))


def drop_repeated_lines(pages: Sequence[PageText]) -> list[PageText]:
    """여러 쪽에 반복되는 머리글·바닥글 줄을 뺀다.

    강의 슬라이드는 매 쪽 "컴퓨터 보안 / 정보보호 개론 (…)" 같은 줄이 반복되어,
    조각마다 같은 글이 섞이고 검색 품질이 떨어진다.
    """
    with_text = [p for p in pages if p.text.strip()]
    if len(with_text) < _MIN_PAGES:
        return list(pages)
    seen = Counter(
        key
        for page in with_text
        for key in {_key(line) for line in page.text.split("\n") if line.strip()}
    )
    threshold = max(_MIN_PAGES - 1, math.ceil(len(with_text) * _REPEAT_RATIO))
    repeated = {key for key, count in seen.items() if count >= threshold}
    if not repeated:
        return list(pages)
    return [
        PageText(
            page.number,
            "\n".join(line for line in page.text.split("\n") if _key(line) not in repeated).strip(),
        )
        for page in pages
    ]
