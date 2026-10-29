# Feynmi
팀플 github

## IntelliJ 프론트엔드 실행 (Windows)

`mise.toml` 기준의 Node.js와 pnpm을 설치하고, `apps/frontend`에서
`pnpm install --frozen-lockfile`로 의존성을 설치합니다.

- 시작: IntelliJ 실행 설정 `Frontend dev` 또는 `pnpm dev`
- 종료: IntelliJ 실행 설정 `Frontend stop` 또는 `pnpm dev:stop`

명령은 `apps/frontend` 폴더에서 실행합니다. 종료 설정은 이 프로젝트 경로의
Next.js 개발 서버와 자식 프로세스만 종료하며, 서버가 이미 꺼져 있으면 그대로 끝납니다.
IntelliJ에서 시작한 서버는 실행 창의 정지(■) 버튼으로도 종료할 수 있습니다.

## IntelliJ 백엔드와 DB 실행 (Windows)

Docker Desktop을 먼저 실행하고, 저장소 루트의 `.env`에 Firebase 설정을 넣습니다.
IntelliJ 상단 실행 설정에서 다음 항목을 선택한 뒤 Run(▶)을 누릅니다.

| 실행 설정 | 동작 |
|---|---|
| `Backend start` | PostgreSQL과 FastAPI 컨테이너 시작, DB 마이그레이션 적용 |
| `Backend stop` | 백엔드와 DB 컨테이너 정지, 저장된 데이터 유지 |

앱을 사용하려면 `Backend start` 실행 후 `Frontend dev`를 실행합니다.
종료할 때는 `Frontend stop`과 `Backend stop`을 각각 실행합니다.
백엔드는 백그라운드 컨테이너로 실행되므로 시작 명령이 완료되어도 계속 켜져 있습니다.
백엔드를 끌 때는 IntelliJ의 ■ 버튼 대신 `Backend stop`을 실행합니다.

API 문서는 http://localhost:8000/docs 에서 확인할 수 있습니다.
터미널에서는 `apps/frontend`에서 `pnpm backend:start`, `pnpm backend:stop`으로도 실행할 수 있습니다.
