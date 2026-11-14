import json
import logging
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel, SecretStr, ValidationError

from backend.llm import (
    LLMError,
    LLMSettings,
    LLMTask,
    OpenAIProvider,
    openai_provider,
    validate_embedding,
)
from backend.llm.schemas import AssessmentOutput, ConceptExtractionOutput
from backend.llm.validators import validate_assessment, validate_concept_extraction


class Answer(BaseModel):
    value: int


def settings(**overrides: Any) -> LLMSettings:
    values: dict[str, Any] = {
        "openai_api_key": SecretStr("fake-test-key"),
        "llm_concept_extraction_model": "test-extraction",
        "llm_concept_extraction_effort": "medium",
        "llm_assessment_model": "test-assessment",
        "llm_assessment_effort": "medium",
        "llm_embedding_model": "test-embedding",
        # 개발 PC의 .env.llm(예: OpenRouter 주소)과 상관없이 기본 주소로 시험한다
        "llm_base_url": "https://api.openai.com/v1",
        "llm_image_text_model": None,
        "llm_image_text_effort": None,
    }
    return LLMSettings(_env_file=None, **(values | overrides))  # pyright: ignore[reportCallIssue]


def response(value: object) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json.dumps(value)},
                    ],
                }
            ],
        },
    )


async def generate(provider: OpenAIProvider, **kwargs: Any) -> Answer:
    return await provider.generate_structured(
        task=LLMTask.ASSESSMENT,
        system="system",
        input="input",
        schema=Answer,
        **kwargs,
    )


async def test_structured_request_and_semantic_retry() -> None:
    calls: list[dict[str, Any]] = []
    delays: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.openai.com/v1/responses"
        calls.append(json.loads(request.content))
        return response({"value": len(calls)})

    async def sleep(delay: float) -> None:
        delays.append(delay)

    def validate(answer: Answer) -> None:
        if answer.value != 3:
            raise ValueError("semantic mismatch")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        answer = await generate(OpenAIProvider(settings(), client, sleep=sleep), validate=validate)
    assert answer.value == 3
    assert delays == [1, 2]
    payload = calls[0]
    assert payload["model"] == "test-assessment"
    assert payload["reasoning"] == {"effort": "medium"}
    assert payload["store"] is False
    assert "temperature" not in payload
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["schema"]["additionalProperties"] is False
    assert payload["text"]["format"]["schema"]["required"] == ["value"]


@pytest.mark.parametrize(
    "failure", ["json", "schema", "shape", "incomplete", "refusal", "429", "503", "timeout"]
)
async def test_retriable_failures_are_bounded(failure: str) -> None:
    calls = 0
    delays: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if failure == "json":
            return httpx.Response(200, text="not json")
        if failure == "schema":
            return response({"value": "not an integer"})
        if failure == "shape":
            return httpx.Response(200, json=[])
        if failure == "incomplete":
            return httpx.Response(200, json={"status": "incomplete", "output": []})
        if failure == "refusal":
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [
                        {"type": "message", "content": [{"type": "refusal", "refusal": "no"}]},
                    ],
                },
            )
        if failure == "timeout":
            raise httpx.ReadTimeout("sensitive upstream error", request=request)
        return httpx.Response(int(failure))

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(LLMError) as caught:
            await generate(OpenAIProvider(settings(), client, sleep=sleep))
    assert calls == 3
    assert delays == [1, 2]
    assert "sensitive" not in str(caught.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_permanent_errors_are_not_retried(status: int) -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, text="sensitive upstream error")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(LLMError, match=f"HTTP {status}"):
            await generate(OpenAIProvider(settings(), client))
    assert calls == 1


async def test_embeddings_preserve_order_across_batches() -> None:
    batch_sizes: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.openai.com/v1/embeddings"
        payload = json.loads(request.content)
        assert payload["dimensions"] == 1536
        assert payload["encoding_format"] == "float"
        batch_sizes.append(len(payload["input"]))
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [float(text)] + [0.0] * 1535}
                    for i, text in reversed(list(enumerate(payload["input"])))
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = OpenAIProvider(settings(), client)
        result = await provider.embed([str(i) for i in range(1, 19)])
        assert await provider.embed([]) == []
        with pytest.raises(ValueError):
            await provider.embed([" "])
    assert batch_sizes == [16, 2]
    assert [v[0] for v in result] == list(range(1, 19))


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"index": 0, "embedding": [1.0]}],
        [{"index": 1, "embedding": [1.0] * 1536}],
        [{"index": 0, "embedding": [0.0] * 1536}],
    ],
)
async def test_invalid_embedding_output_fails(data: object) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": data}),
        )
    ) as client:
        with pytest.raises(LLMError):
            await OpenAIProvider(settings(llm_max_retries=0), client).embed(["text"])


@pytest.mark.parametrize("value", [[float("nan")] * 1536, [float("inf")] * 1536, [True] * 1536])
def test_vectors_reject_nonfinite_and_boolean(value: object) -> None:
    with pytest.raises(ValueError):
        validate_embedding(value)


def extraction() -> dict[str, Any]:
    return {
        "concepts": [
            {
                "title": "개념",
                "description": "기준 설명",
                "elements": [
                    {"text": "요소", "importance": "core", "evidence_chunks": ["C1"]}
                    for _ in range(3)
                ],
                "misconceptions": [],
            }
            for _ in range(5)
        ]
    }


def test_concept_schema_and_semantics() -> None:
    body = extraction()
    output = ConceptExtractionOutput.model_validate(body)
    validate_concept_extraction(output, chunk_labels={"C1"})
    with pytest.raises(ValueError, match="unknown"):
        validate_concept_extraction(output, chunk_labels={"C2"})
    for concept in body["concepts"]:
        for element in concept["elements"]:
            element["importance"] = "supporting"
    with pytest.raises(ValueError, match="core"):
        validate_concept_extraction(
            ConceptExtractionOutput.model_validate(body), chunk_labels={"C1"}
        )
    # 개념 수는 1~10개 (짧은 자료는 1개도 된다)
    concepts = extraction()["concepts"]
    assert len(ConceptExtractionOutput.model_validate({"concepts": concepts[:1]}).concepts) == 1
    for wrong in ([], concepts * 3):  # 0개, 15개
        with pytest.raises(ValidationError):
            ConceptExtractionOutput.model_validate({"concepts": wrong})


def test_assessment_requires_exact_elements_quotes_and_known_evidence() -> None:
    element_id = uuid4()
    body = {
        "elements": [
            {
                "element_id": str(element_id),
                "verdict": "met",
                "learner_quote": "내 말로 설명",
                "evidence_chunks": ["C1"],
                "note": "",
            }
        ],
        "unverified_statements": [],
        "feedback": {
            "correct": [],
            "missing_hint": [],
            "missing": [],
            "incorrect": [],
            "supplement": "",
        },
        "summary_points": [],
        "followup_question": None,
    }

    def check(output: AssessmentOutput, **kwargs: Any) -> None:
        validate_assessment(output, element_ids={element_id}, chunk_labels={"C1"}, **kwargs)

    output = AssessmentOutput.model_validate(body)
    check(output, learner_answers=["내 말로\n설명했어요"])
    with pytest.raises(ValueError, match="quote"):
        check(output, learner_answers=["다른 답변"])
    with pytest.raises(ValueError, match="exactly once"):
        validate_assessment(output, element_ids={uuid4()}, chunk_labels={"C1"}, learner_answers=[])
    body["elements"] *= 2
    with pytest.raises(ValueError, match="exactly once"):
        check(AssessmentOutput.model_validate(body), learner_answers=["내 말로 설명"])


def test_settings_require_explicit_models_and_hide_key() -> None:
    configured = settings()
    assert "fake-test-key" not in repr(configured)
    with pytest.raises(ValidationError):
        settings(llm_timeout_seconds=float("inf"))


async def test_embedding_limit_is_checked_before_request() -> None:
    def unexpected(request: httpx.Request) -> httpx.Response:
        raise AssertionError("oversized input must never be sent")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(ValueError, match="8191"):
            await OpenAIProvider(settings(), client).embed([" a" * 8192])


async def test_context_manager_closes_client_without_request() -> None:
    async with openai_provider(settings()) as provider:
        client = provider.client
        assert not client.is_closed
    assert client.is_closed


async def test_duplicate_embedding_indices_are_rejected() -> None:
    data = [{"index": 0, "embedding": [1.0] * 1536}] * 2
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": data}),
        )
    ) as client:
        with pytest.raises(LLMError):
            await OpenAIProvider(settings(llm_max_retries=0), client).embed(["a", "b"])


async def test_image_text_sends_png_and_returns_text() -> None:
    calls: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return response({"text": " 프로세스 상태도 \n"})

    configured = settings(llm_image_text_model="test-vision")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        text = await OpenAIProvider(configured, client).read_image_text(b"\x89PNG", "image/png")
    assert text == "프로세스 상태도"
    payload = calls[0]
    assert payload["model"] == "test-vision"
    assert "reasoning" not in payload  # effort를 비우면 보내지 않는다
    assert payload["store"] is False
    # OpenAI 이미지 입력 형식 (공식 문서: input_text + input_image, data URL, detail)
    [prompt, image] = payload["input"][0]["content"]
    assert prompt["type"] == "input_text" and prompt["text"]
    assert image == {
        "type": "input_image",
        "image_url": "data:image/png;base64,iVBORw==",
        "detail": "high",  # 작은 글자를 읽으려면 고해상도
    }
    assert "추측" in payload["instructions"]


async def test_image_text_requires_configured_model_and_known_type() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: response({}))) as client:
        with pytest.raises(LLMError, match="not configured"):
            await OpenAIProvider(settings(), client).read_image_text(b"x", "image/png")
        provider = OpenAIProvider(settings(llm_image_text_model="m"), client)
        with pytest.raises(ValueError):
            await provider.read_image_text(b"x", "image/gif")


async def test_base_url_points_to_openai_compatible_service() -> None:
    """OpenRouter처럼 OpenAI 호환 주소로 보낼 수 있다. 끝의 / 는 지운다."""
    urls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1] * 1536}]})

    configured = settings(llm_base_url="https://openrouter.ai/api/v1/")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        await OpenAIProvider(configured, client).embed(["text"])
    assert urls == ["https://openrouter.ai/api/v1/embeddings"]
    assert settings(llm_base_url="").llm_base_url == "https://api.openai.com/v1"
    with pytest.raises(ValidationError):
        settings(llm_base_url="http://openrouter.ai/api/v1")


async def test_retry_reasons_are_logged_without_content() -> None:
    """모든 시도가 실패해도 이유는 남고, 응답 속 글자(학습자 답 등)는 남기지 않는다."""
    replies = iter([{"value": "비밀 답변 문장"}, {"value": 1}])

    def handle(_: httpx.Request) -> httpx.Response:
        return response(next(replies))

    async def sleep(_: float) -> None:
        return None

    def validate(_: Answer) -> None:
        raise ValueError("learner quote is not present in session answers")

    # 다른 시험의 로깅 설정과 상관없이 이 로거의 기록을 직접 받는다
    records: list[logging.LogRecord] = []
    handler = logging.Handler(logging.WARNING)
    handler.emit = records.append  # type: ignore[method-assign]
    target = logging.getLogger("backend.llm.provider")
    target.addHandler(handler)
    old_level, old_disabled = target.level, target.disabled
    target.setLevel(logging.WARNING)
    target.disabled = False
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            provider = OpenAIProvider(settings(llm_max_retries=1), client, sleep=sleep)
            with pytest.raises(LLMError):
                await generate(provider, validate=validate)
    finally:
        target.removeHandler(handler)
        target.setLevel(old_level)
        target.disabled = old_disabled
    messages = [r.getMessage() for r in records]
    assert len(messages) == 2
    assert "attempt 1/2" in messages[0] and "schema ['value:" in messages[0]
    assert "attempt 2/2" in messages[1] and "learner quote is not present" in messages[1]
    assert all("비밀" not in m for m in messages)
