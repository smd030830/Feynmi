"""이미지 글자 인식(OCR). 기본 엔진은 Tesseract이고, 결과가 애매한지 스스로 판단한다.

애매한 결과를 AI로 다시 읽을지는 호출하는 쪽(수집 파이프라인)이 정한다.
"""

import asyncio
import io
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import pytesseract
from PIL import Image, ImageOps

from backend.ingest.base import normalize_text
from backend.ingest.config import OCRSettings
from backend.llm import LLMError

logger = logging.getLogger(__name__)

# AI에 보낼 그림의 긴 변 상한 (비용과 전송량 보호)
_AI_MAX_SIDE = 2048

# Tesseract가 잘 읽는 글자 높이를 맞추기 위해, 긴 변이 이보다 작으면 2배로 키운다
_UPSCALE_BELOW = 1000
# 이 신뢰도 미만인 단어를 "자신 없는 단어"로 센다
_WEAK_WORD = 60
# 페이지 구성 분석(다단 지원)으로 먼저 읽고, 자신 없는 단어가 섞이면 한 덩어리 글로 다시 읽어 본다.
# 슬라이드처럼 줄 간격이 넓은 그림에서 기본 모드는 줄을 쪼개 엉뚱한 글자를 만들기 쉽다.
_LAYOUT_PSM = "--psm 3"
_BLOCK_PSM = "--psm 6"


@dataclass(frozen=True)
class OcrResult:
    text: str
    # 단어 평균 신뢰도(0~100). 읽힌 단어가 없으면 None
    confidence: float | None
    # 신뢰도 60 미만 단어의 비율 (평균이 높아도 쓰레기 단어가 섞였는지 본다)
    weak_ratio: float = 0.0


class OcrEngine(Protocol):
    def read(self, image: Image.Image) -> OcrResult: ...


class OcrUnavailableError(RuntimeError):
    """OCR 엔진(Tesseract)이 설치되지 않았거나 실행할 수 없다."""


def prepare(image: Image.Image) -> Image.Image:
    """사진 방향을 바로잡고, 흑백으로 바꾸고, 작은 그림은 키운다."""
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        # 투명 배경은 흰색으로 깐다 (검은 배경이 되면 글자가 사라진다)
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        image = Image.alpha_composite(background, rgba)
    image = image.convert("L")
    if max(image.size) < _UPSCALE_BELOW:
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
    return image


class TesseractEngine:
    def __init__(self, settings: OCRSettings | None = None) -> None:
        self.settings = settings or OCRSettings()
        self._cmd = self.settings.tesseract_cmd or "tesseract"

    def _use_cmd(self) -> None:
        # pytesseract는 실행 파일 경로를 모듈 전역으로 들고 있어 호출마다 맞춘다
        pytesseract.pytesseract.tesseract_cmd = self._cmd

    def check(self) -> None:
        """Tesseract와 언어 데이터가 준비됐는지 확인한다. 아니면 OcrUnavailableError."""
        self._use_cmd()
        try:
            languages = set(pytesseract.get_languages(config=""))
        except (pytesseract.TesseractNotFoundError, OSError) as e:
            raise OcrUnavailableError("tesseract is not installed") from e
        missing = set(self.settings.ocr_lang.split("+")) - languages
        if missing:
            raise OcrUnavailableError(f"tesseract language data missing: {sorted(missing)}")

    def read(self, image: Image.Image) -> OcrResult:
        prepared = prepare(image)
        result = self._run(prepared, _LAYOUT_PSM)
        # 쪽 배치 모드는 한 줄짜리 한글 띠 그림(슬라이드 속 캡션 등)에서 글자를 통째로 놓친다.
        # 아무것도 못 읽었거나 자신 없는 단어가 많으면 글 덩어리 모드로 한 번 더 읽는다.
        if not result.text or result.weak_ratio > self.settings.ocr_retry_weak_ratio:
            block = self._run(prepared, _BLOCK_PSM)
            if (block.confidence or 0) > (result.confidence or 0):
                result = block
        return result

    def _run(self, image: Image.Image, psm: str) -> OcrResult:
        """한 번 실행으로 글자(txt)와 단어별 신뢰도(tsv)를 함께 받는다.

        글자는 Tesseract가 직접 띄어 쓴 txt를 쓴다. tsv는 한글을 음절마다 다른 단어로 나눠
        띄어쓰기를 되살릴 수 없다("프 로 세 스").
        """
        self._use_cmd()
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "in.png"
            out = Path(folder) / "out"
            image.save(source)
            try:
                pytesseract.pytesseract.run_tesseract(
                    str(source),
                    str(out),
                    extension="txt",
                    lang=self.settings.ocr_lang,
                    config=f"{psm} -c tessedit_create_tsv=1",
                    timeout=self.settings.ocr_timeout_seconds,
                )
            except (pytesseract.TesseractNotFoundError, OSError) as e:
                raise OcrUnavailableError("tesseract is not installed") from e
            except RuntimeError:  # 시간 초과: 이 그림은 못 읽은 것으로 본다
                logger.info("tesseract timed out")
                return OcrResult("", None)
            text = out.with_suffix(".txt").read_text(encoding="utf-8")
            tsv = out.with_suffix(".tsv").read_text(encoding="utf-8")
        return OcrResult(clean_text(text), *word_confidence(tsv))


def clean_text(text: str) -> str:
    """빈 줄과 겹친 공백을 정리한다 (Tesseract는 덩어리 사이에 빈 줄을 넣는다)."""
    lines = (" ".join(line.split()) for line in normalize_text(text).split("\n"))
    return "\n".join(line for line in lines if line)


def word_confidence(tsv: str) -> tuple[float | None, float]:
    """tsv에서 단어 평균 신뢰도와 자신 없는 단어 비율을 계산한다."""
    rows = [line.split("\t") for line in tsv.splitlines() if line]
    if not rows:
        return None, 0.0
    header = rows[0]
    conf_at, text_at = header.index("conf"), header.index("text")
    confidences = [
        float(row[conf_at])
        for row in rows[1:]
        if len(row) > text_at and row[text_at].strip() and float(row[conf_at]) >= 0
    ]
    if not confidences:
        return None, 0.0
    weak = sum(c < _WEAK_WORD for c in confidences) / len(confidences)
    return sum(confidences) / len(confidences), weak


def _is_known_char(ch: str) -> bool:
    return (
        ch.isspace()
        or ch.isalnum()  # 한글, 영문, 숫자
        or ch in ".,:;!?()[]{}<>-–—_/\\'\"%&+=*#@~·•…①②③④⑤⑥⑦⑧⑨⑩▶▣□■○●※→←↑↓"
    )


def garbage_ratio(text: str) -> float:
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return 0.0
    return sum(not _is_known_char(ch) for ch in chars) / len(chars)


def doubt_reason(
    result: OcrResult, image_size: tuple[int, int], settings: OCRSettings
) -> str | None:
    """Tesseract 결과가 애매하면 그 이유를, 믿을 만하면 None을 돌려준다."""
    width, height = image_size
    chars = len("".join(result.text.split()))
    if (
        width * height >= settings.ocr_large_image_pixels
        and chars < settings.ocr_min_chars_for_large
    ):
        return "large image with little text"
    if result.confidence is not None and result.confidence < settings.ocr_min_confidence:
        return f"low confidence {result.confidence:.0f}"
    if result.weak_ratio > settings.ocr_max_weak_ratio:
        return f"many unsure words {result.weak_ratio:.0%}"
    if garbage_ratio(result.text) > settings.ocr_max_garbage_ratio:
        return "many unknown symbols"
    # 한글 사이 영어(예: "Context Switch" → "5\/|[1)")처럼 점수는 높은데 틀린 경우를 잡는다
    odd = odd_token_ratio(result.text)
    if odd > settings.ocr_max_odd_token_ratio:
        return f"many odd tokens {odd:.0%}"
    return None


# 정상 글에는 드문 기호. OCR이 글자를 잘못 읽으면 자주 나온다
_ODD_SYMBOLS = set("|\\×【】『』「」¦§¤©®™°±¬")


# 홀로 떨어져 있으면 이상한 기호. 글머리표(-, •, ①, ▶, ※ 등)는 정상이라 넣지 않는다
_ODD_ALONE = set("=<>~^`_")


def _is_odd_token(token: str) -> bool:
    if len(token) == 1 and token in _ODD_ALONE:
        return True
    return any(ch in _ODD_SYMBOLS or not _is_known_char(ch) for ch in token)


def odd_token_ratio(text: str) -> float:
    """이상한 낱말(드문 기호가 섞였거나 기호 하나뿐인 낱말)의 비율."""
    tokens = text.split()
    if not tokens:
        return 0.0
    return sum(_is_odd_token(t) for t in tokens) / len(tokens)


def is_ocr_target(image_size: tuple[int, int], settings: OCRSettings) -> bool:
    """아이콘·장식처럼 작은 그림은 읽지 않는다."""
    return min(image_size) >= settings.ocr_min_image_side


@dataclass(frozen=True)
class OcrOutcome:
    text: str
    source: Literal["tesseract", "ai"]
    # Tesseract 결과가 애매했던 이유 (믿을 만했으면 None)
    doubt: str | None


class ImageTextReader(Protocol):
    """AI 보조 판독기. OpenAIProvider.read_image_text가 이 모양을 따른다."""

    async def read_image_text(self, image: bytes, mime_type: str) -> str: ...


def _to_png(image: Image.Image) -> bytes:
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((_AI_MAX_SIDE, _AI_MAX_SIDE))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class HybridOcr:
    """기본은 Tesseract, 결과가 애매할 때만 AI로 다시 읽는다. 자료 하나마다 새로 만든다.

    AI가 없거나(키·모델 미설정), 호출 상한에 닿았거나, AI 호출이 실패하면 Tesseract 결과를 쓴다.
    """

    def __init__(
        self,
        engine: OcrEngine,
        settings: OCRSettings,
        ai: ImageTextReader | None = None,
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.ai = ai
        self.ai_calls = 0
        self.images_read = 0

    def has_budget(self) -> bool:
        """자료 하나에서 OCR할 그림 수 상한(`ocr_max_images`)이 남았는지."""
        return self.images_read < self.settings.ocr_max_images

    async def read(self, image: Image.Image) -> OcrOutcome:
        self.images_read += 1
        result = await asyncio.to_thread(self.engine.read, image)
        doubt = doubt_reason(result, image.size, self.settings)
        kept = result.text
        if (
            doubt is not None
            and result.confidence is not None
            and result.confidence < self.settings.ocr_drop_below_confidence
        ):
            kept = ""  # 직인·무늬처럼 거의 다 틀린 결과는 쓰레기 글자를 남기느니 버린다
        fallback = OcrOutcome(kept, "tesseract", doubt)
        if doubt is None or self.ai is None or self.ai_calls >= self.settings.ocr_ai_max_calls:
            return fallback
        self.ai_calls += 1
        try:
            text = await self.ai.read_image_text(_to_png(image), "image/png")
        except LLMError, ValueError:
            return fallback
        return OcrOutcome(normalize_text(text), "ai", doubt)
