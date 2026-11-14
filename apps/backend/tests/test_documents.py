"""글자 문서 형식: TXT, DOCX, HWPX, HWP (test_minseok2 실험 추가, PRD 미반영)."""

import io
import struct
import zipfile
import zlib
from typing import Any

import pytest
from docx import Document
from docx.shared import Inches
from test_read_material import FakeEngine, image_bytes, ocr

from backend.domain.enums import FailureCode
from backend.ingest import MAX_PAGES, IngestError, extract_pages, has_real_pages, read_material
from backend.ingest import hwp as hwp_module
from backend.ingest.hwp import PARA_HEADER, PARA_TEXT, SHAPE_COMPONENT_PICTURE, para_text, records
from backend.ingest.package import MAX_UNZIPPED_BYTES
from backend.ingest.script import Script, scripted
from backend.ingest.sections import SECTION_CHARS, split_sections
from backend.rag.chunking import PageText

# --- TXT ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        "운영체제 정리\n프로세스".encode(),  # UTF-8 (요즘 메모장)
        "운영체제 정리\n프로세스".encode("cp949"),  # 예전 메모장 "ANSI"
        "운영체제 정리\r\n프로세스".encode("utf-16"),  # BOM 있는 UTF-16
        "﻿운영체제 정리\n프로세스".encode(),  # BOM 있는 UTF-8
    ],
)
def test_txt_korean_encodings(data: bytes) -> None:
    pages = extract_pages(data, "txt")
    assert [(p.number, p.text) for p in pages] == [(1, "운영체제 정리\n프로세스")]


def test_txt_form_feed_splits_pages() -> None:
    pages = extract_pages("1장\f2장".encode(), "txt")
    assert [(p.number, p.text) for p in pages] == [(1, "1장"), (2, "2장")]


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"\x89PNG\r\n\x1a\n\x00\x00binary", FailureCode.UNSUPPORTED_FORMAT),  # 이름만 .txt
        (b"   \n\t ", FailureCode.NO_EXTRACTABLE_TEXT),
    ],
)
def test_txt_failures(data: bytes, code: FailureCode) -> None:
    with pytest.raises(IngestError) as error:
        extract_pages(data, "txt")
    assert error.value.code == code


# --- DOCX ---------------------------------------------------------------------


def make_docx(with_picture: bool = False) -> bytes:
    document: Any = Document()
    document.add_heading("1장 프로세스", level=1)
    document.add_paragraph("프로세스는 실행 중인 프로그램이다.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "상태"
    table.cell(0, 1).text = "설명"
    table.cell(1, 0).text = "준비"
    table.cell(1, 1).text = "CPU를 기다림"
    document.add_page_break()
    document.add_paragraph("2장 스레드")
    if with_picture:
        document.add_picture(io.BytesIO(image_bytes((400, 200), color="gray")), width=Inches(3))
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def test_docx_paragraphs_tables_and_page_breaks() -> None:
    pages = extract_pages(make_docx(), "docx")
    assert [p.number for p in pages] == [1, 2]
    assert pages[0].text == (
        "1장 프로세스\n프로세스는 실행 중인 프로그램이다.\n상태 | 설명\n준비 | CPU를 기다림"
    )
    assert pages[1].text == "2장 스레드"


async def test_docx_picture_is_read_on_its_page() -> None:
    engine = FakeEngine("그림 속 설명")
    pages = await read_material(make_docx(with_picture=True), "docx", ocr(engine))
    assert pages[1].text == "2장 스레드\n\n그림 속 설명"
    assert len(engine.sizes) == 1


def test_docx_rejects_other_office_files() -> None:
    pptx_like = io.BytesIO()
    with zipfile.ZipFile(pptx_like, "w") as z:
        z.writestr("ppt/presentation.xml", "<p/>")
    with pytest.raises(IngestError) as error:
        extract_pages(pptx_like.getvalue(), "docx")
    assert error.value.code == FailureCode.UNSUPPORTED_FORMAT


# --- HWPX ---------------------------------------------------------------------

_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HC = "http://www.hancom.co.kr/hwpml/2011/core"


def make_hwpx(section: str, files: dict[str, bytes] | None = None) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr(
            "Contents/content.hpf",
            '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/"><opf:manifest>'
            '<opf:item id="image1" href="BinData/image1.png" media-type="image/png"/>'
            "</opf:manifest></opf:package>",
        )
        z.writestr(
            "Contents/section0.xml",
            f'<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
            f'xmlns:hp="{_HP}" xmlns:hc="{_HC}">{section}</hs:sec>',
        )
        for name, data in (files or {}).items():
            z.writestr(name, data)
    return out.getvalue()


def para(text: str, page_break: bool = False, inner: str = "") -> str:
    run = f"<hp:run><hp:t>{text}</hp:t>{inner}</hp:run>"
    return f'<hp:p pageBreak="{1 if page_break else 0}">{run}</hp:p>'


def test_hwpx_text_tables_and_page_breaks() -> None:
    table = (
        "<hp:tbl><hp:tr>"
        "<hp:tc><hp:subList><hp:p><hp:run><hp:t>유형</hp:t></hp:run></hp:p></hp:subList></hp:tc>"
        "<hp:tc><hp:subList><hp:p><hp:run><hp:t>장점</hp:t></hp:run></hp:p></hp:subList></hp:tc>"
        "</hp:tr></hp:tbl>"
    )
    tab = "<hp:t>앞<hp:tab/>뒤</hp:t>"
    section = (
        para("과제 결과보고서")
        + f"<hp:p><hp:run>{table}</hp:run></hp:p>"
        + f"<hp:p><hp:run>{tab}</hp:run></hp:p>"
        + para("3. 수행 결과", page_break=True)
    )
    pages = extract_pages(make_hwpx(section), "hwpx")
    assert [(p.number, p.text) for p in pages] == [
        (1, "과제 결과보고서\n유형 | 장점\n앞\t뒤"),
        (2, "3. 수행 결과"),
    ]


async def test_hwpx_picture_is_read() -> None:
    picture = '<hp:pic><hc:img binaryItemIDRef="image1"/></hp:pic>'
    data = make_hwpx(
        para("결과물 사진", inner=picture),
        {"BinData/image1.png": image_bytes((400, 200), color="gray")},
    )
    pages = await read_material(data, "hwpx", ocr(FakeEngine("로그인 화면")))
    assert pages[0].text == "결과물 사진\n\n로그인 화면"


def test_hwpx_zip_bomb_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.ingest.package.MAX_UNZIPPED_BYTES", 10)
    with pytest.raises(IngestError) as error:
        extract_pages(make_hwpx(para("크게 풀리는 문서")), "hwpx")
    assert error.value.code == FailureCode.FILE_TOO_LARGE
    assert MAX_UNZIPPED_BYTES > 50 * 1024 * 1024  # 실제 상한은 업로드 상한보다 넉넉하다


# --- HWP (한컴 공개 규격의 레코드를 직접 만들어 시험) -----------------------------


def record(tag: int, payload: bytes, level: int = 0) -> bytes:
    return struct.pack("<I", tag | (level << 10) | (len(payload) << 20)) + payload


def para_header(page_break: bool = False) -> bytes:
    payload = bytearray(22)
    payload[11] = 0x04 if page_break else 0
    return record(PARA_HEADER, bytes(payload))


def text_record(text: str) -> bytes:
    return record(PARA_TEXT, (text + "\r").encode("utf-16-le"), level=1)


def picture_record(bin_id: int) -> bytes:
    payload = bytearray(91)
    struct.pack_into("<H", payload, 71, bin_id)
    return record(SHAPE_COMPONENT_PICTURE, bytes(payload), level=3)


def test_hwp_para_text_drops_controls_and_keeps_tabs() -> None:
    table_control = [11] + [0] * 7  # 확장 제어(표)는 8글자를 차지한다
    units = [ord(c) for c in "앞"] + [9] + [0] * 7 + [ord("뒤")] + table_control + [10, 0xAC00, 13]
    assert para_text(struct.pack(f"<{len(units)}H", *units)) == "앞\t뒤\n가"


def test_hwp_records_with_long_size() -> None:
    payload = b"x" * 5000
    data = struct.pack("<II", PARA_TEXT | (0xFFF << 20), len(payload)) + payload
    assert [(t, len(p)) for t, _, p in records(data)] == [(PARA_TEXT, 5000)]


class FakeOle:
    """olefile.OleFileIO 대역 (HWP 파일은 한컴 프로그램 없이 만들 수 없다)."""

    def __init__(self, streams: dict[str, bytes]) -> None:
        self.streams = streams

    def exists(self, name: str) -> bool:
        return name in self.streams

    def listdir(self) -> list[list[str]]:
        return [name.split("/") for name in self.streams]

    def openstream(self, name: str) -> io.BytesIO:
        return io.BytesIO(self.streams[name])


def deflate(data: bytes) -> bytes:
    compressor = zlib.compressobj(wbits=-15)
    return compressor.compress(data) + compressor.flush()


def hwp_file(monkeypatch: pytest.MonkeyPatch, flags: int, section: bytes, png: bytes) -> bytes:
    header = (
        b"HWP Document File".ljust(32, b"\x00") + b"\x00\x01\x01\x05" + struct.pack("<I", flags)
    )
    streams = {
        "FileHeader": header.ljust(256, b"\x00"),
        "BodyText/Section0": deflate(section) if flags & 1 else section,
        "BinData/BIN0001.png": png,
    }
    monkeypatch.setattr(hwp_module.olefile, "OleFileIO", lambda _data: FakeOle(streams))
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504


async def test_hwp_pages_text_and_pictures(monkeypatch: pytest.MonkeyPatch) -> None:
    section = (
        para_header()
        + text_record("캡스톤디자인 과제 결과보고서")
        + para_header(page_break=True)
        + text_record("4. 결과물 사진")
        + picture_record(1)
    )
    data = hwp_file(monkeypatch, 0x1, section, image_bytes((400, 200), color="gray"))
    pages = await read_material(data, "hwp", ocr(FakeEngine("회원가입 화면")))
    assert [(p.number, p.text) for p in pages] == [
        (1, "캡스톤디자인 과제 결과보고서"),
        (2, "4. 결과물 사진\n\n회원가입 화면"),
    ]


@pytest.mark.parametrize("flags", [0x2, 0x4])  # 암호, 배포용 문서
def test_hwp_locked_documents_are_corrupted(monkeypatch: pytest.MonkeyPatch, flags: int) -> None:
    data = hwp_file(monkeypatch, flags, para_header() + text_record("비밀"), b"")
    with pytest.raises(IngestError) as error:
        extract_pages(data, "hwp")
    assert error.value.code == FailureCode.CORRUPTED_FILE


def test_hwp_rejects_non_ole_files() -> None:
    with pytest.raises(IngestError) as error:
        extract_pages("한글 파일인 척하는 글".encode(), "hwp")
    assert error.value.code == FailureCode.UNSUPPORTED_FORMAT


# --- 위·아래 첨자 ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "script", "expected"),
    [
        ("12", "super", "¹²"),
        ("-1", "super", "⁻¹"),
        ("2", "sub", "₂"),
        (" n ", "super", " ⁿ "),  # 앞뒤 공백은 그대로
        ("k", "super", "^k"),  # 유니코드 첨자가 없는 글자
        ("min", "sub", "_(min)"),  # i는 아래 첨자가 없다
    ],
)
def test_scripted(text: str, script: Script, expected: str) -> None:
    assert scripted(text, script) == expected


def test_docx_keeps_superscript_and_subscript() -> None:
    document: Any = Document()
    paragraph = document.add_paragraph("4KB = 2")
    paragraph.add_run("1").font.superscript = True
    paragraph.add_run("2").font.superscript = True  # 나뉜 첨자 글자 묶음도 이어 붙인다
    paragraph.add_run(" B, log")
    paragraph.add_run("2").font.subscript = True
    paragraph.add_run("256")
    out = io.BytesIO()
    document.save(out)
    assert extract_pages(out.getvalue(), "docx")[0].text == "4KB = 2¹² B, log₂256"


def test_hwpx_keeps_superscript_from_char_shape() -> None:
    header = (
        '<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"><hh:charProperties>'
        '<hh:charPr id="0"/><hh:charPr id="7"><hh:supscript/></hh:charPr>'
        '<hh:charPr id="8"><hh:subscript/></hh:charPr></hh:charProperties></hh:head>'
    )
    section = (
        '<hp:p><hp:run charPrIDRef="0"><hp:t>2</hp:t></hp:run>'
        '<hp:run charPrIDRef="7"><hp:t>10</hp:t></hp:run>'
        '<hp:run charPrIDRef="0"><hp:t> = 1024, P</hp:t></hp:run>'
        '<hp:run charPrIDRef="8"><hp:t>1</hp:t></hp:run></hp:p>'
    )
    data = make_hwpx(section, {"Contents/header.xml": header.encode()})
    assert extract_pages(data, "hwpx")[0].text == "2¹⁰ = 1024, P₁"


# --- 그림 글자는 그림이 있던 문단 바로 뒤에 ------------------------------------


async def test_docx_picture_text_follows_its_paragraph() -> None:
    document: Any = Document()
    document.add_paragraph("터미널에서 ls를 실행한다.")
    document.add_picture(io.BytesIO(image_bytes((400, 200), color="gray")), width=Inches(3))
    document.add_paragraph("다음으로 권한을 바꾼다.")
    out = io.BytesIO()
    document.save(out)
    pages = await read_material(out.getvalue(), "docx", ocr(FakeEngine("user@ubuntu:~$ ls")))
    assert pages[0].text == (
        "터미널에서 ls를 실행한다.\n\nuser@ubuntu:~$ ls\n\n다음으로 권한을 바꾼다."
    )


async def test_hwpx_picture_text_follows_its_paragraph() -> None:
    picture = '<hp:pic><hc:img binaryItemIDRef="image1"/></hp:pic>'
    data = make_hwpx(
        para("실행 화면", inner=picture) + para("설명을 마친다."),
        {"BinData/image1.png": image_bytes((400, 200), color="gray")},
    )
    pages = await read_material(data, "hwpx", ocr(FakeEngine("로그인 화면")))
    assert pages[0].text == "실행 화면\n\n로그인 화면\n\n설명을 마친다."


async def test_hwp_picture_text_follows_its_paragraph(monkeypatch: pytest.MonkeyPatch) -> None:
    section = (
        para_header()
        + text_record("결과물 사진")
        + picture_record(1)
        + picture_record(9)  # 없는 그림 번호는 건너뛰고 순서는 지킨다
        + para_header()
        + text_record("이상으로 마친다.")
    )
    data = hwp_file(monkeypatch, 0x1, section, image_bytes((400, 200), color="gray"))
    engine = FakeEngine("회원가입 화면")
    pages = await read_material(data, "hwp", ocr(engine))
    assert pages[0].text == "결과물 사진\n\n회원가입 화면\n\n이상으로 마친다."
    assert len(engine.sizes) == 1


# --- 긴 글 문서는 구역으로 나눈다 ---------------------------------------------


def _long_text(headings: int, body_lines: int) -> str:
    blocks = []
    for n in range(1, headings + 1):
        body = "\n".join(f"{n}장 본문 문장 {i} " + "가" * 40 for i in range(body_lines))
        blocks.append(f"{n}. 제목 {n}\n{body}")
    return "\n".join(blocks)


def test_long_txt_is_split_at_headings() -> None:
    text = _long_text(headings=6, body_lines=30)  # 제목마다 약 1,500자
    pages = extract_pages(text.encode(), "txt")
    assert len(pages) > 1
    assert [p.number for p in pages] == list(range(1, len(pages) + 1))
    assert all(p.text.startswith(f"{p.text.split('.')[0]}. 제목") for p in pages)
    assert "\n".join(p.text for p in pages) == text  # 글자는 하나도 잃지 않는다


def test_long_text_without_headings_is_split_at_lines() -> None:
    text = "\n".join("제목 없는 긴 줄 " + "나" * 60 for _ in range(200))
    pages = split_sections([PageText(1, text)])
    assert len(pages) > 1
    assert all(len(p.text) <= SECTION_CHARS * 2 for p in pages)
    assert "\n".join(p.text for p in pages) == text


def test_short_document_and_real_pages_are_not_split() -> None:
    assert extract_pages("짧은 메모\n1. 항목".encode(), "txt") == [
        PageText(1, "짧은 메모\n1. 항목")
    ]
    assert has_real_pages("pdf") and has_real_pages("pptx") and not has_real_pages("docx")


def test_sections_never_exceed_page_limit() -> None:
    pages = [PageText(n, "\n".join("줄 " + "다" * 50 for _ in range(300))) for n in range(1, 11)]
    assert len(split_sections(pages)) <= MAX_PAGES
