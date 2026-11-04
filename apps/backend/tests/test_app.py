from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.errors import AppError
from backend.main import API_PREFIX, create_app

ORIGIN = "http://localhost:3000"
UNUSED_DATABASE_URL = "postgresql+asyncpg://user:pw@localhost/unused"  # 앱 생성은 접속하지 않는다


@pytest.fixture
def app() -> FastAPI:
    app = create_app(Settings(database_url=UNUSED_DATABASE_URL, cors_origins=[ORIGIN]))

    @app.get(f"{API_PREFIX}/_test/app-error")
    async def app_error() -> None:
        raise AppError(409, "invalid_state", "session is completed")

    @app.get(f"{API_PREFIX}/_test/validation")
    async def validation(n: int) -> dict[str, int]:
        return {"n": n}

    @app.get(f"{API_PREFIX}/_test/crash")
    async def crash() -> None:
        raise RuntimeError("boom")

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_health(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("path", "status", "code", "retryable"),
    [
        ("/_test/app-error", 409, "invalid_state", False),
        ("/_test/validation?n=abc", 400, "validation_error", False),
        ("/_test/crash", 500, "internal_error", True),
        ("/does-not-exist", 404, "not_found", False),
    ],
)
def test_error_format(
    client: TestClient, path: str, status: int, code: str, retryable: bool
) -> None:
    res = client.get(f"{API_PREFIX}{path}")
    assert res.status_code == status
    error = res.json()["error"]
    assert error["code"] == code
    assert error["retryable"] is retryable
    assert isinstance(error["message"], str)


def test_cors_allows_configured_origin_only(client: TestClient) -> None:
    preflight = {"Access-Control-Request-Method": "GET"}
    allowed = client.options("/health", headers={"Origin": ORIGIN, **preflight})
    assert allowed.headers["access-control-allow-origin"] == ORIGIN

    denied = client.options("/health", headers={"Origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in denied.headers


def test_cors_origins_from_comma_separated_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # 로컬 .env를 읽지 않게 한다
    monkeypatch.setenv("CORS_ORIGINS", f"{ORIGIN}, https://feynmi.vercel.app")
    settings = Settings()  # pyright: ignore[reportCallIssue]
    assert settings.cors_origins == [ORIGIN, "https://feynmi.vercel.app"]
