"""인증과 인가 의존성을 실제 PostgreSQL로 확인한다 (architecture.md 5.2)."""

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.api.deps import CurrentUser, require_profile, require_verified_email
from backend.auth.firebase import VerifiedToken
from backend.config import Settings
from backend.db.models import User
from backend.db.session import make_session_factory
from backend.domain.enums import SignInProvider
from backend.errors import AppError
from backend.main import API_PREFIX, create_app

pytestmark = pytest.mark.usefixtures("migrated_db")

NOW = datetime.now(UTC)


def make_token(
    uid: str = "uid-1",
    *,
    email: str = "a@example.com",
    email_verified: bool = True,
    provider: SignInProvider = SignInProvider.PASSWORD,
    auth_time: datetime = NOW,
) -> VerifiedToken:
    return VerifiedToken(uid, email, email_verified, provider, auth_time)


def fake_verifier(tokens: dict[str, VerifiedToken]) -> Callable[[str], VerifiedToken]:
    def verify(token: str) -> VerifiedToken:
        if token not in tokens:
            raise AppError(401, "unauthenticated", "invalid id token")
        return tokens[token]

    return verify


@pytest.fixture
def tokens() -> dict[str, VerifiedToken]:
    return {}


@pytest.fixture
async def app(engine: AsyncEngine, tokens: dict[str, VerifiedToken]) -> FastAPI:
    settings = Settings(
        database_url=str(engine.url.render_as_string(hide_password=False)),
        firebase_project_id="test",
    )
    app = create_app(settings, token_verifier=fake_verifier(tokens))

    # 사용자 API 조건을 확인하려고 두 의존성을 붙인 경로를 둔다.
    @app.get(f"{API_PREFIX}/_test/verified")
    async def verified(
        _: Annotated[CurrentUser, Depends(require_verified_email)],
    ) -> dict[str, bool]:
        return {"ok": True}

    @app.get(f"{API_PREFIX}/_test/profile")
    async def profile(_: Annotated[CurrentUser, Depends(require_profile)]) -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await app.state.session_factory.kw["bind"].dispose()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def count_users(engine: AsyncEngine) -> int:
    async with make_session_factory(engine)() as db:
        return await db.scalar(select(func.count()).select_from(User)) or 0


async def get_user(engine: AsyncEngine, uid: str = "uid-1") -> User:
    async with make_session_factory(engine)() as db:
        return await db.scalar(select(User).where(User.firebase_uid == uid))  # pyright: ignore[reportReturnType]


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer"}, {"Authorization": "Bearer "}, {"Authorization": "Basic abc"}],
)
async def test_missing_token_is_unauthenticated(
    client: httpx.AsyncClient, engine: AsyncEngine, headers: dict[str, str]
) -> None:
    res = await client.get(f"{API_PREFIX}/me", headers=headers)
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "unauthenticated"
    assert await count_users(engine) == 0


async def test_invalid_token_is_unauthenticated(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    res = await client.get(f"{API_PREFIX}/me", headers=bearer("garbage"))
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "unauthenticated"
    assert await count_users(engine) == 0


async def test_first_request_creates_user_and_returns_me(
    client: httpx.AsyncClient, engine: AsyncEngine, tokens: dict[str, VerifiedToken]
) -> None:
    tokens["t"] = make_token(email_verified=False)
    res = await client.get(f"{API_PREFIX}/me", headers=bearer("t"))
    assert res.status_code == 200
    assert res.json() == {
        "nickname": None,
        "email": "a@example.com",
        "sign_in_provider": "password",
        "email_verified": False,
        "ai_consent_at": None,
        "avatar_url": None,
    }
    assert await count_users(engine) == 1


async def test_repeated_requests_keep_one_user(
    client: httpx.AsyncClient, engine: AsyncEngine, tokens: dict[str, VerifiedToken]
) -> None:
    tokens["t"] = make_token()
    for _ in range(3):
        assert (await client.get(f"{API_PREFIX}/me", headers=bearer("t"))).status_code == 200
    assert await count_users(engine) == 1


async def test_email_and_provider_are_synced(
    client: httpx.AsyncClient, engine: AsyncEngine, tokens: dict[str, VerifiedToken]
) -> None:
    tokens["old"] = make_token()
    await client.get(f"{API_PREFIX}/me", headers=bearer("old"))

    tokens["new"] = make_token(email="b@example.com", provider=SignInProvider.GOOGLE)
    res = await client.get(f"{API_PREFIX}/me", headers=bearer("new"))
    assert res.json()["email"] == "b@example.com"
    assert res.json()["sign_in_provider"] == "google.com"

    user = await get_user(engine)
    assert (user.email, user.sign_in_provider) == ("b@example.com", "google.com")
    assert await count_users(engine) == 1


async def test_token_issued_before_revocation_is_rejected(
    client: httpx.AsyncClient, engine: AsyncEngine, tokens: dict[str, VerifiedToken]
) -> None:
    tokens["old"] = make_token(auth_time=NOW - timedelta(hours=1))
    tokens["new"] = make_token(auth_time=NOW + timedelta(minutes=1))
    await client.get(f"{API_PREFIX}/me", headers=bearer("old"))
    async with make_session_factory(engine)() as db:
        await db.execute(update(User).values(tokens_revoked_at=NOW))
        await db.commit()

    res = await client.get(f"{API_PREFIX}/me", headers=bearer("old"))
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "token_revoked"
    # 폐기 이후에 다시 로그인한 토큰은 통과한다.
    assert (await client.get(f"{API_PREFIX}/me", headers=bearer("new"))).status_code == 200


async def test_unverified_email_is_forbidden(
    client: httpx.AsyncClient, tokens: dict[str, VerifiedToken]
) -> None:
    tokens["t"] = make_token(email_verified=False)
    for path in ("verified", "profile"):
        res = await client.get(f"{API_PREFIX}/_test/{path}", headers=bearer("t"))
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "email_not_verified"


async def test_missing_nickname_is_forbidden_until_set(
    client: httpx.AsyncClient, engine: AsyncEngine, tokens: dict[str, VerifiedToken]
) -> None:
    tokens["t"] = make_token()
    assert (
        await client.get(f"{API_PREFIX}/_test/verified", headers=bearer("t"))
    ).status_code == 200
    res = await client.get(f"{API_PREFIX}/_test/profile", headers=bearer("t"))
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "profile_required"

    async with make_session_factory(engine)() as db:
        await db.execute(update(User).values(nickname="학습자"))
        await db.commit()
    assert (await client.get(f"{API_PREFIX}/_test/profile", headers=bearer("t"))).status_code == 200


async def test_update_profile_sets_nickname(
    client: httpx.AsyncClient, engine: AsyncEngine, tokens: dict[str, VerifiedToken]
) -> None:
    tokens["t"] = make_token()
    res = await client.patch(
        f"{API_PREFIX}/me/profile", headers=bearer("t"), json={"nickname": "  학습자  "}
    )
    assert res.status_code == 200
    assert res.json()["nickname"] == "학습자"
    assert (await get_user(engine)).nickname == "학습자"
    # 이미 있는 닉네임도 바꿀 수 있다 (설정).
    res = await client.patch(
        f"{API_PREFIX}/me/profile", headers=bearer("t"), json={"nickname": "b"}
    )
    assert res.json()["nickname"] == "b"


@pytest.mark.parametrize("nickname", ["", "   ", "가" * 21, None, 3])
async def test_update_profile_rejects_invalid_nickname(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    tokens: dict[str, VerifiedToken],
    nickname: object,
) -> None:
    tokens["t"] = make_token()
    res = await client.patch(
        f"{API_PREFIX}/me/profile", headers=bearer("t"), json={"nickname": nickname}
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "validation_error"


async def test_update_profile_accepts_20_characters(
    client: httpx.AsyncClient, tokens: dict[str, VerifiedToken]
) -> None:
    tokens["t"] = make_token()
    res = await client.patch(
        f"{API_PREFIX}/me/profile", headers=bearer("t"), json={"nickname": "가" * 20}
    )
    assert res.status_code == 200


async def test_update_profile_requires_verified_email_and_token(
    client: httpx.AsyncClient, engine: AsyncEngine, tokens: dict[str, VerifiedToken]
) -> None:
    body = {"nickname": "학습자"}
    assert (await client.patch(f"{API_PREFIX}/me/profile", json=body)).status_code == 401

    tokens["t"] = make_token(email_verified=False)
    res = await client.patch(f"{API_PREFIX}/me/profile", headers=bearer("t"), json=body)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "email_not_verified"
    assert (await get_user(engine)).nickname is None
