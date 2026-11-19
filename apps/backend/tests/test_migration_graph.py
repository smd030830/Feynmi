"""Validate the migration chain without needing a running database."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migrations_have_one_linear_head() -> None:
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_current_head() == "0010"
    revisions = list(scripts.walk_revisions())
    assert len(revisions) == len({revision.revision for revision in revisions})
