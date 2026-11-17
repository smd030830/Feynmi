"""학습자료 업로드·분석 API를 실제 PostgreSQL로 확인한다 (PRD FR-1.1~1.8, FR-4.2).

로그인은 가짜 검증 함수, OCR은 가짜 엔진, 보관소는 메모리(GCS 대신), OpenAI는 가짜 제공자를 쓴다.
업로드는 architecture 7.1 세 단계(upload-url → 저장소에 PUT → upload-complete)를 그대로 거친다.
"""

import io
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
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

from backend.auth.firebase import VerifiedToken
from backend.config import Settings
from backend.db.models import (
    Assessment,
    AssessmentElement,
    Chunk,
    Concept,
    ConceptElement,
    ConceptMisconception,
    Material,
    Message,
    Session,
    User,
)
from backend.db.session import make_session_factory
from backend.domain.enums import ConceptState, Importance, SessionStatus, SignInProvider, Verdict
from backend.errors import AppError
from backend.ingest.config import OCRSettings
from backend.ingest.ocr import HybridOcr, OcrResult
from backend.llm import LLMError, LLMProvider, LLMSettings
from backend.main import API_PREFIX, create_app
from backend.queue import make_queue
from backend.queue.cloud_tasks import CloudTasksQueue
from backend.services import analysis
from backend.services import materials as materials_service
from backend.services.concepts import CONCEPT_EXTRACTION_INSTRUCTIONS
from backend.storage import UploadTarget, make_storage
from backend.storage.gcs import EmulatorStorage, GcsStorage, UnconfiguredStorage

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


class FakeStorage:
    """GCS 대신 메모리. 업로드 주소는 가짜이고, 시험이 브라우저 대신 `files`에 직접 넣는다."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.targets: dict[str, str] = {}  # 업로드 주소 → 객체 경로
        self.deletion_fails = False

    def upload_target(self, key: str, content_type: str, max_bytes: int) -> UploadTarget:
        url = f"https://upload.invalid/{len(self.targets)}"
        self.targets[url] = key
        return UploadTarget(
            url, {"Content-Type": content_type, "x-goog-content-length-range": f"0,{max_bytes}"}
        )

    def put(self, url: str, data: bytes) -> None:
        self.files[self.targets[url]] = data

    def size(self, key: str) -> int | None:
        return len(self.files[key]) if key in self.files else None

    def load(self, key: str) -> bytes:
        if key not in self.files:
            raise FileNotFoundError(key)
        return self.files[key]

    def delete(self, key: str) -> None:
        if self.deletion_fails:
            raise RuntimeError("storage unavailable")
        self.files.pop(key, None)


class FakeQueue:
    def __init__(self) -> None:
        self.tasks: list[tuple[uuid.UUID, int]] = []
        self.fail = False

    def enqueue(self, material_id: uuid.UUID, attempt: int) -> None:
        if self.fail:
            raise RuntimeError("cloud tasks unavailable")
        self.tasks.append((material_id, attempt))


STORAGE = FakeStorage()


@pytest.fixture
async def app(engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    global STORAGE
    STORAGE = FakeStorage()
    settings = Settings(
        database_url=str(engine.url.render_as_string(hide_password=False)),
        firebase_project_id="test",
    )
    app = create_app(settings, token_verifier=verify)
    app.state.account_cloud = FakeCloud()  # 새 사용자 Firebase 확인을 가짜로 (실제 구글 호출 안 함)
    app.state.storage = STORAGE
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


async def upload_url(
    client: httpx.AsyncClient, project_id: str, name: str, size: int, token: str = ALICE
) -> httpx.Response:
    return await client.post(
        f"{API_PREFIX}/projects/{project_id}/materials/upload-url",
        json={"filename": name, "size": size},
        headers=auth(token),
    )


async def complete(
    client: httpx.AsyncClient, material_id: str, token: str = ALICE
) -> httpx.Response:
    return await client.post(
        f"{API_PREFIX}/materials/{material_id}/upload-complete", headers=auth(token)
    )


async def upload(
    client: httpx.AsyncClient, project_id: str, name: str, data: bytes, token: str = ALICE
) -> httpx.Response:
    """화면과 같은 세 단계. 첫 단계에서 막히면 그 응답을 돌려준다."""
    res = await upload_url(client, project_id, name, len(data), token)
    if res.status_code != 200:
        return res
    STORAGE.put(res.json()["upload_url"], data)  # 브라우저가 저장소에 직접 PUT
    return await complete(client, res.json()["material_id"], token)


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
    assert item["status"] == "failed"
    assert item["page_count"] == 2
    assert item["failure_code"] == "ai_unavailable"
    assert item["chunk_count"] == 0  # AI 설정이 없으면 완료로 처리하지 않는다

    project_res = await client.get(f"{API_PREFIX}/projects/{project}", headers=auth(ALICE))
    assert project_res.json()["material_count"] == 1


async def test_image_upload_is_read_by_ocr(client: httpx.AsyncClient, project: str) -> None:
    await upload(
        client, project, "필기.JPEG", png()
    )  # 확장자 대소문자 무관, 실제 형식은 내용으로 판단
    [item] = await materials(client, project)
    assert (item["file_type"], item["status"], item["page_count"]) == ("jpg", "failed", 1)
    assert item["failure_code"] == "ai_unavailable"


async def test_newest_material_is_listed_first(client: httpx.AsyncClient, project: str) -> None:
    await upload(client, project, "첫째.pdf", make_pdf(["하나"]))
    await upload(client, project, "둘째.pdf", make_pdf(["둘"]))
    assert [m["title"] for m in await materials(client, project)] == ["둘째.pdf", "첫째.pdf"]


@pytest.mark.parametrize("status", [SessionStatus.COMPLETED, SessionStatus.IN_PROGRESS])
async def test_deleting_material_preserves_answered_session_with_evidence(
    client: httpx.AsyncClient,
    project: str,
    engine: AsyncEngine,
    status: SessionStatus,
) -> None:
    key = "archive-test.pdf"
    STORAGE.files[key] = b"test source"
    async with make_session_factory(engine)() as db:
        alice_id = (
            await db.execute(select(User.id).where(User.firebase_uid == ALICE))
        ).scalar_one()
        material = Material(
            project_id=uuid.UUID(project),
            title="원본.pdf",
            file_type="pdf",
            status="ready",
            gcs_path=key,
            size_bytes=11,
        )
        db.add(material)
        await db.flush()
        concept = Concept(material_id=material.id, ordinal=0, title="개념", description="기준 설명")
        chunk = Chunk(
            material_id=material.id,
            project_id=material.project_id,
            ordinal=0,
            page_start=2,
            page_end=3,
            text="자료 본문",
            token_count=1,
            embedding=[1.0, *([0.0] * 1535)],
        )
        db.add_all([concept, chunk])
        await db.flush()
        element = ConceptElement(
            concept_id=concept.id, ordinal=0, text="채점 요소", importance=Importance.CORE
        )
        answered = Session(
            concept_id=concept.id,
            user_id=alice_id,
            status=status,
            ended_at=datetime.now(UTC) if status == SessionStatus.COMPLETED else None,
        )
        empty = Session(concept_id=concept.id, user_id=alice_id, status=SessionStatus.ABORTED)
        db.add_all([element, answered, empty])
        await db.flush()
        answer = Message(
            session_id=answered.id, seq=0, role="answer", text="학습 답변", confidence="high"
        )
        db.add(answer)
        await db.flush()
        assessment = Assessment(
            session_id=answered.id,
            answer_message_id=answer.id,
            seq=0,
            state=ConceptState.UNDERSTOOD,
            score=100,
            model_id="test-model",
            raw_output={},
        )
        db.add(assessment)
        await db.flush()
        db.add(
            AssessmentElement(
                assessment_id=assessment.id,
                element_id=element.id,
                verdict=Verdict.MET,
                learner_quote=answer.text,
                evidence_chunk_ids=[chunk.id],
            )
        )
        await db.commit()

    source = f"{API_PREFIX}/materials/{material.id}"
    detail = f"{API_PREFIX}/sessions/{answered.id}"
    assert (await client.delete(source, headers=auth(BOB))).status_code == 404
    STORAGE.deletion_fails = True
    assert (await client.delete(source, headers=auth(ALICE))).status_code == 503
    current = (await client.get(detail, headers=auth(ALICE))).json()
    assert current["concept_available"] is True
    assert current["status"] == status
    assert key in STORAGE.files

    STORAGE.deletion_fails = False
    if status == SessionStatus.IN_PROGRESS:
        async with make_session_factory(engine)() as db:
            await db.execute(
                update(Session)
                .where(Session.id == answered.id)
                .values(evaluating_since=datetime.now(UTC))
            )
            await db.commit()
        busy = await client.delete(source, headers=auth(ALICE))
        assert busy.status_code == 409
        assert busy.json()["error"]["code"] == "evaluation_in_progress"
        assert key in STORAGE.files
        async with make_session_factory(engine)() as db:
            await db.execute(
                update(Session).where(Session.id == answered.id).values(evaluating_since=None)
            )
            await db.commit()
    assert (await client.delete(source, headers=auth(ALICE))).status_code == 204
    assert key not in STORAGE.files
    assert await materials(client, project) == []
    assert (
        await client.get(f"{API_PREFIX}/sessions/{empty.id}", headers=auth(ALICE))
    ).status_code == 404
    assert (await client.get(detail, headers=auth(BOB))).status_code == 404
    result = await client.get(detail, headers=auth(ALICE))
    assert result.status_code == 200
    archive = result.json()
    assert archive["concept_available"] is False
    assert archive["status"] == ("completed" if status == SessionStatus.COMPLETED else "aborted")
    assert archive["concept_id"] == str(concept.id)
    assert archive["recommendation"] is None
    assert archive["messages"] == current["messages"]
    assert archive["assessments"] == current["assessments"]
    assert archive["assessments"][0]["elements"][0]["evidence"][0]["page_start"] == 2
    results = await client.get(f"{detail}/result", headers=auth(ALICE))
    assert results.status_code == (200 if status == SessionStatus.COMPLETED else 409)
    async with make_session_factory(engine)() as db:
        assert await db.get(Concept, concept.id) is None
        assert await db.get(Chunk, chunk.id) is None


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
    res = await upload(client, project, "큰파일.pdf", b"%PDF-" + b"0" * 1000)
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "file_too_large"
    assert await materials(client, project) == []


async def test_empty_file_is_rejected(client: httpx.AsyncClient, project: str) -> None:
    res = await upload(client, project, "빈파일.pdf", b"")
    assert res.json()["error"]["code"] == "empty_file"


async def test_missing_size_is_a_validation_error(client: httpx.AsyncClient, project: str) -> None:
    res = await client.post(
        f"{API_PREFIX}/projects/{project}/materials/upload-url",
        json={"filename": "강의.pdf"},
        headers=auth(ALICE),
    )
    assert res.json()["error"]["code"] == "validation_error"


# --- 업로드 세 단계 (architecture 7.1) ---


async def test_upload_url_signs_type_and_size_limit(
    client: httpx.AsyncClient, project: str
) -> None:
    res = await upload_url(client, project, "보고서.hwp", 1234)
    assert res.status_code == 200
    body = res.json()
    # 브라우저가 형식을 모르는 HWP도 서버가 정한 형식으로 서명한다
    assert body["required_headers"] == {
        "Content-Type": "application/x-hwp",
        "x-goog-content-length-range": "0,52428800",
    }
    assert body["material"]["status"] == "pending_upload"
    [item] = await materials(client, project)
    assert (item["id"], item["status"]) == (body["material_id"], "pending_upload")


async def test_complete_before_upload_is_rejected_then_works(
    client: httpx.AsyncClient, project: str
) -> None:
    res = await upload_url(client, project, "강의.pdf", 10)
    material_id = res.json()["material_id"]
    early = await complete(client, material_id)
    assert (early.status_code, early.json()["error"]["code"]) == (409, "upload_missing")
    [item] = await materials(client, project)
    assert item["status"] == "pending_upload"  # 분석은 시작하지 않는다

    STORAGE.put(res.json()["upload_url"], make_pdf(["프로세스"]))
    assert (await complete(client, material_id)).status_code == 202
    [item] = await materials(client, project)
    assert (item["status"], item["failure_code"]) == ("failed", "ai_unavailable")


async def test_complete_twice_does_not_analyze_twice(
    app: FastAPI, client: httpx.AsyncClient, project: str
) -> None:
    queue = FakeQueue()
    app.state.analysis_queue = queue
    res = await upload(client, project, "강의.pdf", make_pdf(["프로세스"]))
    again = await complete(client, res.json()["id"])
    assert again.status_code == 202
    assert len(queue.tasks) == 1


async def test_actual_size_over_the_limit_fails(
    client: httpx.AsyncClient, project: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 에뮬레이터는 크기 범위를 강제하지 않는다: 신고보다 큰 파일을 올린 경우
    monkeypatch.setattr(materials_service, "MAX_FILE_BYTES", 1000)
    res = await upload_url(client, project, "강의.pdf", 10)
    STORAGE.put(res.json()["upload_url"], b"%PDF-" + b"0" * 1000)
    done = await complete(client, res.json()["material_id"])
    assert (done.json()["status"], done.json()["failure_code"]) == ("failed", "file_too_large")


async def test_unconfigured_storage_gives_a_clear_error(
    app: FastAPI, client: httpx.AsyncClient, project: str
) -> None:
    app.state.storage = UnconfiguredStorage()
    res = await upload_url(client, project, "강의.pdf", 10)
    assert (res.status_code, res.json()["error"]["code"]) == (503, "storage_unavailable")
    assert await materials(client, project) == []


def settings_for(**values: str) -> Settings:
    # compose가 넣는 환경변수(GCS_EMULATOR_URL, QUEUE_MODE 등)와 상관없이 정한 값만 쓴다
    defaults = {"gcs_bucket": "", "gcs_emulator_url": "", "gcs_emulator_public_url": ""}
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url="x",
        firebase_project_id="p",
        **{"queue_mode": "inline", **defaults, **values},
    )


def test_storage_is_chosen_from_settings() -> None:
    assert isinstance(make_storage(settings_for(gcs_bucket="dev-bucket")), GcsStorage)
    emulator = settings_for(
        gcs_emulator_url="http://gcs:4443", gcs_emulator_public_url="http://localhost:4443"
    )
    assert isinstance(make_storage(emulator), EmulatorStorage)
    # 버킷이 있으면 에뮬레이터가 켜져 있어도 실제 버킷을 쓴다
    both = settings_for(gcs_bucket="dev-bucket", gcs_emulator_url="http://gcs:4443")
    assert isinstance(make_storage(both), GcsStorage)
    assert isinstance(make_storage(settings_for()), UnconfiguredStorage)


def test_emulator_upload_url_is_reachable_from_the_browser() -> None:
    storage = EmulatorStorage("http://gcs:4443", "http://localhost:4443")
    storage._bucket = object()  # 에뮬레이터 연결 없이 주소 모양만 본다
    target = storage.upload_target("users/u/a b.pdf", "application/pdf", 100)
    assert target.url == (
        "http://localhost:4443/feynmi-local/users%2Fu%2Fa%20b.pdf"
        "?uploadType=media&name=users%2Fu%2Fa%20b.pdf"
    )
    assert target.headers["Content-Type"] == "application/pdf"


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

    app.state.ocr_factory = fake_ocr  # 서버에 OCR을 설치한 뒤 재시도
    res = await client.post(f"{API_PREFIX}/materials/{failed['id']}/retry", headers=auth(ALICE))
    assert res.status_code == 202
    [item] = await materials(client, project)
    assert (item["status"], item["failure_code"]) == ("failed", "ai_unavailable")

    again = await client.post(f"{API_PREFIX}/materials/{failed['id']}/retry", headers=auth(ALICE))
    assert again.status_code == 202  # AI 미설정으로 여전히 실패 상태이므로 다시 시도할 수 있다
    [retried] = await materials(client, project)
    assert (retried["status"], retried["failure_code"]) == ("failed", "ai_unavailable")
    assert again.json()["status"] == "queued"


# --- 본인 자료만 (FR-4.2) ---


async def test_other_users_cannot_touch_materials(client: httpx.AsyncClient, project: str) -> None:
    await upload(client, project, "강의.pdf", make_pdf(["비밀"]))
    [item] = await materials(client, project)
    assert (await consent(client, BOB)).status_code == 200

    checks = [
        await upload(client, project, "남의것.pdf", make_pdf(["x"]), token=BOB),
        await client.get(f"{API_PREFIX}/projects/{project}/materials", headers=auth(BOB)),
        await client.post(f"{API_PREFIX}/materials/{item['id']}/retry", headers=auth(BOB)),
        await client.delete(f"{API_PREFIX}/materials/{item['id']}", headers=auth(BOB)),
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
    assert (item["status"], item["chunk_count"]) == ("failed", 0)
    assert item["failure_code"] == "ai_unavailable"
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


# --- 멈춘 작업 (architecture 7.1) ---


async def test_stalled_analysis_is_reported_as_failed_and_can_retry(
    client: httpx.AsyncClient, project: str, engine: AsyncEngine
) -> None:
    await upload(client, project, "완료.pdf", make_pdf(["끝난 자료"]))
    await upload(client, project, "도중.pdf", make_pdf(["분석 도중 멈춘 자료"]))
    await upload(client, project, "방금.pdf", make_pdf(["막 시작한 자료"]))
    async with make_session_factory(engine)() as db:
        old = datetime.now(UTC) - timedelta(minutes=31)
        await db.execute(
            update(Material)
            .where(Material.title == "도중.pdf")
            .values(status="extracting", updated_at=old)
        )
        await db.execute(
            update(Material).where(Material.title == "방금.pdf").values(status="extracting")
        )
        await db.commit()

    by_title = {m["title"]: m for m in await materials(client, project)}
    assert (by_title["도중.pdf"]["status"], by_title["도중.pdf"]["failure_code"]) == (
        "failed",
        "internal_error",
    )
    assert by_title["방금.pdf"]["status"] == "extracting"  # 데드라인 전이면 그대로
    assert by_title["완료.pdf"]["status"] == "failed"
    assert by_title["완료.pdf"]["failure_code"] == "ai_unavailable"
    retry = await client.post(
        f"{API_PREFIX}/materials/{by_title['도중.pdf']['id']}/retry", headers=auth(ALICE)
    )
    assert retry.status_code == 202
    statuses = {m["title"]: m["status"] for m in await materials(client, project)}
    assert statuses["도중.pdf"] == "failed"  # 재시도해도 AI 설정이 없으면 완료될 수 없다


# --- Cloud Tasks 모드 (architecture 7.1, 8.1 /internal) ---


def accept_token(token: str) -> None:
    if token != "task-token":
        raise AppError(403, "forbidden", "unexpected caller")


@pytest.fixture
def queue(app: FastAPI) -> FakeQueue:
    fake = FakeQueue()
    app.state.analysis_queue = fake
    app.state.task_token_verifier = accept_token
    return fake


async def run_task(
    client: httpx.AsyncClient, material_id: str, attempt: int, token: str = "task-token"
) -> httpx.Response:
    return await client.post(
        f"{API_PREFIX}/internal/tasks/analyze-material",
        json={"material_id": material_id, "attempt": attempt},
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )


async def test_cloud_tasks_mode_enqueues_and_worker_analyzes(
    queue: FakeQueue, client: httpx.AsyncClient, project: str
) -> None:
    res = await upload(client, project, "강의.pdf", make_pdf(["프로세스"]))
    assert res.json()["status"] == "queued"
    [(material_id, attempt)] = queue.tasks
    [item] = await materials(client, project)
    assert item["status"] == "queued"  # 큐가 부르기 전에는 분석하지 않는다

    assert (await run_task(client, str(material_id), attempt)).status_code == 200
    [item] = await materials(client, project)
    assert (item["status"], item["page_count"]) == ("failed", 1)
    assert item["failure_code"] == "ai_unavailable"

    # 같은 작업이 다시 와도(재전달) 이미 끝났으면 무시한다
    assert (await run_task(client, str(material_id), attempt)).status_code == 200
    assert (await materials(client, project))[0]["status"] == "failed"


async def test_worker_requires_the_task_token(
    queue: FakeQueue, client: httpx.AsyncClient, project: str
) -> None:
    await upload(client, project, "강의.pdf", make_pdf(["프로세스"]))
    [(material_id, attempt)] = queue.tasks
    assert (await run_task(client, str(material_id), attempt, token="")).status_code == 401
    assert (await run_task(client, str(material_id), attempt, token=ALICE)).status_code == 403
    assert (await materials(client, project))[0]["status"] == "queued"


async def test_worker_reruns_after_an_interrupted_delivery(
    queue: FakeQueue, client: httpx.AsyncClient, project: str, engine: AsyncEngine
) -> None:
    await upload(client, project, "강의.pdf", make_pdf(["프로세스"]))
    [(material_id, attempt)] = queue.tasks
    async with make_session_factory(engine)() as db:  # 분석 도중 인스턴스가 끊긴 상황
        await db.execute(update(Material).values(status="extracting"))
        await db.commit()
    await run_task(client, str(material_id), attempt)
    [item] = await materials(client, project)
    assert (item["status"], item["failure_code"]) == ("failed", "ai_unavailable")


async def test_old_attempt_is_ignored(
    queue: FakeQueue, client: httpx.AsyncClient, project: str
) -> None:
    await upload(client, project, "강의.pdf", make_pdf(["프로세스"]))
    [(material_id, attempt)] = queue.tasks
    await run_task(client, str(material_id), attempt + 5)
    assert (await materials(client, project))[0]["status"] == "queued"


async def test_enqueue_failure_marks_the_material_failed(
    queue: FakeQueue, client: httpx.AsyncClient, project: str
) -> None:
    queue.fail = True
    res = await upload(client, project, "강의.pdf", make_pdf(["프로세스"]))
    assert res.status_code == 202
    [item] = await materials(client, project)
    assert (item["status"], item["failure_code"]) == ("failed", "internal_error")


async def test_worker_path_is_closed_in_inline_mode(
    client: httpx.AsyncClient, project: str
) -> None:
    res = await run_task(client, str(uuid.uuid4()), 1)
    assert res.status_code == 404


def test_cloud_tasks_mode_needs_its_settings() -> None:
    assert make_queue(settings_for()) is None  # 기본은 inline
    with pytest.raises(ValueError, match="TASKS_QUEUE"):
        CloudTasksQueue(settings_for(queue_mode="cloud_tasks", tasks_project="p"))
