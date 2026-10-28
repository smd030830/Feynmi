# Feynmi backend

FastAPI + SQLAlchemy 2 (async) + Alembic. 구조와 규칙은 [architecture.md](../../docs/architecture.md)를 따른다.

## 로컬 실행

전체(프론트, 백엔드, DB)는 저장소 루트에서 `docker compose up`으로 띄운다. 백엔드는 기동할 때 마이그레이션을 적용한다.

백엔드만 직접 실행하려면 DB를 먼저 띄운다.

```bash
docker compose up -d db
cd apps/backend
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload   # http://localhost:8000/docs
```

`.env`의 `FIREBASE_PROJECT_ID`(프론트엔드의 `NEXT_PUBLIC_FIREBASE_PROJECT_ID`와 같은 값)가 필요하다. 토큰을 검증하려면 개발용 Firebase 프로젝트의 자격 증명도 필요하다.
`gcloud auth application-default login`을 하거나 개발용 서비스 계정 키 경로를 `GOOGLE_APPLICATION_CREDENTIALS`로 지정한다(키는 커밋하지 않는다).
compose로 띄울 때는 저장소 루트의 `.env`에 `FIREBASE_PROJECT_ID`를 둔다.

## 검사와 테스트

```bash
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest
```

테스트는 PostgreSQL(pgvector)이 필요하다. 기본 접속은 `postgresql+asyncpg://feynmi:feynmi@localhost:5432/feynmi_test`이고 `TEST_DATABASE_URL`로 바꾼다.
테스트가 스키마를 통째로 지우므로 DB 이름은 `_test`로 끝나야 한다. 개발 DB(`feynmi`)에는 쓰지 않는다.

```bash
docker compose exec db createdb -U feynmi feynmi_test
```

## 마이그레이션

```bash
uv run alembic revision --autogenerate -m "설명"   # 모델을 고친 뒤. 생성된 파일을 반드시 검토한다
uv run alembic upgrade head
uv run alembic downgrade -1
```

`tests/test_migrations.py`가 모델과 마이그레이션이 어긋나면 실패한다.
