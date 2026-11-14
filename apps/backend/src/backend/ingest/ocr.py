"""이미지 글자 인식(OCR). 기본 엔진은 Tesseract이고, 결과가 애매한지 스스로 판단한다.

애매한 결과를 AI로 다시 읽을지는 호출하는 쪽(수집 파이프라인)이 정한다.
"""

import asyncio
import io
import logging
import re
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
    # 엉터리 줄을 거르기 전, 그림 전체 단어의 평균 신뢰도. 그림을 통째로 버릴지는 이것으로 정한다
    # (손글씨: 전체 38 → 거른 뒤 남은 조각만 62.7이 되어 엉터리가 남던 문제).
    # 없으면 confidence를 쓴다
    raw_confidence: float | None = None


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
        # 쪽 배치 모드(psm 3)가 실패하는 경우 글 덩어리 모드(psm 6)로 한 번 더 읽는다.
        # - 아무것도 못 읽음: 한 줄짜리 한글 띠 그림(슬라이드 속 캡션 등)
        # - 자신 없는 단어가 많음
        # - 줄이 조각남: 손실 압축 사진(JPG·HEIC)에서 한 줄을 여러 조각으로 나눠 순서까지 섞는다
        #   ("운영체제 3장: 프로세스" → "프로세 / 운영체제 3장: / … / 스")
        if (
            not result.text
            or result.weak_ratio > self.settings.ocr_retry_weak_ratio
            or fragmentation(result.text) >= _FRAGMENTED
        ):
            block = self._run(prepared, _BLOCK_PSM)
            if _is_better(block, result):
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
        return reliable_result(text, tsv, self.settings.ocr_min_line_confidence)


# 공백을 뺀 글자 수가 이 이하인 줄을 "조각"으로 본다
_SHORT_LINE = 4
# 조각 줄 비율이 이 이상이면 줄이 조각난 것으로 본다 (손실 압축 사진에서 0.4~0.7, 정상 글은 낮음)
_FRAGMENTED = 0.3
# 두 결과의 신뢰도가 이만큼 안쪽으로 비슷하면, 덜 조각난 쪽을 고른다
_CONFIDENCE_SLACK = 3.0
# 절반 넘게 조각났으면 조각마다 신뢰도가 높게 나와 믿기 어렵다. 이때는 차이를 더 봐준다
# (손실 압축 HEIC: 조각난 결과 90, 제대로 줄을 맞춘 결과 84)
_HEAVY_FRAGMENTED = 0.5
_HEAVY_SLACK = 10.0


def fragmentation(text: str) -> float:
    """조각 줄(공백 뺀 글자 4자 이하)의 비율."""
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return 0.0
    return sum(len("".join(line.split())) <= _SHORT_LINE for line in lines) / len(lines)


def _is_better(block: OcrResult, layout: OcrResult) -> bool:
    """글 덩어리 모드 결과를 쓸지: 신뢰도가 더 높거나, 비슷하면서 덜 조각났을 때."""
    if not block.text:
        return False
    block_conf, layout_conf = block.confidence or 0, layout.confidence or 0
    if block_conf > layout_conf:
        return True
    layout_frag, block_frag = fragmentation(layout.text), fragmentation(block.text)
    slack = _HEAVY_SLACK if layout_frag >= _HEAVY_FRAGMENTED else _CONFIDENCE_SLACK
    return block_conf >= layout_conf - slack and block_frag < layout_frag


def clean_text(text: str) -> str:
    """빈 줄과 겹친 공백을 정리한다 (Tesseract는 덩어리 사이에 빈 줄을 넣는다)."""
    lines = (" ".join(line.split()) for line in normalize_text(text).split("\n"))
    return "\n".join(line for line in lines if line)


def _confidences(words: list[float]) -> tuple[float | None, float]:
    if not words:
        return None, 0.0
    weak = sum(c < _WEAK_WORD for c in words) / len(words)
    return sum(words) / len(words), weak


def line_words(tsv: str) -> list[list[float]]:
    """tsv의 줄마다 단어 신뢰도 목록. txt의 (빈 줄이 아닌) 줄과 같은 순서다."""
    rows = [line.split("\t") for line in tsv.splitlines() if line]
    if not rows:
        return []
    header = rows[0]
    conf_at, text_at = header.index("conf"), header.index("text")
    keys = ("page_num", "block_num", "par_num", "line_num")
    key_at = [header.index(k) for k in keys if k in header]  # 없으면 한 줄로 본다
    lines: dict[tuple[str, ...], list[float]] = {}
    for row in rows[1:]:
        if len(row) > text_at and row[text_at].strip() and float(row[conf_at]) >= 0:
            lines.setdefault(tuple(row[i] for i in key_at), []).append(float(row[conf_at]))
    return list(lines.values())


def word_confidence(tsv: str) -> tuple[float | None, float]:
    """tsv에서 단어 평균 신뢰도와 자신 없는 단어 비율을 계산한다."""
    return _confidences([c for words in line_words(tsv) for c in words])


# 코드 편집기의 들여쓰기 안내선·접기 표시가 줄 앞에 "| ", "! ", ": ", "4 | "처럼 붙어 읽힌다.
# 낱자 기호 뒤에 공백이 오는 묶음이고, 끝이 분명한 안내선 기호(| ! : 등)일 때만 지운다.
# "1 from …"(줄 번호)이나 "'따옴표'"는 그대로 둔다.
_GUTTER = re.compile(r"^(?:[|!¦ㅣ:‘'`iIl14t]\s+)*[|!¦ㅣ:‘'`]\s+")
_HANGUL = re.compile(r"[가-힣]")
_ACRONYM = re.compile(r"[A-Z]{2,3}")  # CPU, ID, OS 같은 짧은 약어는 남긴다


def _hangul_ratio(line: str) -> float:
    chars = [ch for ch in line if not ch.isspace()]
    return sum(bool(_HANGUL.match(ch)) for ch in chars) / len(chars) if chars else 0.0


def _is_fragment(line: str) -> bool:
    """도표·무늬에서 나온 짧은 조각 ("rh", "oat", "+", "00"). 한글과 약어는 남긴다."""
    compact = "".join(line.split())
    return len(compact) <= 3 and not _HANGUL.search(compact) and not _ACRONYM.fullmatch(compact)


def _is_scatter(line: str, confidence: float | None) -> bool:
    """무늬·도표를 읽은 줄: 한두 글자 낱말이 대부분이고, 이상한 기호가 있거나 신뢰도가 낮다.

    예: "© B25 © f aA", "GE; © © @ [) Nod 7 71 7". 수식("x = a + b")은 기호가 정상이고
    신뢰도가 높아 남는다.
    """
    tokens = line.split()
    if len(tokens) < 4 or _hangul_ratio(line) >= 0.3:
        return False
    short = sum(len(t) <= 2 for t in tokens) / len(tokens)
    # 수식의 = < > 는 정상이므로, 정상 글에 드문 기호(© ¦ 등)와 모르는 기호만 본다
    odd = any(ch in _ODD_SYMBOLS or not _is_known_char(ch) for ch in line if not ch.isspace())
    return short >= 0.6 and (odd or (confidence is not None and confidence < _WEAK_WORD))


def reliable_result(text: str, tsv: str, min_line_confidence: float) -> OcrResult:
    """믿을 만한 줄만 남긴다. 신뢰도는 남긴 줄의 단어로 다시 계산한다.

    도표·아이콘을 함께 읽으면 좋은 줄 사이에 엉터리 줄("ESE acco", "pasa Pal 6 |")이 섞인다.
    그림 전체를 버리면 좋은 줄까지 잃으므로 줄 단위로 거른다:
    - 신뢰도가 낮고(min_line_confidence 미만) 한글이 절반도 안 되는 줄
    - 한글 없는 3자 이하 조각
    - 한두 글자 낱말과 이상한 기호가 흩어진 줄 (무늬·도표)
    txt와 tsv의 줄 수가 다르면(드묾) 신뢰도 거르기는 하지 않는다.
    """
    cleaned = clean_text(text)
    lines = cleaned.split("\n") if cleaned else []
    words = line_words(tsv)
    by_line = len(words) == len(lines)
    kept: list[str] = []
    kept_words: list[float] = []
    for i, raw in enumerate(lines):
        line = _GUTTER.sub("", raw).strip()
        confidence = _confidences(words[i])[0] if by_line else None
        if not line or _is_fragment(line) or _is_scatter(line, confidence):
            continue
        if by_line:
            if (confidence or 0) < min_line_confidence and _hangul_ratio(line) < 0.5:
                continue
            kept_words.extend(words[i])
        kept.append(line)
    all_words = [c for line_confs in words for c in line_confs]
    if not by_line:
        kept_words = all_words
    confidence, weak = _confidences(kept_words)
    return OcrResult("\n".join(kept), confidence, weak, raw_confidence=_confidences(all_words)[0])


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
        # 버릴지는 거르기 전 그림 전체의 신뢰도로 판단한다 (남은 조각만의 신뢰도는 부풀 수 있다)
        whole = result.raw_confidence if result.raw_confidence is not None else result.confidence
        if (
            doubt is not None
            and whole is not None
            and whole < self.settings.ocr_drop_below_confidence
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
