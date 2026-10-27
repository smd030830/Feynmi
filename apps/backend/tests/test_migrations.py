import asyncio
import os
from collections.abc import Callable

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.db.models import Base
from backend.db.session import make_engine

EXPECTED_TABLES = {
    "users",
    "user_settings",
    "login_events",
    "projects",
    "materials",
    "chunks",
    "concepts",
    "concept_elements",
    "concept_misconceptions",
    "sessions",
    "messages",
    "assessments",
    "assessment_elements",
    "feedbacks",
}


def _run[T](fn: Callable[[Connection], T]) -> T:
    async def go() -> T:
        engine = make_engine(os.environ["DATABASE_URL"])
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(fn)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _tables(conn: Connection) -> set[str]:
    rows = conn.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    ).scalars()
    return set(rows)


def _has_vector_extension(conn: Connection) -> bool:
    return (
        conn.execute(
            text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one()
        == 1
    )


def test_upgrade_downgrade_upgrade(empty_db: None, alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "head")
    assert _run(_tables) == EXPECTED_TABLES | {"alembic_version"}
    assert _run(_has_vector_extension)

    command.downgrade(alembic_cfg, "base")
    assert _run(_tables) == {"alembic_version"}
    assert not _run(_has_vector_extension)

    command.upgrade(alembic_cfg, "head")
    assert _run(_tables) == EXPECTED_TABLES | {"alembic_version"}


def test_models_match_migrations(migrated_db: None) -> None:
    """모델을 고치고 마이그레이션을 만들지 않았다면 여기서 걸린다."""

    def diff(conn: Connection) -> list:
        return compare_metadata(MigrationContext.configure(conn), Base.metadata)

    assert _run(diff) == []
