"""조각 전 정리: 반복 머리글·바닥글 빼기."""

from backend.ingest.cleanup import drop_repeated_lines
from backend.rag.chunking import PageText


def lecture(bodies: list[str]) -> list[PageText]:
    # 실제 강의 PDF처럼 매 쪽 머리글(쪽 번호만 다름)과 책 이름이 붙는다
    return [
        PageText(n, f"<{n}> 컴퓨터 보안\n정보보호 개론 (인피니티 북스)\n{body}")
        for n, body in enumerate(bodies, start=1)
    ]


def test_repeated_headers_are_dropped_even_with_different_page_numbers() -> None:
    pages = drop_repeated_lines(
        lecture(["접근 제어란?", "인증의 유형", "지식 기반 인증", "소유 기반 인증"])
    )
    assert [p.text for p in pages] == [
        "접근 제어란?",
        "인증의 유형",
        "지식 기반 인증",
        "소유 기반 인증",
    ]
    assert [p.number for p in pages] == [1, 2, 3, 4]


def test_section_titles_on_fewer_than_half_of_pages_are_kept() -> None:
    # 7쪽 중 3쪽씩: 절반 미만이라 단원 제목은 남는다 (머리글은 7쪽 모두라 빠진다)
    bodies = [
        "2. 인증\n지식",
        "2. 인증\n소유",
        "2. 인증\n존재",
        "3. 모델\n강제적",
        "3. 모델\n임의적",
        "3. 모델\n역할",
        "정리",
    ]
    pages = drop_repeated_lines(lecture(bodies))
    assert pages[0].text == "2. 인증\n지식"
    assert pages[3].text == "3. 모델\n강제적"
    assert pages[6].text == "정리"


def test_short_materials_are_untouched() -> None:
    pages = lecture(["하나", "둘", "셋"])
    assert drop_repeated_lines(pages) == pages


def test_pages_without_text_keep_their_numbers() -> None:
    pages = lecture(["가", "나", "다", "라"]) + [PageText(5, "")]
    result = drop_repeated_lines(pages)
    assert [p.number for p in result] == [1, 2, 3, 4, 5]
    assert result[4].text == ""
