"""프로젝트 API를 실제 PostgreSQL로 확인한다 (PRD FR-1.0, FR-4.2)."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.auth.firebase import VerifiedToken
from backend.config import Settings
from backend.db.models import Concept, Material, Project, User
from backend.db.session import make_session_factory
from backend.domain.enums import ConceptState, MaterialStatus, SignInProvider
from backend.domain.projects import next_project_color
from backend.errors import AppError
from backend.main import API_PREFIX, create_app

pytestmark = pytest.mark.usefixtures("migrated_db")

URL = f"{API_PREFIX}/projects"

# 토큰 문자열이 곧 uid다. NO_NICKNAME만 닉네임을 정하지 않은 계정이다.
ALICE, BOB, NO_NICKNAME = "alice", "bob", "no-nickname"


def verify(token: str) -> VerifiedToken:
    if token not in (ALICE, BOB, NO_NICKNAME):
        raise AppError(401, "unauthenticated", "invalid id token")
    return VerifiedToken(
        token, f"{token}@example.com", True, SignInProvider.PASSWORD, datetime.now(UTC)
    )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        database_url=str(engine.url.render_as_string(hide_password=False)),
        firebase_project_id="test",
    )
    app: FastAPI = create_app(settings, token_verifier=verify)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 첫 요청으로 사용자 행을 만들고 닉네임을 채운다.
        for token in (ALICE, BOB, NO_NICKNAME):
            await client.get(f"{API_PREFIX}/me", headers=auth(token))
        async with make_session_factory(engine)() as db:
            await db.execute(
                update(User).where(User.firebase_uid != NO_NICKNAME).values(nickname="학습자")
            )
            await db.commit()
        yield client
    await app.state.session_factory.kw["bind"].dispose()


async def create(client: httpx.AsyncClient, token: str = ALICE, **body: object) -> httpx.Response:
    return await client.post(URL, json={"name": "운영체제", **body}, headers=auth(token))


def test_colors_cycle_in_prd_order() -> None:
    assert [next_project_color(n) for n in range(4)] == ["indigo", "lavender", "cyan", "indigo"]


async def test_create_project(client: httpx.AsyncClient) -> None:
    res = await create(client, name="  운영체제  ", description="  프로세스와 스레드 ")
    assert res.status_code == 201
    body = res.json()
    uuid.UUID(body.pop("id"))
    assert body.pop("created_at")
    assert body == {
        "name": "운영체제",
        "description": "프로세스와 스레드",
        "color": "indigo",
        "score": None,
        "state_counts": {"understood": 0, "partial": 0, "misconception": 0, "not_studied": 0},
        "material_count": 0,
    }


@pytest.mark.parametrize("description", [None, "", "   "])
async def test_blank_description_is_null(
    client: httpx.AsyncClient, description: str | None
) -> None:
    res = await create(client, description=description)
    assert res.status_code == 201
    assert res.json()["description"] is None


@pytest.mark.parametrize(
    "body",
    [{"name": ""}, {"name": "   "}, {"name": "가" * 41}, {"description": "가" * 201}, {}],
)
async def test_invalid_body_is_rejected(client: httpx.AsyncClient, body: dict[str, str]) -> None:
    payload = {"name": "운영체제", **body} if body else {}
    res = await client.post(URL, json=payload, headers=auth(ALICE))
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "validation_error"


async def test_colors_are_assigned_per_user(client: httpx.AsyncClient) -> None:
    colors = [(await create(client)).json()["color"] for _ in range(4)]
    assert colors == ["indigo", "lavender", "cyan", "indigo"]
    # 다른 사용자의 프로젝트 수는 영향을 주지 않는다.
    assert (await create(client, BOB)).json()["color"] == "indigo"


async def test_list_returns_own_projects_newest_first(client: httpx.AsyncClient) -> None:
    res = await client.get(URL, headers=auth(ALICE))
    assert res.json() == {"items": [], "next_color": "indigo"}

    first = (await create(client, name="운영체제")).json()
    second = (await create(client, name="자료구조")).json()
    await create(client, BOB, name="남의 프로젝트")

    body = (await client.get(URL, headers=auth(ALICE))).json()
    assert [p["id"] for p in body["items"]] == [second["id"], first["id"]]
    assert body["next_color"] == "cyan"


async def test_get_project(client: httpx.AsyncClient) -> None:
    created = (await create(client)).json()
    res = await client.get(f"{URL}/{created['id']}", headers=auth(ALICE))
    assert res.status_code == 200
    assert res.json() == created


async def test_other_users_project_is_not_found(client: httpx.AsyncClient) -> None:
    created = (await create(client)).json()
    for path in (created["id"], str(uuid.uuid4())):
        res = await client.get(f"{URL}/{path}", headers=auth(BOB))
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "not_found"


async def test_invalid_project_id_is_rejected(client: httpx.AsyncClient) -> None:
    res = await client.get(f"{URL}/not-a-uuid", headers=auth(ALICE))
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "validation_error"


async def test_profile_is_required(client: httpx.AsyncClient) -> None:
    for res in (
        await client.get(URL, headers=auth(NO_NICKNAME)),
        await create(client, NO_NICKNAME),
    ):
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "profile_required"


async def test_counts_concepts_and_materials(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    created = (await create(client)).json()
    empty = (await create(client, name="빈 프로젝트")).json()
    async with make_session_factory(engine)() as db:
        project = await db.scalar(select(Project).where(Project.id == uuid.UUID(created["id"])))
        assert project is not None
        materials = [
            Material(
                project_id=project.id,
                title=f"자료 {i}",
                file_type="pdf",
                gcs_path=f"p/{i}",
                size_bytes=1,
                status=MaterialStatus.READY,
            )
            for i in range(2)
        ]
        db.add_all(materials)
        await db.flush()
        states = [
            ConceptState.UNDERSTOOD,
            ConceptState.PARTIAL,
            ConceptState.PARTIAL,
            ConceptState.NOT_STUDIED,
        ]
        db.add_all(
            Concept(
                material_id=materials[i % 2].id,
                ordinal=i,
                title=f"개념 {i}",
                description="d",
                state=state,
            )
            for i, state in enumerate(states)
        )
        await db.commit()

    detail = (await client.get(f"{URL}/{created['id']}", headers=auth(ALICE))).json()
    assert detail["state_counts"] == {
        "understood": 1,
        "partial": 2,
        "misconception": 0,
        "not_studied": 1,
    }
    assert detail["material_count"] == 2

    items = (await client.get(URL, headers=auth(ALICE))).json()["items"]
    by_id = {p["id"]: p for p in items}
    assert by_id[created["id"]]["state_counts"] == detail["state_counts"]
    assert by_id[empty["id"]]["material_count"] == 0
    assert sum(by_id[empty["id"]]["state_counts"].values()) == 0
