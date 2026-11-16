from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.llm import LLMSettings
from backend.rag.config import RAGSettings


def test_dedicated_env_file_overrides_root_and_process_env_overrides_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root_env, ai_env = tmp_path / ".env", tmp_path / ".env.llm"
    root_env.write_text(
        "OPENAI_API_KEY=fake-root-key\n"
        "LLM_CONCEPT_EXTRACTION_MODEL=test-model\n"
        "LLM_CONCEPT_EXTRACTION_EFFORT=medium\n"
        "LLM_ASSESSMENT_MODEL=test-model\n"
        "LLM_ASSESSMENT_EFFORT=medium\n"
        "LLM_EMBEDDING_MODEL=test-embedding\n",
        encoding="utf-8",
    )
    ai_env.write_text("OPENAI_API_KEY=fake-dedicated-key\n", encoding="utf-8")
    for key in LLMSettings.model_fields:
        monkeypatch.delenv(key.upper(), raising=False)
    settings = LLMSettings(_env_file=(root_env, ai_env))  # pyright: ignore[reportCallIssue]
    assert settings.openai_api_key.get_secret_value() == "fake-dedicated-key"
    assert settings.llm_embedding_model == "test-embedding"
    monkeypatch.setenv("OPENAI_API_KEY", "fake-process-key")
    settings = LLMSettings(_env_file=(root_env, ai_env))  # pyright: ignore[reportCallIssue]
    assert settings.openai_api_key.get_secret_value() == "fake-process-key"
    assert "fake-process-key" not in repr(settings)


def test_missing_model_configuration_fails_without_api_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in LLMSettings.model_fields:
        monkeypatch.delenv(key.upper(), raising=False)
    env_file = tmp_path / ".env.llm"
    env_file.write_text("OPENAI_API_KEY=fake-key\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        LLMSettings(_env_file=env_file)  # pyright: ignore[reportCallIssue]


def test_rag_environment_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_CHUNK_TOKENS", "400")
    monkeypatch.setenv("RAG_CHUNK_OVERLAP_TOKENS", "50")
    monkeypatch.setenv("RAG_TOP_K", "2")
    settings = RAGSettings()
    assert (settings.rag_chunk_tokens, settings.rag_chunk_overlap_tokens, settings.rag_top_k) == (
        400,
        50,
        2,
    )
