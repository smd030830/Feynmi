# AGENTS.md

Feynmi(파인마이): 학습자가 프로젝트에 자료(PDF/PPTX)를 올리고 개념을 자기 말로 설명하면, LLM이 이해도를 판정하고 피드백하는 한국어 전용 PC 웹 학습 서비스. 1개월 MVP(공모전/졸업작품).

## 문서
- **단일 진실 공급원: [docs/prd.md](docs/prd.md)**. 요구사항, 판정/세션 규칙, 수치 기준, 스택, 모델은 PRD에만 정의한다. 이 파일과 backlog는 PRD를 요약하거나 참조만 하며, 충돌하면 PRD를 따른다.
- 아키텍처: [docs/architecture.md](docs/architecture.md) — 구성 요소, 흐름, 모듈 경계, API, 데이터 모델, 배포. PRD 절을 참조하며 구현 방식만 정의
- 디자인 시스템: [docs/design-system.md](docs/design-system.md) — Figma Make 시안 기반의 디자인 토큰, 컴포넌트, 화면 구성. 기능과 규칙은 PRD를 따름
- 백로그/스프린트: [docs/backlog.md](docs/backlog.md) — `FM-xxx` 스토리, SP, 스프린트, 완료 정의. AC는 PRD 절을 참조
- 하위 지침: [apps/backend/AGENTS.md](apps/backend/AGENTS.md), [apps/frontend/AGENTS.md](apps/frontend/AGENTS.md)

작업 전 관련 FM 스토리와 그 AC가 가리키는 PRD 절을 확인하고, MVP 제외 항목(prd.md 5.2)은 구현하지 않는다. PRD에 없는 결정이 필요하면 임의로 가정하지 말고 확인한 뒤 PRD에 반영한다(결정 이력은 prd.md 12장).

## 구조
- `apps/frontend`: Next.js (pnpm)
- `apps/backend`: Python, FastAPI (uv)
- `packages/`: 공용 코드
- 도구 버전은 `mise.toml` 기준 (node 24, pnpm, uv). CI는 `.github/workflows/ci.yml`.

## 핵심 규칙 (상세는 PRD)
- **상태 판정**: LLM은 요소별 판정만 하고, 개념 상태는 코드 규칙으로 산출한다 (prd.md 6.1).
- LLM 출력은 JSON 스키마로 검증하고 실패 시 재시도한다 (FR-5.4).
- LLM 호출은 별도 모듈로 분리한다. 모델 ID, effort, API 키는 환경변수로 관리하며 코드/저장소에 하드코딩·커밋하지 않는다 (prd.md 9.2).
- 자료에 없는 내용은 단정하지 않고 "자료에서 확인되지 않음"으로 표시한다. AI는 정답을 바로 알려주지 않고 질문으로 유도한다 (FR-3.3, FR-5.5).
- 사용자는 본인 자료만 접근할 수 있어야 한다 (FR-4.2).
