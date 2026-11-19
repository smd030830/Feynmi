"""Download bytes only after the existing owner-scoped lookup succeeds."""

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock
from urllib.parse import unquote

import httpx
import pytest
from fastapi import FastAPI

from backend.api.deps import get_db, require_profile
from backend.api.materials import router
from backend.errors import AppError, register_error_handlers
from backend.services import materials


def download_setup(status="ready", title="운영체제.pdf") -> tuple[Any, ...]:
    material = SimpleNamespace(
        id=uuid.uuid4(), status=status, title=title, file_type="pdf", gcs_path="private/source.pdf"
    )
    db = SimpleNamespace(scalar=AsyncMock(return_value=material))
    storage = SimpleNamespace(load=Mock(return_value=b"%PDF-original"))
    return material, db, storage


@pytest.mark.parametrize(
    "status", ["ready", "failed", "queued", "extracting", "generating_concepts"]
)
async def test_download_returns_original_for_uploaded_material(status):
    material, db, storage = download_setup(status)
    owner = uuid.uuid4()
    actual, content = await materials.download_material(db, storage, owner, material.id)
    assert actual is material
    assert content == b"%PDF-original"
    storage.load.assert_called_once_with(material.gcs_path)
    # Ensure the real ownership lookup includes the caller rather than trusting the ID alone.
    query = db.scalar.await_args.args[0]
    assert owner in query.compile().params.values()


async def test_download_never_loads_another_owners_or_missing_material():
    material, db, storage = download_setup()
    db.scalar.return_value = None
    with pytest.raises(AppError) as caught:
        await materials.download_material(db, storage, uuid.uuid4(), material.id)
    assert (caught.value.status_code, caught.value.code) == (404, "not_found")
    storage.load.assert_not_called()


async def test_pending_upload_cannot_be_downloaded():
    material, db, storage = download_setup("pending_upload")
    with pytest.raises(AppError) as caught:
        await materials.download_material(db, storage, uuid.uuid4(), material.id)
    assert (caught.value.status_code, caught.value.code) == (409, "material_busy")
    storage.load.assert_not_called()


@pytest.mark.parametrize(
    ("failure", "status", "code", "retryable"),
    [
        (FileNotFoundError(), 404, "original_missing", False),
        (RuntimeError("private bucket details"), 503, "storage_unavailable", True),
        (AppError(503, "storage_unavailable"), 503, "storage_unavailable", False),
    ],
)
async def test_download_storage_errors(failure, status, code, retryable):
    material, db, storage = download_setup()
    storage.load.side_effect = failure
    with pytest.raises(AppError) as caught:
        await materials.download_material(db, storage, uuid.uuid4(), material.id)
    assert (caught.value.status_code, caught.value.code, caught.value.retryable) == (
        status,
        code,
        retryable,
    )


@pytest.mark.parametrize("title", ["운영체제.pdf", "../folder\\자료\r\n이름.pdf", "\r\n"])
async def test_download_response_preserves_bytes_and_safe_attachment_filename(title):
    material, db, storage = download_setup(title=title)
    app = FastAPI()
    app.include_router(router)
    app.state.storage = storage
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_profile] = lambda: SimpleNamespace(
        user=SimpleNamespace(id=uuid.uuid4())
    )
    register_error_handlers(app)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/materials/{material.id}/download")
    assert response.status_code == 200
    assert response.content == b"%PDF-original"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment; filename=\"material.pdf\"; filename*=UTF-8''")
    filename = unquote(disposition.split("filename*=UTF-8''")[1])
    assert all(c not in filename for c in ["\r", "\n", "/", "\\"])
    if title == "운영체제.pdf":
        assert filename == title


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (FileNotFoundError("private/source.pdf"), 404, "original_missing"),
        (RuntimeError("private bucket details"), 503, "storage_unavailable"),
    ],
)
async def test_download_response_reports_storage_errors_without_leaking_details(
    failure, status, code
):
    material, db, storage = download_setup()
    storage.load.side_effect = failure
    app = FastAPI()
    app.include_router(router)
    app.state.storage = storage
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_profile] = lambda: SimpleNamespace(
        user=SimpleNamespace(id=uuid.uuid4())
    )
    register_error_handlers(app)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/materials/{material.id}/download")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "private" not in response.text
