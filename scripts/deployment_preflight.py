"""Check exported production configuration without printing values or contacting services."""

import os
from collections.abc import Mapping
from urllib.parse import urlsplit

REQUIRED = (
    "DATABASE_URL",
    "FIREBASE_PROJECT_ID",
    "GCS_BUCKET",
    "GCS_SIGNER_SERVICE_ACCOUNT",
    "TASKS_PROJECT",
    "TASKS_LOCATION",
    "TASKS_QUEUE",
    "TASKS_INVOKER_SA",
    "PUBLIC_BASE_URL",
    "OPENAI_API_KEY",
    "LLM_CONCEPT_EXTRACTION_MODEL",
    "LLM_CONCEPT_EXTRACTION_EFFORT",
    "LLM_ASSESSMENT_MODEL",
    "LLM_ASSESSMENT_EFFORT",
    "LLM_EMBEDDING_MODEL",
    "CORS_ORIGINS",
)


def https_origin(value: str) -> bool:
    try:
        url = urlsplit(value)
        return bool(
            url.scheme == "https"
            and url.hostname
            and url.hostname not in {"localhost", "127.0.0.1", "::1"}
            and not url.username
            and not url.password
            and url.path in {"", "/"}
            and not url.query
            and not url.fragment
            and "*" not in value
            and url.port != 0
        )
    except ValueError:
        return False


def check(env: Mapping[str, str]) -> list[str]:
    errors = [f"{name}: required" for name in REQUIRED if not env.get(name, "").strip()]
    if env.get("QUEUE_MODE") != "cloud_tasks":
        errors.append("QUEUE_MODE: must be cloud_tasks")
    for name in ("GCS_EMULATOR_URL", "GCS_EMULATOR_PUBLIC_URL"):
        if env.get(name, "").strip():
            errors.append(f"{name}: must be empty")
    if not env.get("DATABASE_URL", "").startswith("postgresql+asyncpg://"):
        errors.append("DATABASE_URL: must use postgresql+asyncpg")
    if not https_origin(env.get("PUBLIC_BASE_URL", "")):
        errors.append("PUBLIC_BASE_URL: must be an HTTPS origin")
    origins = env.get("CORS_ORIGINS", "").split(",")
    if not origins or not all(https_origin(origin.strip()) for origin in origins):
        errors.append("CORS_ORIGINS: must contain exact HTTPS origins")
    try:
        deadline = int(env.get("ANALYSIS_DEADLINE_MINUTES", "30"))
        if not 1 <= deadline <= 30:
            errors.append("ANALYSIS_DEADLINE_MINUTES: must be between 1 and 30")
    except ValueError:
        errors.append("ANALYSIS_DEADLINE_MINUTES: must be an integer")
    return errors


def main() -> int:
    errors = check(os.environ)
    if errors:
        print("Production configuration check failed (values are hidden):")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(
        "Configuration shape passed. Cloud permissions, database and live flows remain unverified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
