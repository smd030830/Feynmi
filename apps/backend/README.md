# Feynmi backend

FastAPI + SQLAlchemy 2 (async) + Alembic. 구조와 규칙은 [architecture.md](../../docs/architecture.md)를 따른다.

## 로컬 실행

전체(프론트, 백엔드, DB)는 저장소 루트에서 `docker compose up`으로 띄운다. 백엔드는 기동할 때 마이그레이션을 적용한다.

백엔드만 직접 실행하려면 DB를 먼저 띄운다.

```bash
docker compose up -d db
cd apps/backend
uv sync
cp ../../.env.example ../../.env   # 저장소 루트의 .env를 쓴다
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload   # http://localhost:8000/docs
```

`.env`의 `FIREBASE_PROJECT_ID`(프론트엔드의 `NEXT_PUBLIC_FIREBASE_PROJECT_ID`와 같은 값)가 필요하다. 기존 사용자의 ID 토큰 서명 검증은 Firebase 공개 인증서를 쓴다(인터넷 연결 필요). 최초 DB 사용자 생성 전 Firebase 계정 존재 확인, 모든 기기 로그아웃, 회원 탈퇴에는 Firebase Admin SDK 권한을 가진 ADC 또는 개발용 서비스 계정 자격 증명이 필요하다.
compose로 띄울 때는 저장소 루트의 `.env`에 `FIREBASE_PROJECT_ID`를 둔다.

프로필 이미지는 `POST /api/v1/me/avatar`에 JPG/PNG 원본 바이트를 보내며 최대 2MB다. `GCS_BUCKET`은 비공개 버킷으로 설정한다. 서버 자격 증명에 객체 읽기·쓰기·삭제 권한을 부여하고, 읽기 Signed URL 발급을 위해 서명 가능한 서비스 계정 또는 `GCS_SIGNER_SERVICE_ACCOUNT`와 IAM `signBlob` 권한을 준비한다. 쓰기 Signed URL은 발급하지 않는다. 자격 증명 파일과 키는 커밋하지 않는다.

Docker에서는 호스트 ADC가 자동으로 전달되지 않는다. 개인용 Compose override에서 자격 증명 파일을 읽기 전용으로 마운트하고, `GOOGLE_APPLICATION_CREDENTIALS`를 컨테이너 안의 해당 경로로 지정한다. 개인 경로·자격 증명을 공유 Compose 파일에 넣지 않는다.

탈퇴 실패 시 `deleting` 행을 유지하고 일반 요청을 차단한다. 서버가 시작 시와 실행 중 30초마다 삭제를 재시도하며 Firebase·파일 삭제가 완료된 뒤 DB를 마지막으로 삭제한다. Cloud Run에서 요청이 없을 때도 재시도하려면 상시 CPU와 최소 인스턴스를 설정한다. 개발 환경에서는 서버를 실행한 동안 재시도한다.

설명 학습은 기존 `ready` 자료의 개념·체크리스트·근거 청크를 사용한다. 이번 구현에는 자료 업로드와 개념 추출이 포함되지 않으며, `tests/test_sessions.py`가 실제 API와 테스트용 자료·가짜 AI 응답으로 흐름을 검증한다. 실제 학습 판정에는 `.env.llm` 설정이 필요하다.

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

## 독립 AI·RAG 모듈 (FM-050~053)

현재 구현 범위는 OpenAI 호출, 청크 분할·임베딩 준비·저장·검색, 출력 검증과 재시도다.
업로드/파서/분석 워커, 개념 추출·평가 프롬프트, 학습 API는 연결하지 않았다.
출력 스키마가 있다는 것이 개념 추출이나 학습 기능의 완료를 뜻하지 않는다.

### 키와 모델 설정

- 저장소 루트의 `.env.llm`이 AI 전용 로컬 설정 파일이다. `OPENAI_API_KEY`에 키를 입력한다.
- 이번 작업 PC의 `.env.llm`에는 PRD 9.2의 모델/effort가 미리 설정되어 있으며 키는 비어 있다.
- 다른 PC에서는 `.env.llm.example`을 `.env.llm`으로 복사하고 PRD 9.2의 모델/effort와 키를 채운다.
  모델 ID/effort는 코드에 기본값을 두지 않는다.
- 설정 우선순위는 생성자 인자 → 프로세스 환경변수 → `.env.llm` → `.env`다.
  키는 `SecretStr`로 다루고 `.env.llm`은 Git에서 제외한다.
- `openai_provider()` 진입 시 필요한 설정을 검증한다. 키 없이도 기존 앱과 가짜 응답 테스트는 실행할 수 있다.
- Docker Compose도 선택적 `.env.llm`을 백엔드 환경변수로 전달한다. 설정을 바꾸면 컨테이너를 재생성한다.
  운영에서는 동일한 변수들을 실행 환경에 주입한다.

### 사용 경계

```python
from backend.llm import openai_provider
from backend.rag.chunking import PageText, split_pages
from backend.rag.store import embed_chunks, save_chunks, search_chunks

# pages는 별도 파서가 준비한 쪽/슬라이드 텍스트다.
chunks = split_pages([PageText(number=1, text="자료에서 추출된 텍스트")])
async with openai_provider() as provider:
    prepared = await embed_chunks(chunks, provider)
    query_vector = (await provider.embed([query_text]))[0]

# 외부 API 호출이 끝난 뒤 DB 트랜잭션을 연다. session_factory는 기존 DB 구성이다.
async with session_factory.begin() as db:
    await save_chunks(db, user_id=user_id, material_id=material_id, chunks=prepared)
async with session_factory.begin() as db:
    evidence = await search_chunks(
        db,
        user_id=user_id,
        project_id=project_id,
        query_embedding=query_vector,
        evidence_chunk_ids=required_chunk_ids,
    )
```

- `split_pages`: 쪽 경계를 유지하고 긴 쪽만 분할한다. 0부터 시작하는 청크 순번, 쪽 범위, 토큰 수를 보존한다.
  한글·이모지의 UTF-8 문자 경계에서 분할한다. 빈 쪽은 건너뛰며, 쪽 번호는 양수·오름차순이다.
- `RAG_CHUNK_TOKENS`/`RAG_CHUNK_OVERLAP_TOKENS`/`RAG_TOP_K`는 루트 `.env` 또는 환경변수에서 읽는다.
  초기값은 PRD 9.4를 따른다. 토큰 계산은 임베딩 입력 기준 `cl100k_base`다.
  tiktoken 최초 사용 시 공개 토큰 사전을 다운로드·캐시하므로 최초 실행에는 네트워크가 필요하다.
- `embed_chunks`: DB 접근 없이 임베딩을 준비한다. 1536차원·유한값·영벡터 여부와 응답 개수·순서를 검증한다.
  임베딩은 최대 16개씩 전송하고 입력당 8191토큰을 넘으면 요청 전에 거절한다.
- `save_chunks`: 소유권을 확인한 뒤 기존 `chunks` 테이블에 저장한다. 자체 커밋하지 않는다.
  이미 청크가 있는 자료는 거절한다. 재분석·교체·자료 상태 변경은 향후 워커 책임이다.
- `search_chunks`: 본인 프로젝트의 `ready` 자료 전체를 코사인 거리로 정확 검색한다.
  Top-k에 필수 근거를 합쳐 중복을 제거하므로 결과 수는 k보다 클 수 있다.
  필수 근거가 다른 프로젝트/사용자/미완료 자료에 속하거나 없으면 거절한다.
- `generate_structured(task=..., system=..., input=..., schema=..., validate=...)`:
  Responses API의 strict JSON Schema와 Pydantic으로 출력 형식을 검증한다.
  `schemas.py`의 개념 추출·판정 계약과 `validators.py`의 의미 검증기를 제공한다.
  호출자는 `validate` 콜백에 입력 청크 라벨·체크리스트 요소·현재 세션 답변을 바인딩한다.
  이를 통해 없는 근거 참조, 빠지거나 중복된 판정, 실제 답변에 없는 인용도 재시도 대상이 된다.
- 네트워크/타임아웃/429/5xx 및 출력 검증 실패는 `LLM_MAX_RETRIES`만큼 지수 백오프로 재시도한다.
  초기값 2는 최초 포함 총 3회다. 400/401/403 등 영구 오류는 재시도하지 않는다.
  최종 오류는 원문 응답·자료·키를 담지 않는 `LLMError`다.

가짜 응답과 로컬 DB만 사용하는 검사:

```bash
uv run pytest tests/test_llm.py tests/test_chunking.py tests/test_rag_embeddings.py tests/test_rag_store.py
```

실제 OpenAI 요청은 위 테스트에서 전송하지 않는다. API 계약은
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)와
[Embeddings API](https://developers.openai.com/api/reference/resources/embeddings/methods/create)를 따른다.

## 마이그레이션

```bash
uv run alembic revision --autogenerate -m "설명"   # 모델을 고친 뒤. 생성된 파일을 반드시 검토한다
uv run alembic upgrade head
uv run alembic downgrade -1
```

`tests/test_migrations.py`가 모델과 마이그레이션이 어긋나면 실패한다.
