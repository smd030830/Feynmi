# syntax=docker/dockerfile:1
# 빌드 컨텍스트는 apps/backend다. 기본 타깃(prod)은 Cloud Run용, dev는 compose용이다.

FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS base
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# 로컬 개발: 소스는 compose가 /app에 마운트하고, 가상환경은 마운트에 가려지지 않게 밖에 둔다.
FROM base AS dev
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked
CMD ["uvicorn", "backend.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]

# 운영 가상환경: 개발 도구 없이, 소스를 복사해 넣는 비편집 설치
FROM base AS build
ENV UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# Cloud Run 이미지. 마이그레이션(alembic upgrade head)도 이 이미지로 실행한다.
FROM python:3.14-slim-trixie AS prod
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
RUN useradd --system --uid 1000 --no-create-home app
WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY alembic.ini ./
COPY migrations ./migrations
USER app
# Cloud Run은 PORT 환경변수로 포트를 알려 준다.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
