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
