"""Project deletion rejects unsafe states before touching external storage."""

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from backend.errors import AppError
from backend.services import projects


def setup_delete(monkeypatch: pytest.MonkeyPatch, statuses: list[str]) -> tuple[Any, ...]:
    project = SimpleNamespace(id=uuid.uuid4())
    materials = [SimpleNamespace(status=s, gcs_path=f"source-{i}") for i, s in enumerate(statuses)]
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=project),
        scalars=AsyncMock(return_value=materials),
        delete=AsyncMock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    storage = SimpleNamespace(delete=Mock())
    archive = AsyncMock()
    monkeypatch.setattr(projects, "lock_learning_user", AsyncMock())
    monkeypatch.setattr(projects, "archive_material_sessions", archive)
    return db, storage, archive, project, materials


async def test_busy_material_prevents_any_archive_or_storage_change(monkeypatch):
    db, storage, archive, project, _ = setup_delete(monkeypatch, ["ready", "extracting"])
    with pytest.raises(AppError):
        await projects.delete_project(db, storage, uuid.uuid4(), project.id)
    archive.assert_not_awaited()
    storage.delete.assert_not_called()
    db.delete.assert_not_awaited()


async def test_busy_evaluation_prevents_storage_deletion(monkeypatch):
    db, storage, archive, project, _ = setup_delete(monkeypatch, ["ready", "failed"])
    archive.side_effect = [None, AppError(409, "evaluation_in_progress")]
    with pytest.raises(AppError):
        await projects.delete_project(db, storage, uuid.uuid4(), project.id)
    storage.delete.assert_not_called()
    db.commit.assert_not_awaited()


async def test_partial_storage_failure_rolls_back_and_retry_deletes_all_sources(monkeypatch):
    db, storage, _, project, materials = setup_delete(monkeypatch, ["ready", "failed"])
    storage.delete.side_effect = [None, RuntimeError("storage unavailable")]
    with pytest.raises(AppError):
        await projects.delete_project(db, storage, uuid.uuid4(), project.id)
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
    storage.delete.side_effect = None
    storage.delete.reset_mock()
    await projects.delete_project(db, storage, uuid.uuid4(), project.id)
    assert [call.args[0] for call in storage.delete.call_args_list] == [
        m.gcs_path for m in materials
    ]
    db.commit.assert_awaited_once()


async def test_missing_or_other_owner_project_never_touches_storage(monkeypatch):
    db, storage, _, project, _ = setup_delete(monkeypatch, [])
    db.scalar.return_value = None
    with pytest.raises(AppError):
        await projects.delete_project(db, storage, uuid.uuid4(), project.id)
    db.scalars.assert_not_awaited()
    storage.delete.assert_not_called()


async def test_success_archives_every_material_before_removing_project(monkeypatch):
    db, storage, archive, project, materials = setup_delete(monkeypatch, ["ready", "failed"])
    user_id = uuid.uuid4()

    async def verify_archive_before_delete(_):
        assert archive.await_count == len(materials)

    db.delete.side_effect = verify_archive_before_delete
    await projects.delete_project(db, storage, user_id, project.id)
    assert [call.args for call in archive.await_args_list] == [
        (db, user_id, material) for material in materials
    ]
    db.delete.assert_awaited_once_with(project)
    db.flush.assert_awaited_once()
    assert storage.delete.call_count == len(materials)
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()
