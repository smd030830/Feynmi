"""OCR 엔진과 '애매함' 판단. 진짜 Tesseract 검사는 설치된 PC/CI에서만 돈다."""

import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from backend.ingest.config import OCRSettings
from backend.ingest.ocr import (
    HybridOcr,
    OcrOutcome,
    OcrResult,
    OcrUnavailableError,
    TesseractEngine,
    clean_text,
    doubt_reason,
    garbage_ratio,
    is_ocr_target,
    odd_token_ratio,
    prepare,
    word_confidence,
)
from backend.llm import LLMError

# 기준값은 기본값으로 고정하고, Tesseract 경로만 .env(TESSERACT_CMD)를 따른다
SETTINGS = OCRSettings(_env_file=None, tesseract_cmd=OCRSettings().tesseract_cmd)  # pyright: ignore[reportCallIssue]


def tesseract_ready() -> bool:
    try:
        TesseractEngine(SETTINGS).check()
    except OcrUnavailableError:
        return False
    return True


needs_tesseract = pytest.mark.skipif(not tesseract_ready(), reason="Tesseract 미설치")

_KOREAN_FONTS = [
    Path("C:/Windows/Fonts/malgun.ttf"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
]


def text_image(lines: list[str], font_path: Path | None = None) -> Image.Image:
    font = ImageFont.truetype(str(font_path), 48) if font_path else ImageFont.load_default(size=48)
    image = Image.new("RGB", (1400, 90 * len(lines) + 60), "white")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text((40, 30 + 90 * i), line, fill="black", font=font)
    return image


# --- 애매함 판단 (Tesseract 없이 검사) ---


def test_clear_result_is_trusted() -> None:
    result = OcrResult("프로세스는 실행 중인 프로그램이다", confidence=91.0)
    assert doubt_reason(result, (1200, 800), SETTINGS) is None


@pytest.mark.parametrize(
    ("result", "size", "reason"),
    [
        (OcrResult("프로세스", confidence=42.0), (400, 300), "low confidence 42"),
        (OcrResult("", confidence=None), (1024, 1425), "large image with little text"),
        (OcrResult("a b", confidence=95.0), (1024, 1425), "large image with little text"),
        (OcrResult("§¶ª¤ ¦¨ ©®", confidence=88.0), (400, 300), "many unknown symbols"),
    ],
)
def test_doubtful_results(result: OcrResult, size: tuple[int, int], reason: str) -> None:
    assert doubt_reason(result, size, SETTINGS) == reason


def test_small_image_with_no_text_is_not_doubtful() -> None:
    # 작은 그림에 글자가 없는 건 자연스럽다 (AI를 부를 이유가 없다)
    assert doubt_reason(OcrResult("", None), (300, 200), SETTINGS) is None


def test_thresholds_come_from_settings() -> None:
    strict = SETTINGS.model_copy(update={"ocr_min_confidence": 95})
    assert doubt_reason(OcrResult("본문", 91.0), (400, 300), strict) == "low confidence 91"


def test_garbage_ratio_counts_korean_and_bullets_as_normal() -> None:
    assert garbage_ratio("① 프로세스 → 스레드 (CPU 100%)") == 0.0
    assert garbage_ratio("") == 0.0
    assert garbage_ratio("ab§¶") == 0.5


def test_tiny_images_are_skipped() -> None:
    assert not is_ocr_target((60, 60), SETTINGS)  # 아이콘
    assert not is_ocr_target((1200, 40), SETTINGS)  # 가는 선
    assert is_ocr_target((1024, 1425), SETTINGS)  # 포스터


def test_word_confidence_from_tesseract_table() -> None:
    rows = [
        ["level", "left", "conf", "text"],
        ["1", "0", "-1", ""],  # 덩어리 행 (단어 아님)
        ["5", "0", "90", "운영체제"],
        ["5", "9", "80", "3강"],
        ["5", "0", "70", "프로세스"],
        ["5", "0", "10", "~"],
        ["5", "0", "95", " "],  # 빈 단어는 세지 않는다
    ]
    tsv = "\n".join("\t".join(row) for row in rows)
    confidence, weak = word_confidence(tsv)
    assert confidence == pytest.approx((90 + 80 + 70 + 10) / 4)
    assert weak == 0.25
    assert word_confidence("level\tconf\ttext\n") == (None, 0.0)
    assert word_confidence("") == (None, 0.0)


def test_clean_text_drops_blank_lines_and_double_spaces() -> None:
    assert clean_text("운영체제  프로세스\n\n\n선점형 \r\n\n") == "운영체제 프로세스\n선점형"


def test_many_unsure_words_are_doubtful() -> None:
    result = OcrResult("운영체제 rz 스케줄링 fi", confidence=75.0, weak_ratio=0.5)
    assert doubt_reason(result, (400, 300), SETTINGS) == "many unsure words 50%"


@pytest.mark.parametrize(
    "text",
    [
        # 진짜 Tesseract가 높은 점수(90)로 내놓은 오답: "문맥 교환(Context Switch)에는 비용이 든다."
        "프로세스는 실행 단위이다\n문맥 교환(20016×【 5\\/|[1)에는 비용이 든다.",
        # "선점형: RR, SRTF / 비선점형: FCFS, SJF" 캡처를 줄이 엉켜 읽은 결과 (점수 81)
        "형\n=\n선점\n> RR, SRTF\n> FCFS, SJF\nof\n=\n비선점",
    ],
)
def test_confident_but_garbled_results_are_doubtful(text: str) -> None:
    result = OcrResult(text, confidence=88.0, weak_ratio=0.05)
    assert (doubt_reason(result, (880, 368), SETTINGS) or "").startswith("many odd tokens")


def test_bullets_and_normal_symbols_are_not_odd() -> None:
    text = "① 대회 안내\n- 결과보고서 (필수)\n▶ 금상 : 1팀 ※ 마감 2026. 11. 12.(목) 24:00 / 50%"
    assert odd_token_ratio(text) == 0.0
    result = OcrResult(text, confidence=90.0)
    assert doubt_reason(result, (880, 368), SETTINGS) is None


def test_prepare_flattens_transparency_and_upscales_small_images() -> None:
    transparent = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    prepared = prepare(transparent)
    assert prepared.mode == "L"
    assert prepared.size == (400, 200)
    assert prepared.getpixel((0, 0)) == 255  # 투명 → 흰 배경
    assert prepare(Image.new("RGB", (1600, 900))).size == (1600, 900)


def test_missing_tesseract_is_reported() -> None:
    engine = TesseractEngine(
        SETTINGS.model_copy(update={"tesseract_cmd": "C:/없는/경로/tesseract.exe"})
    )
    with pytest.raises(OcrUnavailableError):
        engine.check()
    with pytest.raises(OcrUnavailableError):
        engine.read(Image.new("RGB", (200, 200), "white"))


# --- 진짜 Tesseract ---


@needs_tesseract
def test_tesseract_reads_english() -> None:
    result = TesseractEngine(SETTINGS).read(text_image(["Process Scheduling 2026"]))
    assert "Process" in result.text and "2026" in result.text
    assert result.confidence is not None and result.confidence > 60


@needs_tesseract
@pytest.mark.skipif(
    not any(p.exists() for p in _KOREAN_FONTS), reason="한글 글꼴 없음 (테스트 그림을 못 만듦)"
)
def test_tesseract_reads_korean() -> None:
    font = next(p for p in _KOREAN_FONTS if p.exists())
    image = text_image(["운영체제 프로세스와 스레드", "선점형 스케줄링"], font)
    result = TesseractEngine(SETTINGS).read(image)
    assert "프로세스" in result.text and "스케줄링" in result.text
    assert doubt_reason(result, image.size, SETTINGS) is None


@needs_tesseract
def test_blank_image_reads_nothing() -> None:
    result = TesseractEngine(SETTINGS).read(Image.new("RGB", (800, 600), "white"))
    assert result.text == ""


# --- 하이브리드: Tesseract 먼저, 애매하면 AI (가짜 엔진·가짜 AI) ---


class FakeEngine:
    def __init__(self, result: OcrResult) -> None:
        self.result = result

    def read(self, image: Image.Image) -> OcrResult:
        return self.result


class FakeAI:
    def __init__(self, text: str = "AI가 읽은 글자", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[tuple[bytes, str]] = []

    async def read_image_text(self, image: bytes, mime_type: str) -> str:
        self.calls.append((image, mime_type))
        if self.error:
            raise self.error
        return self.text


CLEAR = OcrResult("프로세스와 스레드", confidence=92.0)
BLURRY = OcrResult("프로세 스와", confidence=35.0)
SLIDE_IMAGE = Image.new("RGB", (800, 400), "white")  # 큰 그림 기준(50만 화소) 미만


async def test_clear_result_never_calls_ai() -> None:
    ai = FakeAI()
    outcome = await HybridOcr(FakeEngine(CLEAR), SETTINGS, ai).read(SLIDE_IMAGE)
    assert outcome == OcrOutcome("프로세스와 스레드", "tesseract", None)
    assert ai.calls == []


async def test_doubtful_result_is_reread_by_ai_as_png() -> None:
    ai = FakeAI(" 프로세스와 스레드 \r\n")
    outcome = await HybridOcr(FakeEngine(BLURRY), SETTINGS, ai).read(SLIDE_IMAGE)
    assert outcome == OcrOutcome("프로세스와 스레드", "ai", "low confidence 35")
    [(png, mime)] = ai.calls
    assert mime == "image/png" and png.startswith(b"\x89PNG")


async def test_large_images_are_shrunk_before_sending_to_ai() -> None:
    ai = FakeAI()
    await HybridOcr(FakeEngine(BLURRY), SETTINGS, ai).read(Image.new("RGB", (6000, 3000)))
    sent = Image.open(io.BytesIO(ai.calls[0][0]))
    assert max(sent.size) == 2048


SHAKY = OcrResult("프로세 스와", confidence=50.0)  # 애매하지만 버릴 정도는 아님


async def test_without_ai_a_shaky_tesseract_result_is_kept() -> None:
    outcome = await HybridOcr(FakeEngine(SHAKY), SETTINGS, None).read(SLIDE_IMAGE)
    assert outcome == OcrOutcome("프로세 스와", "tesseract", "low confidence 50")


async def test_without_ai_a_nearly_all_wrong_result_is_dropped() -> None:
    # 직인처럼 신뢰도 40 미만이면 쓰레기 글자를 남기지 않는다
    seal = OcrResult("내민[거906\nHoe\n리그레이여", confidence=35.0)
    outcome = await HybridOcr(FakeEngine(seal), SETTINGS, None).read(SLIDE_IMAGE)
    assert outcome == OcrOutcome("", "tesseract", "low confidence 35")


@pytest.mark.parametrize("error", [LLMError("down"), ValueError("bad output")])
async def test_ai_failure_falls_back_to_tesseract(error: Exception) -> None:
    outcome = await HybridOcr(FakeEngine(SHAKY), SETTINGS, FakeAI(error=error)).read(SLIDE_IMAGE)
    assert (outcome.text, outcome.source) == ("프로세 스와", "tesseract")


async def test_ai_calls_are_capped_per_material() -> None:
    ai = FakeAI()
    ocr = HybridOcr(FakeEngine(BLURRY), SETTINGS.model_copy(update={"ocr_ai_max_calls": 2}), ai)
    sources = [(await ocr.read(SLIDE_IMAGE)).source for _ in range(4)]
    assert sources == ["ai", "ai", "tesseract", "tesseract"]
    assert len(ai.calls) == 2


async def test_zero_cap_disables_ai() -> None:
    ai = FakeAI()
    ocr = HybridOcr(FakeEngine(BLURRY), SETTINGS.model_copy(update={"ocr_ai_max_calls": 0}), ai)
    assert (await ocr.read(SLIDE_IMAGE)).source == "tesseract"
    assert ai.calls == []
