"""OpenAI REST 경계: Structured Outputs, 검증, 유한 재시도 (PRD FR-5.4).

호출자는 클라이언트 수명을 관리한다. SDK 내부 재시도가 없어 설정한 시도 횟수가 그대로 적용된다.
"""

import asyncio
import base64
import math
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Any, Protocol

import httpx
import tiktoken
from pydantic import BaseModel, ConfigDict

from backend.db.models import EMBEDDING_DIMENSIONS
from backend.llm.config import LLMSettings


class LLMTask(StrEnum):
    CONCEPT_EXTRACTION = "concept_extraction"
    ASSESSMENT = "assessment"


class LLMError(Exception):
    """외부 응답·키·학습자료를 오류 메시지에 포함하지 않는다."""


class _InvalidOutput(ValueError):
    pass


class ImageText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


IMAGE_TEXT_INSTRUCTIONS = (
    "학습자료 속 이미지에 보이는 글자를 그대로 옮겨 적는다. "
    "해석, 요약, 번역, 보충 설명을 하지 않고 이미지에 없는 내용을 추측해 넣지 않는다. "
    "읽는 순서대로 줄바꿈을 유지하고, 표는 한 행을 한 줄로 하여 칸을 ' | '로 구분한다. "
    "글자가 없거나 읽을 수 없으면 text를 빈 문자열로 둔다."
)


class LLMProvider(Protocol):
    async def generate_structured[T: BaseModel](
        self,
        *,
        task: LLMTask,
        system: str,
        input: str,
        schema: type[T],
        validate: Callable[[T], None] | None = None,
    ) -> T: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def read_image_text(self, image: bytes, mime_type: str) -> str: ...


def validate_embedding(value: object) -> list[float]:
    if not isinstance(value, list) or len(value) != EMBEDDING_DIMENSIONS:
        raise ValueError("embedding dimension mismatch")
    if any(
        isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n)
        for n in value
    ):
        raise ValueError("embedding must contain finite numbers")
    if not any(n != 0 for n in value):
        raise ValueError("embedding must not be zero")
    return [float(n) for n in value]


def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic 모델의 모든 객체를 strict JSON Schema로 만든다."""

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(schema)
    return schema


class OpenAIProvider:
    def __init__(
        self,
        settings: LLMSettings,
        client: httpx.AsyncClient,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.settings = settings
        self.client = client
        self.sleep = sleep

    async def _request[T](
        self,
        path: str,
        payload: dict[str, Any],
        parse: Callable[[Any], T],
    ) -> T:
        for attempt in range(self.settings.llm_max_retries + 1):
            try:
                response = await self.client.post(
                    f"https://api.openai.com/v1/{path}",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.settings.openai_api_key.get_secret_value()}"
                    },
                    timeout=self.settings.llm_timeout_seconds,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise _InvalidOutput("transient upstream failure")
                if response.is_error:
                    raise LLMError(f"OpenAI request rejected (HTTP {response.status_code})")
                return parse(response.json())
            except httpx.TransportError, ValueError, KeyError, TypeError, AttributeError:
                if attempt == self.settings.llm_max_retries:
                    raise LLMError("OpenAI request or output validation failed") from None
                # ValueError includes Pydantic and caller-provided semantic validation failures.
                await self.sleep(float(2**attempt))
        raise AssertionError("unreachable")

    async def generate_structured[T: BaseModel](
        self,
        *,
        task: LLMTask,
        system: str,
        input: str,
        schema: type[T],
        validate: Callable[[T], None] | None = None,
    ) -> T:
        return await self._structured(
            model=getattr(self.settings, f"llm_{task.value}_model"),
            effort=getattr(self.settings, f"llm_{task.value}_effort"),
            system=system,
            input=input,
            schema=schema,
            validate=validate,
        )

    async def read_image_text(self, image: bytes, mime_type: str) -> str:
        """이미지 속 글자를 옮겨 적는다 (AI 보조 OCR). 모델이 설정되지 않았으면 LLMError."""
        model = self.settings.llm_image_text_model
        if not model or not model.strip():
            raise LLMError("image text model is not configured")
        if mime_type not in ("image/png", "image/jpeg"):
            raise ValueError("image must be png or jpeg")
        encoded = base64.b64encode(image).decode("ascii")
        result = await self._structured(
            model=model,
            effort=self.settings.llm_image_text_effort,
            system=IMAGE_TEXT_INSTRUCTIONS,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": f"data:{mime_type};base64,{encoded}"}
                    ],
                }
            ],
            schema=ImageText,
        )
        return result.text.strip()

    async def _structured[T: BaseModel](
        self,
        *,
        model: str,
        effort: str | None,
        system: str,
        input: str | list[dict[str, Any]],
        schema: type[T],
        validate: Callable[[T], None] | None = None,
    ) -> T:
        def parse(body: Any) -> T:
            if body.get("status") != "completed" or body.get("error"):
                raise _InvalidOutput("response did not complete")
            texts: list[str] = []
            for item in body["output"]:
                if item.get("type") != "message":
                    continue
                for content in item["content"]:
                    if content.get("type") == "refusal":
                        raise _InvalidOutput("response refused")
                    if content.get("type") == "output_text":
                        texts.append(content["text"])
            if len(texts) != 1:
                raise _InvalidOutput("expected one structured output")
            result = schema.model_validate_json(texts[0], strict=True)
            if validate:
                validate(result)
            return result

        payload: dict[str, Any] = {
            "model": model,
            "instructions": system,
            "input": input,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema.__name__,
                    "strict": True,
                    "schema": _strict_schema(schema.model_json_schema()),
                }
            },
        }
        if effort:
            payload["reasoning"] = {"effort": effort}
        return await self._request("responses", payload, parse)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not text.strip() for text in texts):
            raise ValueError("embedding input must not be empty")
        encoding = tiktoken.get_encoding("cl100k_base")
        if any(len(encoding.encode(text, disallowed_special=())) > 8191 for text in texts):
            raise ValueError("embedding input exceeds 8191 tokens")
        vectors: list[list[float]] = []
        # 16 × 8192 tokens remains below the 300k request token limit.
        for start in range(0, len(texts), 16):
            batch = texts[start : start + 16]

            def parse(body: Any, count: int = len(batch)) -> list[list[float]]:
                data = body["data"]
                if len(data) != count:
                    raise _InvalidOutput("embedding count mismatch")
                ordered: dict[int, list[float]] = {}
                for item in data:
                    index = item["index"]
                    if type(index) is not int or index not in range(count) or index in ordered:
                        raise _InvalidOutput("invalid embedding index")
                    ordered[index] = validate_embedding(item["embedding"])
                return [ordered[i] for i in range(count)]

            vectors.extend(
                await self._request(
                    "embeddings",
                    {
                        "model": self.settings.llm_embedding_model,
                        "input": batch,
                        "dimensions": EMBEDDING_DIMENSIONS,
                        "encoding_format": "float",
                    },
                    parse,
                )
            )
        return vectors


@asynccontextmanager
async def openai_provider(settings: LLMSettings | None = None) -> AsyncIterator[OpenAIProvider]:
    """환경설정 검증과 클라이언트 해제를 담당하며, 여기서는 API를 호출하지 않는다."""
    configured = settings if settings is not None else LLMSettings()  # pyright: ignore[reportCallIssue]
    async with httpx.AsyncClient() as client:
        yield OpenAIProvider(configured, client)
