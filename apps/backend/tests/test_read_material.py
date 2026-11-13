"""그림 속 글자까지 읽기: PNG/JPG, 스캔 PDF, PDF·PPTX 속 그림 (가짜 OCR 엔진으로 검사)."""

import io
from collections.abc import Callable

import pytest
from PIL import Image
from pptx import Presentation
from pptx.util import Inches
from pypdf import PdfReader, PdfWriter
from test_ingest import make_pdf

from backend.domain.enums import FailureCode
from backend.ingest import IngestError, extract_pages, make_ocr, read_material
from backend.ingest.config import OCRSettings
from backend.ingest.image import try_decode
from backend.ingest.ocr import HybridOcr, OcrResult

SETTINGS = OCRSettings(_env_file=None)  # pyright: ignore[reportCallIssue]


class FakeEngine:
    """그림 크기를 기록하고, 정해 둔 글자를 돌려준다."""

    def __init__(self, reply: str | Callable[[Image.Image], str] = "그림 속 글자") -> None:
        self.reply = reply
        self.sizes: list[tuple[int, int]] = []

    def read(self, image: Image.Image) -> OcrResult:
        self.sizes.append(image.size)
        text = self.reply(image) if callable(self.reply) else self.reply
        return OcrResult(text, 95.0 if text else None)


def ocr(engine: FakeEngine, **settings: object) -> HybridOcr:
    return HybridOcr(engine, SETTINGS.model_copy(update=settings))


def image_bytes(size: tuple[int, int], fmt: str = "PNG", color: str = "white") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format=fmt)
    return out.getvalue()


def scanned_pdf(pages: int) -> bytes:
    images = [Image.new("RGB", (850, 1100), "white") for _ in range(pages)]
    out = io.BytesIO()
    images[0].save(out, format="PDF", save_all=True, append_images=images[1:], resolution=100)
    return out.getvalue()


def text_pdf_with_image() -> bytes:
    """1쪽: 글자 + 박힌 그림 (그림 쪽 위에 글자 쪽을 겹친다)."""
    writer = PdfWriter(clone_from=io.BytesIO(scanned_pdf(1)))
    writer.pages[0].merge_page(PdfReader(io.BytesIO(make_pdf(["운영체제 개요"]))).pages[0])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def pptx_with_pictures(title: str, pictures: list[tuple[int, int]], grouped: bool = False) -> bytes:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    if title:
        slide.shapes.add_textbox(
            Inches(1), Inches(0.5), Inches(6), Inches(1)
        ).text_frame.text = title
    target = slide.shapes.add_group_shape().shapes if grouped else slide.shapes
    for i, size in enumerate(pictures):
        target.add_picture(io.BytesIO(image_bytes(size)), Inches(1 + i), Inches(2))
    out = io.BytesIO()
    presentation.save(out)
    return out.getvalue()


# --- PNG/JPG 파일 ---


@pytest.mark.parametrize("fmt", ["PNG", "JPEG"])
async def test_image_file_is_one_page_read_by_ocr(fmt: str) -> None:
    engine = FakeEngine("프로세스 상태 전이도")
    pages = await read_material(image_bytes((640, 480), fmt), "png", ocr(engine))
    assert [(p.number, p.text) for p in pages] == [(1, "프로세스 상태 전이도")]
    assert engine.sizes == [(640, 480)]


async def test_small_uploaded_image_is_still_read() -> None:
    # 자료 속 아이콘과 달리 사용자가 올린 그림은 작아도 읽는다
    engine = FakeEngine("CPU")
    assert (await read_material(image_bytes((50, 50)), "jpg", ocr(engine)))[0].text == "CPU"


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"%PDF-1.7 not an image", FailureCode.UNSUPPORTED_FORMAT),
        (image_bytes((300, 300))[:60], FailureCode.CORRUPTED_FILE),
        (b"\x89PNG\r\n\x1a\n" + b"\0" * (50 * 1024 * 1024), FailureCode.FILE_TOO_LARGE),
    ],
    ids=["not-image", "truncated", "too-large"],
)
async def test_bad_image_files(data: bytes, code: FailureCode) -> None:
    with pytest.raises(IngestError) as caught:
        await read_material(data, "png", ocr(FakeEngine()))
    assert caught.value.code == code


async def test_decompression_bomb_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(IngestError) as caught:
        await read_material(image_bytes((100, 100)), "png", ocr(FakeEngine()))
    assert caught.value.code == FailureCode.FILE_TOO_LARGE


async def test_image_without_text_has_no_extractable_text() -> None:
    with pytest.raises(IngestError) as caught:
        await read_material(image_bytes((640, 480)), "png", ocr(FakeEngine("")))
    assert caught.value.code == FailureCode.NO_EXTRACTABLE_TEXT


async def test_image_file_needs_an_ocr_engine() -> None:
    with pytest.raises(IngestError) as caught:
        await read_material(image_bytes((640, 480)), "png", None)
    assert caught.value.code == FailureCode.INTERNAL_ERROR
    with pytest.raises(IngestError) as caught:
        extract_pages(image_bytes((640, 480)), "png")
    assert caught.value.code == FailureCode.INTERNAL_ERROR


# --- PDF ---


async def test_scanned_pdf_pages_are_rendered_and_read() -> None:
    engine = FakeEngine(lambda image: f"스캔 {len(engine.sizes)}쪽")
    pages = await read_material(scanned_pdf(2), "pdf", ocr(engine))
    assert [(p.number, p.text) for p in pages] == [(1, "스캔 1쪽"), (2, "스캔 2쪽")]
    # 8.5×11인치 쪽을 300dpi로 그린다 (반올림 1px 차이 허용)
    assert all(w == 2550 and h in (3300, 3301) for w, h in engine.sizes)
    assert len(engine.sizes) == 2


async def test_scanned_pdf_without_ocr_has_no_text() -> None:
    with pytest.raises(IngestError) as caught:
        await read_material(scanned_pdf(1), "pdf", None)
    assert caught.value.code == FailureCode.NO_EXTRACTABLE_TEXT


async def test_picture_inside_text_pdf_page_is_appended() -> None:
    engine = FakeEngine("포스터: 본선 11월 27일")
    pages = await read_material(text_pdf_with_image(), "pdf", ocr(engine))
    assert pages[0].text == "운영체제 개요\n\n포스터: 본선 11월 27일"
    assert engine.sizes == [(850, 1100)]  # 쪽을 그리지 않고 박힌 그림만 읽는다


async def test_plain_text_pdf_is_unchanged_with_ocr() -> None:
    engine = FakeEngine()
    pages = await read_material(make_pdf(["가나다", "라마바"]), "pdf", ocr(engine))
    assert [p.text for p in pages] == ["가나다", "라마바"]
    assert engine.sizes == []


# --- PPTX ---


async def test_slide_pictures_are_read_and_tiny_icons_skipped() -> None:
    engine = FakeEngine("선점형 | 비선점형")
    data = pptx_with_pictures("스케줄링", [(400, 300), (60, 60)])
    pages = await read_material(data, "pptx", ocr(engine))
    assert pages[0].text == "스케줄링\n\n선점형 | 비선점형"
    assert engine.sizes == [(400, 300)]


async def test_pictures_inside_groups_are_read() -> None:
    engine = FakeEngine("그룹 속 그림")
    pages = await read_material(
        pptx_with_pictures("", [(300, 200)], grouped=True), "pptx", ocr(engine)
    )
    assert pages[0].text == "그룹 속 그림"


async def test_text_already_on_the_slide_is_not_duplicated() -> None:
    engine = FakeEngine("운영체제 스케줄링 알고리즘")
    data = pptx_with_pictures("운영체제 스케줄링 알고리즘 정리", [(400, 300)])
    pages = await read_material(data, "pptx", ocr(engine))
    assert pages[0].text == "운영체제 스케줄링 알고리즘 정리"


async def test_image_count_is_capped_per_material() -> None:
    engine = FakeEngine(lambda image: f"그림{len(engine.sizes)}")
    data = pptx_with_pictures("제목", [(400, 300), (400, 300), (400, 300)])
    pages = await read_material(data, "pptx", ocr(engine, ocr_max_images=2))
    assert pages[0].text == "제목\n\n그림1\n\n그림2"


async def test_without_ocr_pictures_are_ignored() -> None:
    data = pptx_with_pictures("제목", [(400, 300)])
    pages = await read_material(data, "pptx", None)
    assert [p.text for p in pages] == ["제목"] == [p.text for p in extract_pages(data, "pptx")]


# --- 기타 ---


def test_unreadable_embedded_image_is_skipped() -> None:
    assert try_decode(b"not an image", "slide 1") is None


def test_make_ocr_returns_none_without_tesseract() -> None:
    missing = SETTINGS.model_copy(update={"tesseract_cmd": "C:/없는/경로/tesseract.exe"})
    assert make_ocr(settings=missing) is None


async def test_parsing_does_not_block_other_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """큰 자료를 읽는 동안에도 서버가 다른 요청(목록 새로고침 등)에 답할 수 있어야 한다."""
    import asyncio
    import time

    import backend.ingest as ingest

    original = ingest._raw_pages

    def slow_raw_pages(data: bytes, file_type: str):  # noqa: ANN202
        time.sleep(0.5)  # 무거운 파싱 흉내 (작업 줄을 막는 동기 작업)
        return original(data, file_type)

    monkeypatch.setattr(ingest, "_raw_pages", slow_raw_pages)
    first_tick: float | None = None
    started = time.perf_counter()

    async def other_requests() -> None:
        nonlocal first_tick
        await asyncio.sleep(0.05)
        first_tick = time.perf_counter() - started

    await asyncio.gather(read_material(make_pdf(["본문"]), "pdf", None), other_requests())
    # 파싱이 주 작업 줄을 막았다면 다른 요청은 0.5초 뒤에야 처리됐을 것이다
    assert first_tick is not None and first_tick < 0.3
