import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.db.session import make_engine

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://feynmi:feynmi@localhost:5432/feynmi_test"
)

# 앱 설정과 Alembic이 테스트 DB를 보게 한다. .env의 개발 DB로 새어 나가지 않도록 덮어쓴다.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("FIREBASE_PROJECT_ID", "test")  # 앱 모듈을 불러올 때 필요하다


def _require_test_database() -> None:
    name = make_url(TEST_DATABASE_URL).database or ""
    if not name.endswith("_test"):
        # 스키마를 통째로 지우므로 테스트 전용 DB가 아니면 거부한다.
        pytest.exit(f"TEST_DATABASE_URL의 DB 이름은 '_test'로 끝나야 합니다: {name!r}", 2)


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


async def _reset_schema() -> None:
    engine = make_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


def reset_schema() -> None:
    """테스트 DB를 빈 상태로 되돌린다(확장 포함)."""
    _require_test_database()
    asyncio.run(_reset_schema())


@pytest.fixture
def alembic_cfg() -> Config:
    return alembic_config()


@pytest.fixture
def empty_db() -> None:
    reset_schema()


@pytest.fixture
def migrated_db(empty_db: None, alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "head")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    _require_test_database()
    engine = make_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()
