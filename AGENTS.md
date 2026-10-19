# AGENTS.md

FeynMi(파인마이): 학습자가 자료(PDF/PPTX)를 올리고 개념을 자기 말로 설명하면, LLM이 이해도를 판정하고 피드백하는 한국어 전용 반응형 웹 학습 서비스. 1개월 MVP(공모전/졸업작품).

## 문서
- 제품 요구사항: [docs/prd.md](docs/prd.md) — 기능/비기능 요구사항, 판정 로직(6.1), 기술 스택(9장)
- 백로그/스프린트: [docs/backlog.md](docs/backlog.md) — `FM-xxx` 스토리, 인수 조건, 완료 정의
- 하위 지침: [apps/backend/AGENTS.md](apps/backend/AGENTS.md), [apps/frontend/AGENTS.md](apps/frontend/AGENTS.md)

작업 전 관련 FM 스토리의 인수 조건을 확인하고, MVP 제외 항목(prd.md 5.2)은 구현하지 않는다.

## 구조
- `apps/frontend`: Next.js (pnpm)
- `apps/backend`: Python, FastAPI (uv)
- `packages/`: 공용 코드
- 도구 버전은 `mise.toml` 기준 (node 24, pnpm, uv). CI는 `.github/workflows/ci.yml`.

## 스택
Firebase Auth(백엔드에서 ID 토큰 검증) · PostgreSQL + pgvector(RAG) · OpenAI API 단일 공급자.

## 핵심 규칙
- **상태 판정**: LLM은 요소별 판정(충족/부분/누락/모순)만 하고, 개념 상태(미학습/오개념/이해/부분 이해)는 코드 규칙으로 산출한다. 규칙 상세는 prd.md 6.1.
- LLM 출력은 JSON 스키마로 검증하고 실패 시 재시도한다.
- LLM 호출은 별도 모듈로 분리한다. 모델 ID와 API 키는 환경변수로 관리하며 코드/저장소에 하드코딩·커밋하지 않는다.
- 자료에 없는 내용은 단정하지 않고 "자료에서 확인되지 않음"으로 표시한다. AI는 정답을 바로 알려주지 않고 질문으로 유도한다.
- 사용자는 본인 자료만 접근할 수 있어야 한다.

## 미확정
임베딩 모델, OpenAI 모델 ID/파라미터는 미정(prd.md 12장). 임의로 가정하지 말고 확인한다.
