from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator
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
    # GCS_BUCKET이 비었을 때 쓰는 로컬 GCS 에뮬레이터 (architecture 11.2).
    # 백엔드가 부르는 주소와 브라우저가 업로드할 공개 주소가 다르다
    # (compose: http://gcs:4443 / http://localhost:4443)
    gcs_emulator_url: str = ""
    gcs_emulator_public_url: str = ""
    # 분석 작업 전달: inline(같은 프로세스, 로컬) 또는 cloud_tasks (architecture 7.1, 11.1)
    queue_mode: Literal["inline", "cloud_tasks"] = "inline"
    tasks_project: str = ""
    tasks_location: str = ""
    tasks_queue: str = ""
    # Cloud Tasks가 워커를 부를 때 OIDC 토큰을 서명하는 서비스 계정. 워커는 이 계정의 토큰만 받는다
    tasks_invoker_sa: str = ""
    # 워커 호출 URL의 앞부분이자 OIDC audience (예: https://feynmi-api-xxxx.run.app)
    public_base_url: str = ""
    # 진행 상태로 이 시간을 넘긴 자료는 멈춘 것으로 보고 실패 처리한다 (Cloud Tasks 데드라인과 같게)
    analysis_deadline_minutes: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def _cloud_tasks_deadline(self) -> Self:
        if self.queue_mode == "cloud_tasks" and self.analysis_deadline_minutes > 30:
            raise ValueError("Cloud Tasks analysis deadline must not exceed 30 minutes")
        return self

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
