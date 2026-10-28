from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# 저장소 루트의 .env. 컨테이너처럼 파일이 없으면 환경변수만 쓴다.
_parents = Path(__file__).resolve().parents
ROOT_ENV_FILE = _parents[4] / ".env" if len(_parents) > 4 else None


class Settings(BaseSettings):
    """환경변수 설정 (architecture.md 10장). 항목은 쓰는 기능이 생길 때 추가한다."""

    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, extra="ignore")

    # asyncpg 접속 문자열 (postgresql+asyncpg://user:password@host:5432/db). 기본값은 두지 않는다.
    database_url: str
    # ID 토큰의 발급 대상 프로젝트 (architecture.md 10장)
    firebase_project_id: Annotated[str, Field(min_length=1)]
    cors_origins: Annotated[list[str], NoDecode] = []

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # 쉼표 구분 문자열을 허용한다: CORS_ORIGINS=http://localhost:3000,https://feynmi.vercel.app
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    # database_url 등은 환경변수에서 읽으므로 생성자 인자가 없다. 타입 검사기는 이를 모른다.
    return Settings()  # pyright: ignore[reportCallIssue]
