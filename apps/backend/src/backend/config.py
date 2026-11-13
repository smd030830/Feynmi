from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 설정 (architecture.md 10장). 항목은 쓰는 기능이 생길 때 추가한다."""

    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[2] / "../../.env").resolve(),
        extra="ignore",
    )

    # asyncpg 접속 문자열 (postgresql+asyncpg://user:password@host:5432/db). 기본값은 두지 않는다.
    database_url: str
    firebase_project_id: str
    gcs_bucket: str = ""
    gcs_signer_service_account: str = ""
    cors_origins: Annotated[list[str], NoDecode] = []
    # 원본 자료 보관 폴더 (로컬 개발용 보관소, Git 제외). GCS 대신 쓴다
    materials_dir: Path = Path(__file__).resolve().parents[4] / ".local-storage" / "materials"

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
