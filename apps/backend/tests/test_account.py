import asyncio
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from account_fakes import FakeCloud
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.api.deps import _sync_user
from backend.auth.firebase import VerifiedToken
from backend.config import Settings
from backend.db.models import LoginEvent, Project, User
from backend.domain.enums import SignInProvider, UserStatus
from backend.errors import AppError
from backend.main import create_app
from backend.services.account import active_user, finish_deletion, mark_deleting, summarize_agent

NOW = datetime.now(UTC) - timedelta(minutes=1)


def verify(token: str) -> VerifiedToken:
    if token not in ("alice", "bob"):
        raise AppError(401, "unauthenticated")
    return VerifiedToken(token, f"{token}@example.com", True, SignInProvider.PASSWORD, NOW)


def headers(uid: str = "alice") -> dict[str, str]:
    return {"Authorization": f"Bearer {uid}"}


@pytest.fixture
def cloud() -> FakeCloud:
    return FakeCloud()


@pytest.fixture
async def app(engine: AsyncEngine, cloud: FakeCloud, migrated_db: None) -> FastAPI:
    app = create_app(
        Settings(
            database_url=engine.url.render_as_string(hide_password=False),
            firebase_project_id="test",
        ),
        token_verifier=verify,
    )
    app.state.account_cloud = cloud
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for uid in ("alice", "bob"):
            response = await client.patch(
                "/api/v1/me/profile", json={"nickname": uid}, headers=headers(uid)
            )
            assert response.status_code == 200
        yield client
    await app.state.session_factory.kw["bind"].dispose()


async def test_settings_defaults_partial_update_validation_and_isolation(
    client: httpx.AsyncClient,
) -> None:
    expected = {"question_depth": "basic", "notifications_enabled": True, "weekly_goal_days": 3}
    response = await client.get("/api/v1/me/settings", headers=headers())
    assert response.json() == expected
    changed = await client.patch(
        "/api/v1/me/settings",
        json={"question_depth": "deep", "weekly_goal_days": 7},
        headers=headers(),
    )
    assert changed.status_code == 200
    assert changed.json() == {**expected, "question_depth": "deep", "weekly_goal_days": 7}
    assert (await client.get("/api/v1/me/settings", headers=headers("bob"))).json() == expected
    for body in (
        {"weekly_goal_days": 0},
        {"weekly_goal_days": 8},
        {"weekly_goal_days": True},
        {"question_depth": "hard"},
        {"notifications_enabled": None},
    ):
        assert (
            await client.patch("/api/v1/me/settings", json=body, headers=headers())
        ).status_code == 400
    assert (await client.get("/api/v1/me/settings")).status_code == 401


async def test_login_events_recent_ten_owner_scoped_without_raw_agent_or_ip(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    for _ in range(12):
        response = await client.post(
            "/api/v1/me/login-events",
            headers={
                **headers(),
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/123.0 SECRET",
                "X-Forwarded-For": "192.0.2.1",
            },
        )
        assert response.status_code == 201
    events = (await client.get("/api/v1/me/login-events", headers=headers())).json()["items"]
    assert len(events) == 10
    assert all(item["client_summary"] == "Chrome · Windows" for item in events)
    assert not (await client.get("/api/v1/me/login-events", headers=headers("bob"))).json()["items"]
    async with app.state.session_factory() as db:
        all_rows = list(await db.scalars(select(LoginEvent)))
        assert len(all_rows) == 12
        assert all(
            "SECRET" not in row.client_summary and "192.0.2" not in row.client_summary
            for row in all_rows
        )


async def test_revoke_blocks_existing_tokens(client: httpx.AsyncClient, cloud: FakeCloud) -> None:
    response = await client.post("/api/v1/me/revoke-sessions", headers=headers())
    assert response.status_code == 200
    assert cloud.revoked == ["alice"]
    assert (await client.get("/api/v1/me", headers=headers())).status_code == 401
    assert (await client.get("/api/v1/me", headers=headers("bob"))).status_code == 200


async def test_avatar_raw_upload_validation_replacement_and_no_write_urls(
    client: httpx.AsyncClient, cloud: FakeCloud, app: FastAPI
) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"test"
    jpg = b"\xff\xd8\xff" + b"test"
    response = await client.post(
        "/api/v1/me/avatar", content=png, headers={**headers(), "Content-Type": "image/png"}
    )
    assert response.status_code == 200
    assert response.json()["avatar_url"].startswith("https://example.invalid/users/")
    assert len(cloud.files) == 1
    previous = next(iter(cloud.files))
    response = await client.post(
        "/api/v1/me/avatar", content=jpg, headers={**headers(), "Content-Type": "image/jpeg"}
    )
    assert response.status_code == 200
    assert len(cloud.files) == 1 and previous not in cloud.files
    current_path = next(iter(cloud.files))
    assert cloud.files[current_path] == ("image/jpeg", jpg)
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.firebase_uid == "alice"))
        assert user is not None and user.avatar_path == current_path
        bob = await db.scalar(select(User).where(User.firebase_uid == "bob"))
        assert bob is not None and bob.avatar_path is None
    for content_type, content in (
        ("image/png", b"not an image"),
        ("image/png", jpg),
        ("image/svg+xml", b"<svg/>"),
        ("image/png", b""),
        ("image/png", png + b"x" * 2097152),
    ):
        count = len(cloud.uploaded)
        invalid = await client.post(
            "/api/v1/me/avatar",
            content=content,
            headers={**headers(), "Content-Type": content_type},
        )
        assert invalid.status_code == 400
        assert len(cloud.uploaded) == count
    assert (await client.post("/api/v1/me/avatar", content=png)).status_code == 401
    for route in ("/avatar/upload-url", "/avatar/complete"):
        assert (
            await client.post("/api/v1/me" + route, json={}, headers=headers())
        ).status_code == 404


async def test_avatar_stream_rejects_oversize_without_content_length(
    client: httpx.AsyncClient, cloud: FakeCloud
) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b"\x89PNG\r\n\x1a\n"
        yield b"x" * 2097152

    response = await client.post(
        "/api/v1/me/avatar", content=chunks(), headers={**headers(), "Content-Type": "image/png"}
    )
    assert response.status_code == 400
    assert not cloud.uploaded


async def test_avatar_failures_preserve_previous_pointer(
    client: httpx.AsyncClient, cloud: FakeCloud, app: FastAPI
) -> None:
    image = b"\x89PNG\r\n\x1a\n" + b"test"
    assert (
        await client.post(
            "/api/v1/me/avatar", content=image, headers={**headers(), "Content-Type": "image/png"}
        )
    ).status_code == 200
    previous = next(iter(cloud.files))
    for failure in ("fail_upload", "fail_read_url"):
        setattr(cloud, failure, True)
        response = await client.post(
            "/api/v1/me/avatar",
            content=image,
            headers={**headers(), "Content-Type": "image/png"},
        )
        setattr(cloud, failure, False)
        assert response.status_code == 503
        assert list(cloud.files) == [previous]
        async with app.state.session_factory() as db:
            user = await db.scalar(select(User).where(User.firebase_uid == "alice"))
            assert user is not None and user.avatar_path == previous


@pytest.mark.parametrize("cancel_upload", [False, True])
async def test_inflight_avatar_upload_finishes_before_delete_including_cancellation(
    client: httpx.AsyncClient, cloud: FakeCloud, cancel_upload: bool
) -> None:
    cloud.upload_started = threading.Event()
    cloud.upload_release = threading.Event()
    upload = asyncio.create_task(
        client.post(
            "/api/v1/me/avatar",
            content=b"\x89PNG\r\n\x1a\n" + b"test",
            headers={**headers(), "Content-Type": "image/png"},
        )
    )
    deletion = None
    try:
        assert await asyncio.to_thread(cloud.upload_started.wait, 5)
        if cancel_upload:
            upload.cancel()
        deletion = asyncio.create_task(
            client.request("DELETE", "/api/v1/me", json={"confirm": "탈퇴"}, headers=headers())
        )
        await asyncio.sleep(0.05)
        assert not deletion.done()
        if cancel_upload:
            assert not upload.done()
    finally:
        cloud.upload_release.set()
    if cancel_upload:
        with pytest.raises(asyncio.CancelledError):
            await upload
    else:
        assert (await upload).status_code == 200
    assert deletion is not None
    assert (await deletion).status_code == 204
    assert not cloud.files
    assert cloud.deleted == {"alice"}


async def test_avatar_after_deleting_does_not_write_cloud(
    client: httpx.AsyncClient, cloud: FakeCloud
) -> None:
    cloud.fail_deletion = True
    assert (
        await client.request("DELETE", "/api/v1/me", json={"confirm": "탈퇴"}, headers=headers())
    ).status_code == 503
    response = await client.post(
        "/api/v1/me/avatar",
        content=b"\x89PNG\r\n\x1a\n" + b"test",
        headers={**headers(), "Content-Type": "image/png"},
    )
    assert response.status_code == 409
    assert not cloud.uploaded


async def test_delete_failure_retains_marker_blocks_access_and_recovers(
    client: httpx.AsyncClient, app: FastAPI, cloud: FakeCloud
) -> None:
    assert (
        await client.request("DELETE", "/api/v1/me", json={"confirm": "wrong"}, headers=headers())
    ).status_code == 400
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.firebase_uid == "alice"))
        assert user is not None
        user_id = user.id
        db.add(Project(user_id=user_id, name="study", color="indigo"))
        await db.commit()
    cloud.files[f"users/{user_id}/avatar/old.png"] = ("image/png", b"image")
    cloud.files["users/other/keep.pdf"] = ("application/pdf", b"pdf")
    cloud.fail_deletion = True
    failed = await client.request(
        "DELETE", "/api/v1/me", json={"confirm": "탈퇴"}, headers=headers()
    )
    assert failed.status_code == 503
    async with app.state.session_factory() as db:
        user = await db.get(User, user_id)
        assert user is not None and user.status == UserStatus.DELETING
    assert (await client.get("/api/v1/me", headers=headers())).status_code == 409
    assert (
        await client.patch("/api/v1/me/settings", json={"weekly_goal_days": 1}, headers=headers())
    ).status_code == 409
    cloud.fail_deletion = False
    # Worker recovery is independent of the browser/token/Firebase account.
    await finish_deletion(app.state.session_factory, cloud, user_id)
    await finish_deletion(app.state.session_factory, cloud, user_id)
    async with app.state.session_factory() as db:
        assert await db.get(User, user_id) is None
        assert (
            await db.scalar(
                select(func.count()).select_from(Project).where(Project.user_id == user_id)
            )
            == 0
        )
    assert cloud.calls == ["storage", "firebase", "storage", "firebase"]
    assert list(cloud.files) == ["users/other/keep.pdf"]
    # Signature-valid old token must not silently provision a fresh DB user.
    assert (await client.get("/api/v1/me", headers=headers())).status_code == 401
    assert (await client.get("/api/v1/me", headers=headers("bob"))).status_code == 200


async def test_delete_endpoint_retry_is_allowed_while_deleting(
    client: httpx.AsyncClient, cloud: FakeCloud
) -> None:
    cloud.fail_deletion = True
    assert (
        await client.request("DELETE", "/api/v1/me", json={"confirm": "탈퇴"}, headers=headers())
    ).status_code == 503
    cloud.fail_deletion = False
    assert (
        await client.request("DELETE", "/api/v1/me", json={"confirm": "탈퇴"}, headers=headers())
    ).status_code == 204


def test_agent_summary_does_not_echo_untrusted_input() -> None:
    assert summarize_agent("private arbitrary text") == "기타 브라우저 · 기타 OS"


async def test_mutation_rechecks_deleting_after_auth_loaded_active(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    factory = app.state.session_factory
    async with factory() as earlier:
        user = await earlier.scalar(select(User).where(User.firebase_uid == "alice"))
        assert user is not None
        async with factory() as later:
            newer = await later.get(User, user.id)
            assert newer is not None
            newer.status = UserStatus.DELETING
            await later.commit()
        # Identity-map contents from request authentication must not override a fresh row lock.
        with pytest.raises(AppError) as failure:
            await active_user(earlier, user.id)
        assert failure.value.code == "account_deleting"


async def test_profile_sync_cannot_recreate_user_deleted_after_initial_read(
    client: httpx.AsyncClient,
    app: FastAPI,
    cloud: FakeCloud,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = app.state.session_factory
    async with factory() as db:
        original_scalar = db.scalar
        deleted = False

        async def delete_after_read(*args: Any, **kwargs: Any) -> Any:
            nonlocal deleted
            row = await original_scalar(*args, **kwargs)
            if isinstance(row, User) and not deleted:
                deleted = True
                async with factory() as deletion_db:
                    await mark_deleting(deletion_db, row.id)
                await finish_deletion(factory, cloud, row.id)
            return row

        monkeypatch.setattr(db, "scalar", delete_after_read)
        token = VerifiedToken("alice", "changed@example.com", True, SignInProvider.PASSWORD, NOW)
        with pytest.raises(AppError) as failure:
            await _sync_user(db, token, cloud)
        assert failure.value.code == "account_deleting"
        await db.rollback()
    async with factory() as fresh:
        assert await fresh.scalar(select(User.id).where(User.firebase_uid == "alice")) is None
    assert "alice" in cloud.deleted
