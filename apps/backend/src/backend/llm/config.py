from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, StringConstraints, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ROOT = (Path(__file__).resolve().parents[3] / "../..").resolve()


class LLMSettings(BaseSettings):
    """이 모듈을 구성할 때만 검증한다. 모델 ID와 effort의 기본값은 없다."""

    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / ".env.llm"),
        extra="ignore",
    )
    openai_api_key: SecretStr
    llm_concept_extraction_model: NonEmpty
    llm_concept_extraction_effort: NonEmpty
    llm_assessment_model: NonEmpty
    llm_assessment_effort: NonEmpty
    llm_embedding_model: NonEmpty
    # 애매한 OCR 결과를 다시 읽는 멀티모달 모델. 비우면 AI 보조 OCR을 쓰지 않는다
    llm_image_text_model: str | None = None
    llm_image_text_effort: str | None = None
    # OpenAI 호환 API 주소. 비우면 OpenAI. OpenRouter는 https://openrouter.ai/api/v1
    # (모델 ID에 공급자 접두어가 붙는다: openai/text-embedding-3-small)
    llm_base_url: str = "https://api.openai.com/v1"
    llm_max_retries: int = Field(default=2, ge=0, le=10)
    llm_timeout_seconds: float = Field(default=60, gt=0, allow_inf_nan=False)

    @field_validator("llm_base_url", mode="before")
    @classmethod
    def https_base_url(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return "https://api.openai.com/v1"
        if not isinstance(value, str) or not value.strip().startswith("https://"):
            raise ValueError("LLM_BASE_URL must be an https URL")
        return value.strip().rstrip("/")

    @field_validator("openai_api_key")
    @classmethod
    def nonempty_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("OPENAI_API_KEY must not be empty")
        return value
