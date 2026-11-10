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
    llm_max_retries: int = Field(default=2, ge=0, le=10)
    llm_timeout_seconds: float = Field(default=60, gt=0, allow_inf_nan=False)

    @field_validator("openai_api_key")
    @classmethod
    def nonempty_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("OPENAI_API_KEY must not be empty")
        return value
