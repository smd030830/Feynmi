"""PDF/PPTX 파싱 → split_pages → embed_chunks 연결 (PRD FR-1.2, FR-1.4, FR-5.1)."""

import io
import zipfile
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from pptx import Presentation
from pptx.presentation import Presentation as PresentationFile
from pptx.util import Inches
from pypdf import PdfReader, PdfWriter

from backend.domain.enums import FailureCode
from backend.ingest import (
    MAX_FILE_BYTES,
    MAX_PAGES,
    IngestError,
    extract_pages,
    extract_pdf_pages,
    extract_pptx_pages,
)
from backend.llm import LLMProvider
from backend.rag.chunking import PageText, split_pages
from backend.rag.config import RAGSettings
from backend.rag.store import embed_chunks

# --- 테스트 자료 생성 ---------------------------------------------------------


Run = tuple[float, float, str]  # 글자 묶음을 놓을 위치(x, y)와 글자


def make_pdf(pages: list[str]) -> bytes:
    """쪽마다 주어진 텍스트를 가진 텍스트 PDF. 빈 문자열은 텍스트 없는 쪽이 된다.

    한글을 추출할 수 있도록 글자별 ToUnicode 매핑을 넣는다(글꼴 파일은 넣지 않음).
    """
    return make_placed_pdf(
        [
            [(50, 750 - 20 * j, line) for j, line in enumerate(text.split("\n")) if line]
            for text in pages
        ]
    )


def make_placed_pdf(pages: list[list[Run]]) -> bytes:
    """글자 묶음을 정한 자리에 놓는다. 공백 글자 없이 간격만 둔 띄어쓰기, 2단 배치를 만들 때 쓴다.

    글자 하나의 폭은 글자 크기(12pt)와 같다(/DW 1000).
    """
    chars = sorted({c for runs in pages for _, _, text in runs for c in text})
    code = {c: i + 1 for i, c in enumerate(chars)}
    entries = [f"<{code[c]:04X}> <{c.encode('utf-16-be').hex().upper()}>" for c in chars]
    blocks = [entries[i : i + 100] for i in range(0, len(entries), 100)]
    cmap = (
        "/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
        "/CMapName /Test-UTF16 def /CMapType 2 def\n"
        "1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
        + "".join(f"{len(b)} beginbfchar\n" + "\n".join(b) + "\nendbfchar\n" for b in blocks)
        + "endcmap CMapName currentdict /CMap defineresource pop end end\n"
    ).encode()
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type0 /BaseFont /Test /Encoding /Identity-H "
        b"/DescendantFonts [<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Test "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        b"/DW 1000 >>] /ToUnicode 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(cmap) + cmap + b"\nendstream",
    ]
    for i, runs in enumerate(pages):
        content = "\n".join(
            f"BT /F1 12 Tf {x} {y} Td <{''.join(f'{code[c]:04X}' for c in text)}> Tj ET"
            for x, y, text in runs
        ).encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {6 + 2 * i} 0 R >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
    out = io.BytesIO()
    out.write(b"%PDF-1.7\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    )
    return out.getvalue()


def encrypt_pdf(data: bytes, user_password: str) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    writer.encrypt(user_password=user_password, owner_password="owner")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def save_pptx(presentation: PresentationFile) -> bytes:
    out = io.BytesIO()
    presentation.save(out)
    return out.getvalue()


def make_pptx(slides: list[str]) -> bytes:
    """슬라이드마다 텍스트 상자 하나. 빈 문자열은 빈 슬라이드가 된다."""
    presentation = Presentation()
    blank = presentation.slide_layouts[6]
    for text in slides:
        slide = presentation.slides.add_slide(blank)
        if text:
            box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(3))
            box.text_frame.text = text
    return save_pptx(presentation)


def png() -> io.BytesIO:
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(out, format="PNG")
    out.seek(0)
    return out


def code_of(error: pytest.ExceptionInfo[IngestError]) -> FailureCode:
    return error.value.code


# --- PDF --------------------------------------------------------------------


def test_pdf_keeps_korean_symbols_and_page_numbers_with_empty_page() -> None:
    data = make_pdf(["운영체제 1장: 프로세스\nO(n log n) ≤ ∑ α", "", "3쪽 English mix"])
    pages = extract_pdf_pages(data)
    assert [p.number for p in pages] == [1, 2, 3]
    assert pages[0].text == "운영체제 1장: 프로세스\nO(n log n) ≤ ∑ α"
    assert pages[1].text == ""
    assert pages[2].text == "3쪽 English mix"


def test_pdf_spaces_stored_as_gaps_are_restored() -> None:
    # 실제 강의 PDF: 띄어쓰기가 공백 글자 없이 글자 간격으로만 들어 있었다
    # ("적절한권한을가진…"으로 붙어 나오던 문제)
    words = ["적절한", "권한을", "가진", "인가자만이"]
    runs: list[Run] = []
    x = 50.0
    for word in words:
        runs.append((x, 700, word))
        x += 12 * len(word) + 6  # 반 글자 간격
    assert extract_pdf_pages(make_placed_pdf([runs]))[0].text == "적절한 권한을 가진 인가자만이"


def test_pdf_two_columns_are_read_column_by_column() -> None:
    left: list[Run] = [(50.0, 700 - 20 * i, f"왼쪽 단 {i}번째 줄") for i in range(1, 4)]
    right: list[Run] = [(330.0, 700 - 20 * i, f"오른쪽 단 {i}번째 줄") for i in range(1, 4)]
    text = extract_pdf_pages(make_placed_pdf([left + right]))[0].text
    assert text.splitlines() == [t for _, _, t in left + right]


def test_pdf_private_use_symbols_are_dropped() -> None:
    # 장식 글꼴의 기호가 글꼴 전용 영역(U+F000 등)으로 나오던 문제 (대회 공고 PDF)
    text = extract_pdf_pages(make_pdf([" 1. 참가 안내"]))[0].text
    assert text == "1. 참가 안내"


def test_pdf_without_text_is_no_extractable_text() -> None:
    with pytest.raises(IngestError) as error:
        extract_pdf_pages(make_pdf(["", ""]))
    assert code_of(error) == FailureCode.NO_EXTRACTABLE_TEXT


def test_pdf_page_limit() -> None:
    assert len(extract_pdf_pages(make_pdf(["내용"] + [""] * (MAX_PAGES - 1)))) == MAX_PAGES
    with pytest.raises(IngestError) as error:
        extract_pdf_pages(make_pdf(["내용"] + [""] * MAX_PAGES))
    assert code_of(error) == FailureCode.TOO_MANY_PAGES


def test_pdf_owner_only_encryption_is_readable() -> None:
    pages = extract_pdf_pages(encrypt_pdf(make_pdf(["권한만 제한"]), user_password=""))
    assert pages == [PageText(1, "권한만 제한")]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"not a pdf at all", FailureCode.UNSUPPORTED_FORMAT),
        (b"%PDF-1.7\n garbage without objects", FailureCode.CORRUPTED_FILE),
        (encrypt_pdf(make_pdf(["비밀"]), user_password="secret"), FailureCode.CORRUPTED_FILE),
        (b"%PDF-" + b"\0" * MAX_FILE_BYTES, FailureCode.FILE_TOO_LARGE),
    ],
    ids=["not-pdf", "corrupted", "password", "too-large"],
)
def test_pdf_failures(data: bytes, expected: FailureCode) -> None:
    with pytest.raises(IngestError) as error:
        extract_pdf_pages(data)
    assert code_of(error) == expected


def test_pdf_truncated_file_is_corrupted() -> None:
    data = make_pdf(["잘린 파일"])
    with pytest.raises(IngestError) as error:
        extract_pdf_pages(data[: len(data) // 3])
    assert code_of(error) == FailureCode.CORRUPTED_FILE


# --- PPTX -------------------------------------------------------------------


def test_pptx_keeps_slide_numbers_line_breaks_and_empty_slide() -> None:
    pages = extract_pptx_pages(make_pptx(["첫 슬라이드\n둘째 줄", "", "세 번째"]))
    assert pages == [PageText(1, "첫 슬라이드\n둘째 줄"), PageText(2, ""), PageText(3, "세 번째")]


def test_pptx_reads_title_table_group_and_soft_break_in_shape_order() -> None:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])  # 제목만
    assert slide.shapes.title is not None
    slide.shapes.title.text = "스케줄링"
    table = slide.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(4), Inches(1)).table
    table.cell(0, 0).text = "알고리즘"
    table.cell(0, 1).text = "특징"
    table.cell(1, 0).text = "RR"
    table.cell(1, 1).text = "시간 할당량"
    group = slide.shapes.add_group_shape()
    box = group.shapes.add_textbox(Inches(1), Inches(4), Inches(4), Inches(1))
    paragraph = box.text_frame.paragraphs[0]
    paragraph.add_run().text = "그룹 안"
    paragraph.add_line_break()
    paragraph.add_run().text = "줄바꿈"
    slide.shapes.add_picture(png(), Inches(6), Inches(1))
    pages = extract_pptx_pages(save_pptx(presentation))
    assert pages == [PageText(1, "스케줄링\n알고리즘 | 특징\nRR | 시간 할당량\n그룹 안\n줄바꿈")]


def test_pptx_with_only_images_is_no_extractable_text() -> None:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_picture(png(), Inches(1), Inches(1))
    with pytest.raises(IngestError) as error:
        extract_pptx_pages(save_pptx(presentation))
    assert code_of(error) == FailureCode.NO_EXTRACTABLE_TEXT


def test_pptx_slide_limit() -> None:
    assert len(extract_pptx_pages(make_pptx(["내용"] + [""] * (MAX_PAGES - 1)))) == MAX_PAGES
    with pytest.raises(IngestError) as error:
        extract_pptx_pages(make_pptx(["내용"] + [""] * MAX_PAGES))
    assert code_of(error) == FailureCode.TOO_MANY_PAGES


def plain_zip() -> bytes:
    """PowerPoint 본문(ppt/presentation.xml)이 없는 그냥 압축 파일."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("readme.txt", "hello")
    return out.getvalue()


def docx_like_zip() -> bytes:
    """PowerPoint가 아닌 OOXML 패키지(워드 문서 형태)."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as package:
        package.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/'
            '2006/content-types"><Default Extension="rels" ContentType="application/'
            'vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/'
            'document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document.main+xml"/></Types>',
        )
        package.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
            'openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>',
        )
        package.writestr("word/document.xml", "<w:document/>")
    return out.getvalue()


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 64, FailureCode.UNSUPPORTED_FORMAT),
        (docx_like_zip(), FailureCode.UNSUPPORTED_FORMAT),
        (plain_zip(), FailureCode.UNSUPPORTED_FORMAT),
        (make_pptx(["잘림"])[:200], FailureCode.CORRUPTED_FILE),
        (b"PK\x03\x04" + b"\0" * MAX_FILE_BYTES, FailureCode.FILE_TOO_LARGE),
    ],
    ids=["legacy-ppt", "docx", "plain-zip", "truncated", "too-large"],
)
def test_pptx_failures(data: bytes, expected: FailureCode) -> None:
    with pytest.raises(IngestError) as error:
        extract_pptx_pages(data)
    assert code_of(error) == expected


# --- 형식 선택과 RAG 연결 -----------------------------------------------------


def test_extract_pages_dispatches_by_file_type_and_does_not_trust_it() -> None:
    assert extract_pages(make_pdf(["PDF 본문"]), "pdf") == [PageText(1, "PDF 본문")]
    assert extract_pages(make_pptx(["PPTX 본문"]), "pptx") == [PageText(1, "PPTX 본문")]
    for data, file_type in [(make_pptx(["x"]), "pdf"), (make_pdf(["x"]), "pptx"), (b"x", "docx")]:
        with pytest.raises(IngestError) as error:
            extract_pages(data, file_type)
        assert code_of(error) == FailureCode.UNSUPPORTED_FORMAT


def fake_provider() -> AsyncMock:
    """입력 순서대로 서로 다른 1536차원 벡터를 돌려준다."""
    provider = AsyncMock(spec=LLMProvider)

    async def embed(texts: list[str]) -> list[list[float]]:
        return [[float(i + 1)] + [0.0] * 1535 for i in range(len(texts))]

    provider.embed.side_effect = embed
    return provider


async def test_parsed_pages_flow_into_chunks_and_embeddings() -> None:
    long_slide = "프로세스는 실행 중인 프로그램이다. " * 300  # 여러 청크로 나뉘는 분량
    pages = extract_pages(make_pptx(["개요", "", long_slide.strip()]), "pptx")
    chunks = split_pages(pages, settings=RAGSettings())
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert chunks[0].page_start == chunks[0].page_end == 1
    assert len(chunks) > 2
    # 빈 2번 슬라이드를 건너뛰어도 실제 슬라이드 번호 3을 유지한다.
    assert {(c.page_start, c.page_end) for c in chunks[1:]} == {(3, 3)}
    assert all(0 < c.token_count <= 800 for c in chunks)

    embedded = await embed_chunks(chunks, fake_provider())
    assert [e.chunk for e in embedded] == chunks
    assert all(len(e.embedding) == 1536 for e in embedded)
    assert [e.embedding[0] for e in embedded] == [float(i + 1) for i in range(len(chunks))]
