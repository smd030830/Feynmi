"""학습자료 업로드·분석 API를 실제 PostgreSQL로 확인한다 (PRD FR-1.1~1.8, FR-4.2).

로그인은 가짜 검증 함수, OCR은 가짜 엔진, 보관소는 임시 폴더, OpenAI는 가짜 제공자를 쓴다.
"""

import io
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from account_fakes import FakeCloud
from ai_fakes import FakeAI
from fastapi import FastAPI
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine
from test_ingest import make_pdf

from backend.api import materials as materials_api
from backend.auth.firebase import VerifiedToken
from backend.config import Settings
from backend.db.models import (
    Chunk,
    Concept,
    ConceptElement,
    ConceptMisconception,
    Material,
    User,
)
from backend.db.session import make_session_factory
from backend.domain.enums import SignInProvider
from backend.errors import AppError
from backend.ingest.config import OCRSettings
from backend.ingest.ocr import HybridOcr, OcrResult
from backend.llm import LLMError, LLMProvider, LLMSettings
from backend.main import API_PREFIX, create_app
from backend.services import analysis
from backend.services import materials as materials_service
from backend.services.concepts import CONCEPT_EXTRACTION_INSTRUCTIONS
from backend.services.storage import LocalStorage

pytestmark = pytest.mark.usefixtures("migrated_db")

ALICE, BOB = "alice", "bob"


def verify(token: str) -> VerifiedToken:
    if token not in (ALICE, BOB):
        raise AppError(401, "unauthenticated", "invalid id token")
    return VerifiedToken(
        token, f"{token}@example.com", True, SignInProvider.PASSWORD, datetime.now(UTC)
    )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class FakeEngine:
    def read(self, image: Image.Image) -> OcrResult:
        if image.convert("L").getextrema()[0] == 255:  # 새하얀 그림에는 글자가 없다
            return OcrResult("", None)
        return OcrResult("사진 속 프로세스 상태도", 95.0)


def fake_ocr(_: object = None) -> HybridOcr:
    return HybridOcr(FakeEngine(), OCRSettings(_env_file=None))  # pyright: ignore[reportCallIssue]


@pytest.fixture
async def app(engine: AsyncEngine, tmp_path: Path) -> AsyncIterator[FastAPI]:
    settings = Settings(
        database_url=str(engine.url.render_as_string(hide_password=False)),
        firebase_project_id="test",
    )
    app = create_app(settings, token_verifier=verify)
    app.state.account_cloud = FakeCloud()  # 새 사용자 Firebase 확인을 가짜로 (실제 구글 호출 안 함)
    app.state.storage = LocalStorage(tmp_path / "materials")
    app.state.ocr_factory = fake_ocr
    app.state.llm_settings = None  # 기본은 키 없음
    yield app
    await app.state.session_factory.kw["bind"].dispose()


@pytest.fixture
async def client(app: FastAPI, engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for token in (ALICE, BOB):
            await client.get(f"{API_PREFIX}/me", headers=auth(token))
        async with make_session_factory(engine)() as db:
            await db.execute(update(User).values(nickname="학습자"))
            await db.commit()
        yield client


async def consent(client: httpx.AsyncClient, token: str = ALICE) -> httpx.Response:
    return await client.post(f"{API_PREFIX}/me/ai-consent", headers=auth(token))


async def new_project(client: httpx.AsyncClient, token: str = ALICE) -> str:
    res = await client.post(
        f"{API_PREFIX}/projects", json={"name": "운영체제"}, headers=auth(token)
    )
    return res.json()["id"]


async def upload(
    client: httpx.AsyncClient, project_id: str, name: str, data: bytes, token: str = ALICE
) -> httpx.Response:
    return await client.post(
        f"{API_PREFIX}/projects/{project_id}/materials",
        files={"file": (name, data)},
        headers=auth(token),
    )


async def materials(client: httpx.AsyncClient, project_id: str, token: str = ALICE) -> list[dict]:
    res = await client.get(f"{API_PREFIX}/projects/{project_id}/materials", headers=auth(token))
    assert res.status_code == 200
    return res.json()["items"]


def png() -> bytes:
    out = io.BytesIO()
    image = Image.new("RGB", (640, 480), "white")
    image.paste((0, 0, 0), (100, 100, 300, 140))  # 글자 대신 검은 막대
    image.save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
async def project(client: httpx.AsyncClient) -> str:
    assert (await consent(client)).status_code == 200
    return await new_project(client)


# --- 동의 (FR-1.8) ---


async def test_upload_requires_ai_consent_once(client: httpx.AsyncClient) -> None:
    project_id = await new_project(client)
    res = await upload(client, project_id, "강의.pdf", make_pdf(["프로세스"]))
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "consent_required"
    assert await materials(client, project_id) == []

    first = (await consent(client)).json()["ai_consent_at"]
    assert first is not None
    assert (await consent(client)).json()["ai_consent_at"] == first  # 처음 시각 유지


# --- 정상 업로드 → 분석 ---


async def test_pdf_is_uploaded_analyzed_and_readable(
    client: httpx.AsyncClient, project: str
) -> None:
    res = await upload(client, project, "운영체제 3강.pdf", make_pdf(["프로세스 정의", "스레드"]))
    assert res.status_code == 202
    body = res.json()
    assert (body["title"], body["file_type"], body["status"]) == (
        "운영체제 3강.pdf",
        "pdf",
        "queued",
    )

    [item] = await materials(client, project)  # 분석은 응답 뒤 바로 끝난다
    assert item["status"] == "ready"
    assert item["page_count"] == 2
    assert item["failure_code"] is None
    assert item["chunk_count"] == 0  # 키가 없으면 임베딩을 건너뛴다

    pages = await client.get(f"{API_PREFIX}/materials/{item['id']}/pages", headers=auth(ALICE))
    assert pages.json()["pages"] == [
        {"number": 1, "text": "프로세스 정의"},
        {"number": 2, "text": "스레드"},
    ]

    project_res = await client.get(f"{API_PREFIX}/projects/{project}", headers=auth(ALICE))
    assert project_res.json()["material_count"] == 1


async def test_image_upload_is_read_by_ocr(client: httpx.AsyncClient, project: str) -> None:
    await upload(
        client, project, "필기.JPEG", png()
    )  # 확장자 대소문자 무관, 실제 형식은 내용으로 판단
    [item] = await materials(client, project)
    assert (item["file_type"], item["status"], item["page_count"]) == ("jpg", "ready", 1)
    pages = await client.get(f"{API_PREFIX}/materials/{item['id']}/pages", headers=auth(ALICE))
    assert pages.json()["pages"] == [{"number": 1, "text": "사진 속 프로세스 상태도"}]


async def test_newest_material_is_listed_first(client: httpx.AsyncClient, project: str) -> None:
    await upload(client, project, "첫째.pdf", make_pdf(["하나"]))
    await upload(client, project, "둘째.pdf", make_pdf(["둘"]))
    assert [m["title"] for m in await materials(client, project)] == ["둘째.pdf", "첫째.pdf"]


# --- 업로드 단계에서 막히는 예외 (사전 검증) ---


@pytest.mark.parametrize("name", ["보고서.doc", "강의.ppt", "표.xlsx", "움짤.gif", "확장자없음"])
async def test_unsupported_extensions_are_rejected(
    client: httpx.AsyncClient, project: str, name: str
) -> None:
    res = await upload(client, project, name, b"anything")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "unsupported_format"
    assert await materials(client, project) == []


async def test_too_large_file_is_rejected(
    client: httpx.AsyncClient, project: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(materials_service, "MAX_FILE_BYTES", 1000)
    monkeypatch.setattr(materials_api, "MAX_FILE_BYTES", 1000)
    res = await upload(client, project, "큰파일.pdf", b"%PDF-" + b"0" * 1000)
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "file_too_large"


async def test_empty_file_is_rejected(client: httpx.AsyncClient, project: str) -> None:
    res = await upload(client, project, "빈파일.pdf", b"")
    assert res.json()["error"]["code"] == "empty_file"


async def test_missing_file_field_is_a_validation_error(
    client: httpx.AsyncClient, project: str
) -> None:
    res = await client.post(
        f"{API_PREFIX}/projects/{project}/materials", data={"x": "1"}, headers=auth(ALICE)
    )
    assert res.json()["error"]["code"] == "validation_error"


# --- 분석 단계에서 실패하는 예외 (FR-1.4, FR-1.7) ---


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("사진인데.pdf", png(), "unsupported_format"),  # 확장자만 바꾼 파일
        ("깨짐.pdf", make_pdf(["가나다"])[:200], "corrupted_file"),
        ("빈문서.pdf", make_pdf(["", ""]), "no_extractable_text"),
        ("워드.pptx", b"PK\x03\x04 not a presentation", "corrupted_file"),
    ],
)
async def test_analysis_failures_are_reported(
    client: httpx.AsyncClient, project: str, name: str, data: bytes, code: str
) -> None:
    assert (await upload(client, project, name, data)).status_code == 202
    [item] = await materials(client, project)
    assert (item["status"], item["failure_code"]) == ("failed", code)


async def test_image_without_ocr_engine_fails_as_internal_error(
    app: FastAPI, client: httpx.AsyncClient, project: str
) -> None:
    app.state.ocr_factory = lambda _=None: None  # Tesseract 미설치 서버
    await upload(client, project, "사진.png", png())
    [item] = await materials(client, project)
    assert (item["status"], item["failure_code"]) == ("failed", "internal_error")


async def test_retry_only_from_failed_and_uses_kept_original(
    app: FastAPI, client: httpx.AsyncClient, project: str
) -> None:
    app.state.ocr_factory = lambda _=None: None
    await upload(client, project, "사진.png", png())
    [failed] = await materials(client, project)
    pages = await client.get(f"{API_PREFIX}/materials/{failed['id']}/pages", headers=auth(ALICE))
    assert pages.json()["error"]["code"] == "invalid_state"  # 끝나지 않은 자료는 볼 수 없다

    app.state.ocr_factory = fake_ocr  # 서버에 OCR을 설치한 뒤 재시도
    res = await client.post(f"{API_PREFIX}/materials/{failed['id']}/retry", headers=auth(ALICE))
    assert res.status_code == 202
    [item] = await materials(client, project)
    assert (item["status"], item["failure_code"]) == ("ready", None)

    again = await client.post(f"{API_PREFIX}/materials/{failed['id']}/retry", headers=auth(ALICE))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_state"


# --- 본인 자료만 (FR-4.2) ---


async def test_other_users_cannot_touch_materials(client: httpx.AsyncClient, project: str) -> None:
    await upload(client, project, "강의.pdf", make_pdf(["비밀"]))
    [item] = await materials(client, project)
    assert (await consent(client, BOB)).status_code == 200

    checks = [
        await upload(client, project, "남의것.pdf", make_pdf(["x"]), token=BOB),
        await client.get(f"{API_PREFIX}/projects/{project}/materials", headers=auth(BOB)),
        await client.post(f"{API_PREFIX}/materials/{item['id']}/retry", headers=auth(BOB)),
        await client.get(f"{API_PREFIX}/materials/{item['id']}/pages", headers=auth(BOB)),
        await upload(client, str(uuid.uuid4()), "없는곳.pdf", make_pdf(["x"])),
    ]
    assert [r.status_code for r in checks] == [404] * 5
    assert len(await materials(client, project)) == 1


async def test_login_is_required(client: httpx.AsyncClient, project: str) -> None:
    res = await client.get(f"{API_PREFIX}/projects/{project}/materials")
    assert res.status_code == 401


# --- 키가 있을 때: 임베딩 저장 ---


def llm_settings() -> LLMSettings:
    return LLMSettings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        openai_api_key=SecretStr("fake-test-key"),
        llm_concept_extraction_model="m",
        llm_concept_extraction_effort="low",
        llm_assessment_model="m",
        llm_assessment_effort="low",
        llm_embedding_model="m",
    )


def fake_provider_context(provider: Any) -> Any:
    @asynccontextmanager
    async def fake(_: LLMSettings) -> AsyncIterator[Any]:
        yield provider

    return fake


async def test_chunks_are_embedded_and_stored_when_llm_is_configured(
    app: FastAPI, client: httpx.AsyncClient, project: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = AsyncMock(spec=LLMProvider)

    async def embed(texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 1535 for _ in texts]

    provider.embed.side_effect = embed
    provider.generate_structured.side_effect = FakeAI().generate_structured
    monkeypatch.setattr(analysis, "openai_provider", fake_provider_context(provider))
    app.state.llm_settings = llm_settings()

    await upload(client, project, "강의.pdf", make_pdf(["프로세스", "스레드"]))
    [item] = await materials(client, project)
    assert (item["status"], item["chunk_count"]) == ("ready", 2)


async def test_llm_failure_is_reported_and_retry_replaces_chunks(
    app: FastAPI, client: httpx.AsyncClient, project: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = AsyncMock(spec=LLMProvider)
    provider.embed.side_effect = LLMError("down")
    provider.generate_structured.side_effect = FakeAI().generate_structured
    monkeypatch.setattr(analysis, "openai_provider", fake_provider_context(provider))
    app.state.llm_settings = llm_settings()

    await upload(client, project, "강의.pdf", make_pdf(["프로세스"]))
    [item] = await materials(client, project)
    assert (item["status"], item["failure_code"], item["chunk_count"]) == (
        "failed",
        "llm_failed",
        0,
    )

    async def embed(texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 1535 for _ in texts]

    provider.embed.side_effect = embed
    await client.post(f"{API_PREFIX}/materials/{item['id']}/retry", headers=auth(ALICE))
    [item] = await materials(client, project)
    assert (item["status"], item["chunk_count"]) == ("ready", 1)


# --- 개념 추출 (FM-022, PRD FR-1.5, 6.1①, architecture 6.3) ---


@pytest.fixture
def ai(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> FakeAI:
    fake = FakeAI()
    monkeypatch.setattr(analysis, "openai_provider", fake_provider_context(fake))
    app.state.llm_settings = llm_settings()
    return fake


async def concepts(client: httpx.AsyncClient, project_id: str) -> list[dict]:
    res = await client.get(f"{API_PREFIX}/projects/{project_id}/concepts", headers=auth(ALICE))
    assert res.status_code == 200
    return res.json()["items"]


async def count(engine: AsyncEngine, model: type) -> int:
    async with make_session_factory(engine)() as db:
        return await db.scalar(select(func.count()).select_from(model)) or 0


async def test_concepts_are_saved_with_real_chunk_ids(
    ai: FakeAI, client: httpx.AsyncClient, project: str, engine: AsyncEngine
) -> None:
    await upload(client, project, "강의.pdf", make_pdf(["프로세스", "스레드"]))
    [item] = await materials(client, project)
    assert (item["status"], item["chunk_count"]) == ("ready", 2)

    # 입력: 청크 전체를 한 번에, 라벨과 쪽 번호를 붙여서 (PRD 9.4)
    [sent] = ai.extraction_inputs
    assert sent["material_title"] == "강의.pdf"
    assert [(c["label"], c["pages"]) for c in sent["chunks"]] == [("C1", "1쪽"), ("C2", "2쪽")]
    assert "프로세스" in sent["chunks"][0]["text"]

    listed = await concepts(client, project)
    assert [c["title"] for c in listed] == [f"개념 {n}" for n in range(1, 6)]
    assert {c["state"] for c in listed} == {"not_studied"}
    assert {c["score"] for c in listed} == {None}
    assert {c["material_title"] for c in listed} == {"강의.pdf"}

    async with make_session_factory(engine)() as db:
        chunk_ids = list((await db.scalars(select(Chunk.id).order_by(Chunk.ordinal))).all())
        elements = {e.text: e for e in (await db.scalars(select(ConceptElement))).all()}
        [misconception] = (await db.scalars(select(ConceptMisconception))).all()
    assert len(elements) == 15
    assert elements["핵심 1"].importance == "core"
    assert elements["보충 1-1"].importance == "supporting"
    assert elements["핵심 1"].evidence_chunk_ids == [chunk_ids[0]]  # 라벨 → 실제 chunk_id
    assert elements["보충 1-1"].evidence_chunk_ids == [chunk_ids[1]]  # 같은 근거는 한 번만
    assert elements["보충 1-2"].evidence_chunk_ids == chunk_ids
    assert misconception.evidence_chunk_ids == [chunk_ids[0]]


async def test_extraction_failure_then_retry(
    ai: FakeAI, client: httpx.AsyncClient, project: str, engine: AsyncEngine
) -> None:
    ai.fail_extraction = True
    await upload(client, project, "강의.pdf", make_pdf(["프로세스"]))
    [item] = await materials(client, project)
    assert (item["status"], item["failure_code"]) == ("failed", "llm_failed")
    assert await concepts(client, project) == []
    assert await count(engine, Concept) == 0

    ai.fail_extraction = False
    ai.concepts = 7
    res = await client.post(f"{API_PREFIX}/materials/{item['id']}/retry", headers=auth(ALICE))
    assert res.status_code == 202
    [item] = await materials(client, project)
    assert (item["status"], item["chunk_count"]) == ("ready", 1)
    assert len(await concepts(client, project)) == 7


async def test_retry_replaces_concepts_instead_of_adding(
    ai: FakeAI, client: httpx.AsyncClient, project: str, engine: AsyncEngine
) -> None:
    await upload(client, project, "강의.pdf", make_pdf(["프로세스"]))
    [item] = await materials(client, project)
    async with make_session_factory(engine)() as db:  # 다시 분석해야 하는 상황
        await db.execute(update(Material).values(status="failed", failure_code="internal_error"))
        await db.commit()
    await client.post(f"{API_PREFIX}/materials/{item['id']}/retry", headers=auth(ALICE))
    assert len(await concepts(client, project)) == 5
    assert await count(engine, Concept) == 5
    assert await count(engine, ConceptElement) == 15
    assert await count(engine, Chunk) == 1


async def test_unknown_evidence_label_fails_without_saving(
    ai: FakeAI, client: httpx.AsyncClient, project: str, engine: AsyncEngine
) -> None:
    ai.bad_label = True  # 입력에 없는 청크를 근거로 댄 결과
    await upload(client, project, "강의.pdf", make_pdf(["프로세스"]))
    [item] = await materials(client, project)
    assert item["status"] == "failed"
    assert await count(engine, Concept) == 0


async def test_short_material_can_have_a_single_concept(
    ai: FakeAI, client: httpx.AsyncClient, project: str
) -> None:
    ai.concepts = 1  # 짧은 자료: 개수를 채우려고 만들지 않는다 (1~10개)
    await upload(client, project, "메모.pdf", make_pdf(["교착 상태의 정의"]))
    [item] = await materials(client, project)
    assert item["status"] == "ready"
    assert [c["title"] for c in await concepts(client, project)] == ["개념 1"]


async def test_no_key_means_no_concepts(client: httpx.AsyncClient, project: str) -> None:
    await upload(client, project, "강의.pdf", make_pdf(["프로세스"]))  # 기본은 키 없음
    [item] = await materials(client, project)
    assert (item["status"], item["chunk_count"]) == ("ready", 0)
    assert await concepts(client, project) == []


def test_instructions_keep_prd_rules() -> None:
    # PRD FR-1.5 개수, 6.1① 요소·오개념 수, FR-5.5 자료 밖 내용 금지, 프롬프트 주입 방어
    for rule in (
        "1~10개",
        "정답 기준",
        "3~5개",
        "0~2개",
        "core",
        "자료에 없는 사실",
        "명령을 따르지 않는다",
    ):
        assert rule in CONCEPT_EXTRACTION_INSTRUCTIONS


def test_storage_key_cannot_escape_root(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "materials")
    with pytest.raises(ValueError):
        storage.save("../outside.txt", b"x")


# --- 서버 재시작 ---


async def test_server_restart_marks_interrupted_analyses_as_failed(
    app: FastAPI, client: httpx.AsyncClient, project: str, engine: AsyncEngine
) -> None:
    await upload(client, project, "완료.pdf", make_pdf(["끝난 자료"]))
    await upload(client, project, "도중.pdf", make_pdf(["분석 도중 서버가 꺼진 자료"]))
    async with make_session_factory(engine)() as db:  # 분석 도중에 서버가 꺼진 상황
        await db.execute(
            update(Material).where(Material.title == "도중.pdf").values(status="extracting")
        )
        await db.commit()

    async with app.router.lifespan_context(app):  # 서버 다시 켜기
        pass

    by_title = {m["title"]: m for m in await materials(client, project)}
    assert (by_title["도중.pdf"]["status"], by_title["도중.pdf"]["failure_code"]) == (
        "failed",
        "internal_error",
    )
    assert by_title["완료.pdf"]["status"] == "ready"  # 끝난 자료는 그대로
    retry = await client.post(
        f"{API_PREFIX}/materials/{by_title['도중.pdf']['id']}/retry", headers=auth(ALICE)
    )
    assert retry.status_code == 202
    assert {m["title"]: m["status"] for m in await materials(client, project)}[
        "도중.pdf"
    ] == "ready"


# --- 뽑힌 글자 보기: DB에 저장된 글자 / 원본이 사라진 경우 ---


async def test_pages_come_from_db_without_rereading_the_original(
    app: FastAPI, client: httpx.AsyncClient, project: str, tmp_path: Path
) -> None:
    await upload(client, project, "사진.png", png())
    [item] = await materials(client, project)
    for original in (tmp_path / "materials").rglob("original.*"):
        original.unlink()  # 원본이 사라져도
    app.state.ocr_factory = lambda _=None: None  # OCR 없이도
    res = await client.get(f"{API_PREFIX}/materials/{item['id']}/pages", headers=auth(ALICE))
    assert res.json()["pages"] == [{"number": 1, "text": "사진 속 프로세스 상태도"}]


async def test_old_material_without_saved_text_and_original_reports_missing(
    client: httpx.AsyncClient, project: str, tmp_path: Path, engine: AsyncEngine
) -> None:
    await upload(client, project, "강의.pdf", make_pdf(["본문"]))
    [item] = await materials(client, project)
    async with make_session_factory(engine)() as db:  # 글자 저장 기능 전에 분석된 자료
        await db.execute(update(Material).values(page_texts=None))
        await db.commit()
    for original in (tmp_path / "materials").rglob("original.*"):
        original.unlink()
    res = await client.get(f"{API_PREFIX}/materials/{item['id']}/pages", headers=auth(ALICE))
    assert (res.status_code, res.json()["error"]["code"]) == (409, "original_missing")
