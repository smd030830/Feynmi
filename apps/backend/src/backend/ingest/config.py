from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.config import Settings


class OCRSettings(BaseSettings):
    """이미지 글자 인식(OCR) 설정. 기본은 Tesseract, 결과가 애매할 때만 AI로 다시 읽는다."""

    model_config = SettingsConfigDict(
        env_file=Settings.model_config.get("env_file"), extra="ignore"
    )

    # Tesseract 실행 파일 경로. 비우면 PATH에서 찾는다
    # (Windows 예: C:\Program Files\Tesseract-OCR\tesseract.exe)
    tesseract_cmd: str | None = None
    ocr_lang: str = "kor+eng"
    # 그림 한 장을 읽는 시간 상한(초). 넘으면 그 그림은 못 읽은 것으로 본다 (데드라인 보호)
    ocr_timeout_seconds: int = Field(default=60, ge=1)
    # 서버 전체에서 동시에 돌리는 Tesseract 수. 0이면 CPU 수만큼
    # (자리를 기다리는 시간은 위 시간 상한에 들어가지 않는다)
    ocr_max_parallel: int = Field(default=0, ge=0)
    # 이보다 작은 그림(가로나 세로, 픽셀)은 아이콘·장식으로 보고 읽지 않는다
    ocr_min_image_side: int = Field(default=100, ge=1)
    # 자료 하나에서 OCR할 그림 수 상한 (분석 데드라인 30분 보호, architecture 7.1)
    ocr_max_images: int = Field(default=300, ge=0)
    # "애매함" 기준: 단어 평균 신뢰도가 이보다 낮으면 애매
    ocr_min_confidence: float = Field(default=60.0, ge=0, le=100)
    # "애매함" 기준: 신뢰도 60 미만 단어의 비율이 이보다 높으면 애매
    ocr_max_weak_ratio: float = Field(default=0.3, ge=0, le=1)
    # 이 비율을 넘으면 Tesseract를 "한 덩어리 글" 모드로 한 번 더 돌려 더 나은 쪽을 쓴다
    ocr_retry_weak_ratio: float = Field(default=0.05, ge=0, le=1)
    # "애매함" 기준: 큰 그림(이 면적 이상)인데 글자가 이보다 적으면 애매
    ocr_large_image_pixels: int = Field(default=500_000, ge=1)
    ocr_min_chars_for_large: int = Field(default=10, ge=0)
    # "애매함" 기준: 알 수 없는 기호 비율이 이보다 높으면 애매
    ocr_max_garbage_ratio: float = Field(default=0.3, ge=0, le=1)
    # "애매함" 기준: 이상한 낱말(드문 기호가 섞였거나 기호 하나뿐)의 비율이 이보다 높으면 애매
    ocr_max_odd_token_ratio: float = Field(default=0.1, ge=0, le=1)
    # "애매함" 기준: 줄 거르기로 버린 글자가 이 비율보다 많으면 애매
    ocr_max_dropped_ratio: float = Field(default=0.2, ge=0, le=1)
    # 애매한데 평균 신뢰도가 이보다 낮으면(AI로 다시 읽지 못할 때) 글자를 버린다
    ocr_drop_below_confidence: float = Field(default=40.0, ge=0, le=100)
    # 그림 속 한 줄의 단어 평균 신뢰도가 이보다 낮고 한글이 절반 미만이면 그 줄을 버린다
    # (도표·아이콘에서 나온 엉터리 줄). 실제 자료에서 엉터리 줄은 8~33, 정상 줄은 대부분 40 이상
    ocr_min_line_confidence: float = Field(default=35.0, ge=0, le=100)
    # 자료 하나에서 AI로 다시 읽는 횟수 상한 (비용 보호). 0이면 AI 보조를 쓰지 않는다
    ocr_ai_max_calls: int = Field(default=20, ge=0)
