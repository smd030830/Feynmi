"""이미지 글자 인식(OCR). 기본 엔진은 Tesseract이고, 결과가 애매한지 스스로 판단한다.

애매한 결과를 AI로 다시 읽을지는 호출하는 쪽(수집 파이프라인)이 정한다.
"""

from dataclasses import dataclass
from typing import Protocol

import pytesseract
from PIL import Image, ImageOps

from backend.ingest.base import normalize_text
from backend.ingest.config import OCRSettings

# Tesseract가 잘 읽는 글자 높이를 맞추기 위해, 긴 변이 이보다 작으면 2배로 키운다
_UPSCALE_BELOW = 1000


@dataclass(frozen=True)
class OcrResult:
    text: str
    # 단어 평균 신뢰도(0~100). 읽힌 단어가 없으면 None
    confidence: float | None


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
        self._use_cmd()
        try:
            data = pytesseract.image_to_data(
                prepare(image), lang=self.settings.ocr_lang, output_type=pytesseract.Output.DICT
            )
        except (pytesseract.TesseractNotFoundError, OSError) as e:
            raise OcrUnavailableError("tesseract is not installed") from e
        return _from_data(data)


def _from_data(data: dict[str, list]) -> OcrResult:
    """image_to_data 결과를 줄 단위 글자와 평균 신뢰도로 묶는다."""
    lines: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    for i, word in enumerate(data["text"]):
        word = str(word).strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        key = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
        lines.setdefault(key, []).append(word)
        confidences.append(conf)
    text = "\n".join(" ".join(words) for _, words in sorted(lines.items()))
    confidence = sum(confidences) / len(confidences) if confidences else None
    return OcrResult(text=normalize_text(text), confidence=confidence)


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
    if garbage_ratio(result.text) > settings.ocr_max_garbage_ratio:
        return "many unknown symbols"
    return None


def is_ocr_target(image_size: tuple[int, int], settings: OCRSettings) -> bool:
    """아이콘·장식처럼 작은 그림은 읽지 않는다."""
    return min(image_size) >= settings.ocr_min_image_side
