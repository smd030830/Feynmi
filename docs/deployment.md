# 운영 배포와 검증

PRD 9.1과 architecture 11장의 Vercel·Cloud Run·Cloud SQL·Cloud Storage·Cloud Tasks 구성을 따른다. 이 문서는 배포 실행 또는 공개 환경 검증 완료를 뜻하지 않는다.

## 이번 배포의 비용 조건

- 프론트엔드는 Vercel Hobby 플랜만 사용하며 유료 플랜으로 전환하지 않는다.
- 사용자가 2026-11-15에 일주일 시연을 위한 Google Cloud 유료 배포를 승인했다. Cloud Run은 요청 기반 CPU, 최소 0개·최대 1개 인스턴스를 사용한다. PDF 분석 중 조회 요청의 플랫폼 429가 확인돼 2 vCPU·2 GiB·동시 요청 16개로 조정했다. 요청 처리 중 자원 단가는 증가하며 Cloud SQL과 저장소 등은 별도 비용이 발생한다.
- 프로젝트별 예산 알림은 20,000원이며 50%·90%·100%에서 알린다. 예산 알림은 사용량이나 결제를 자동으로 차단하지 않는다. 일주일 뒤 자원을 자동 종료하는 설정은 없으므로 시연 종료 후 별도로 중지·정리해야 한다. 데이터 삭제 전에는 백업과 사용자 확인이 필요하다.
- 기존 프로젝트를 변경하지 않고 Feynmi 전용 프로젝트를 사용한다. 생성된 프로젝트·연결 상태는 Git 제외 로컬 기록으로 관리한다.
- Vercel 업로드는 `.vercelignore`로 개인 환경변수·인증·로컬 테스트·자료를 제외한다. 프로젝트 Root Directory는 `apps/frontend`, 공유 타입을 위해 루트 외 소스 포함을 켠다.
- 배포 검증 중 OpenRouter 유료 AI 호출은 수행하지 않는다. 사용자가 배포 후 직접 실행하는 AI 분석·평가는 별도의 API 비용이 발생할 수 있다.

## 현재 시연 배포

- 프론트엔드: https://feynmi.vercel.app
- 백엔드: https://feynmi-api-7orgcgb3ra-du.a.run.app
- Google Cloud와 Firebase 프로젝트: `feynmi-study-20261115-d7d0d`, 리전: `asia-northeast3`.
- Firebase는 사용자가 승인한 새 프로젝트로 전환했다. 기존 Firebase 프로젝트의 사용자와 학습 데이터는 이전하지 않았으므로 새로 가입해야 한다.
- 2026-11-15 검증: 공개 로그인 화면 200, 백엔드 상태 200, 인증 없는 계정·내부 작업 요청 401. 실제 Firebase 임시 계정의 첫 계정 조회·프로필 설정·프로젝트 생성·탈퇴·삭제된 토큰 거부가 통과했고 테스트 데이터는 제거했다. 삭제 복구 Scheduler 실행도 성공했다.
- 실제 AI 분석과 브라우저 Google 로그인 전체 흐름은 검증하지 않았다. Google 공급자 활성화와 승인 도메인은 API로 확인했다.
- 업로드 장애 후 검증: 운영 서버의 인증·상태 조회를 12개 동시 요청으로 3회 실행해 36개 모두 200을 확인했다. 임시 계정은 삭제했고 브라우저 오리진의 CORS도 확인했다. 유료 AI 분석을 재실행하는 부하 시험은 수행하지 않았다.

## main 자동 배포

- Vercel 프로젝트는 `smd030830/Feynmi` 저장소에 연결했다. 운영 브랜치는 `main`이며 Vercel 빌드 명령은 `pnpm lint && pnpm typecheck && pnpm build`다. 프론트 배포는 GitHub CI와 독립적으로 이 검사를 통과해야 완료된다.
- `.github/workflows/deploy.yml`은 `main` push의 `CI` 전체 성공 후 Cloud Run을 배포한다. PR·다른 저장소의 실행은 제외하고 검사한 커밋 SHA로만 빌드한다. 최신 main보다 오래된 커밋은 배포하지 않는다.
- 장기 서비스 계정 키 대신 GitHub OIDC를 사용한다. Google의 신뢰 조건은 저장소 ID·소유자 ID·main ref·배포 워크플로 경로를 모두 제한한다. GitHub 저장소 변수 `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_DEPLOY_SERVICE_ACCOUNT`는 설정 완료했다.
- 배포 계정에는 전용 프로젝트의 Cloud Run Developer, Service Usage Consumer, 이미지 저장소 Writer, 기존 런타임·마이그레이션 계정의 actAs만 부여한다. AI 키·DB URL은 기존 Secret Manager 참조를 유지한다.
- 순서는 이미지 게시 → 기존 마이그레이션 작업 이미지 변경 → 마이그레이션 성공 대기 → 서비스 이미지 변경 → `/health` 검증이다. 서버 용량·환경변수·비밀 설정은 덮어쓰지 않는다. 임시 Google 인증 파일은 Git과 Vercel 업로드에서 제외한다.
- 현재 원격 CI는 기존 `tests/test_materials_api.py`의 AI 미설정 기대값 8개가 실제 동작과 달라 실패 중이다. 사용자가 기존 테스트 수정도 커밋에서 제외하도록 재확인했으므로 이를 변경하거나 실패 검사를 우회하지 않았다. 이 상태에서는 백엔드 자동 배포가 차단된다. 워크플로 파일을 main에 푸시하고 CI 실패를 해결해야 실제 자동 배포가 실행된다.
- 검증: 실제 Bash 배포 스크립트의 성공·마이그레이션 실패·상태 확인 실패·오래된 SHA 차단 등 8개 오프라인 테스트를 통과했다. 실제 GitHub OIDC 배포 실행은 아직 검증되지 않았다.

## 배포 준비 절차

1. GCP 프로젝트·리전·Cloud Run 서비스·이미지 저장소·Cloud SQL 연결 이름과 Vercel 프로젝트를 확정한다.
2. Cloud SQL PostgreSQL 18에 pgvector를 활성화한다. `show server_version_num`이 180000 이상 190000 미만인지 확인하고 `select extversion from pg_extension where extname = 'vector'`로 확장을 확인한다.
3. 비공개 GCS 버킷을 만들고 실제 프론트엔드 오리진에만 PUT CORS를 허용한다. Firebase의 Google·이메일 로그인과 프론트엔드 승인 도메인을 설정한다.
4. Cloud Run 런타임 계정에 필요한 Cloud SQL Client, Secret Accessor, Cloud Tasks Enqueuer, 버킷 객체 접근 권한을 부여한다. URL 서명 계정의 signBlob 권한과 Tasks OIDC 계정에 대한 actAs 권한도 확인한다. OIDC 계정은 큐와 같은 프로젝트에 둔다.
5. DB 접속 주소와 AI 키는 Secret Manager에 보관한다. 실제 값은 명령 기록·Git·화면 캡처에 남기지 않는다. 모델 ID와 effort는 환경변수로 지정한다.

## 실행 순서

1. 기존 `apps/backend/Dockerfile`의 운영 이미지를 빌드한다. 같은 이미지·계정·DB 연결·비밀 참조를 사용하는 별도 작업에서 `alembic upgrade head`를 실행한다. Cloud SQL 소켓은 `/cloudsql/PROJECT:REGION:INSTANCE`이며 기존 asyncpg URL의 host 옵션을 사용한다.
2. Cloud Run에 이미지를 배포한다. 브라우저 Firebase 토큰과 Tasks OIDC를 애플리케이션이 검증하는 단일 서비스이므로 플랫폼 접근은 공개로 두고 앱 인증을 유지한다. 요청 제한은 분석 제한과 맞추고 최대 1800초 이내로 설정한다. 저비용 시연은 `DELETION_RECOVERY_MODE=scheduled`, 요청 기반 CPU, 최소 인스턴스 0개를 사용한다. 이 경우 아래 Scheduler 작업도 함께 구성해야 한다. `background` 기본 모드는 30초 재시도 루프를 유지하므로 유휴 시 처리까지 보장하려면 인스턴스 기반 CPU와 최소 인스턴스 1개가 필요하다.
3. 실제 서비스의 HTTPS 오리진을 `PUBLIC_BASE_URL`에 넣는다. 워커 경로를 포함하지 않는다. `QUEUE_MODE=cloud_tasks`, 큐 위치·이름·OIDC 계정을 지정한다. 분석 제한은 1~30분이고 큐 재시도 정책은 architecture 7.1을 따른다.
4. 운영 환경변수를 안전하게 내보낸 셸에서 `python scripts/deployment_preflight.py`를 실행한다. 이 검사는 값을 출력하지 않고 형식만 확인하며 클라우드 권한이나 접속 성공을 증명하지 않는다. 에뮬레이터 설정은 비운다.
5. Vercel 루트를 `apps/frontend`로 지정하고 Firebase 공개 설정과 API 주소를 빌드 환경변수로 설정한다. `NEXT_PUBLIC_*` 변경 후에는 다시 빌드한다. 확정된 프론트엔드 HTTPS 오리진을 API·버킷 CORS·Firebase 승인 도메인에 반영한다.

## 유휴 비용을 줄이는 삭제 재시도

`DELETION_RECOVERY_MODE=scheduled`는 `QUEUE_MODE=cloud_tasks`와 함께 사용한다. 사용자 탈퇴 요청은 기존처럼 즉시 삭제를 시도하고, 실패한 `deleting` 행만 예약 작업에서 다시 처리한다.

Cloud Scheduler HTTP 작업을 예를 들어 15분마다 실행하도록 만든다. 대상은 `POST ${PUBLIC_BASE_URL}/api/v1/internal/tasks/retry-account-deletions`, OIDC 서비스 계정은 `TASKS_INVOKER_SA`, audience는 경로 없는 `PUBLIC_BASE_URL`이다. 분석 워커와 동일하게 서명·audience·발급 SA를 확인하며 Firebase 토큰으로 호출할 수 없다. Scheduler 서비스 에이전트의 토큰 발급 권한도 유지한다.

한 요청은 현재 대기 계정의 유한한 스냅샷을 한 번 처리하고 끝난다. 개별 계정의 삭제 실패가 다른 계정의 시도를 막지 않으며, 실패가 하나라도 있거나 DB 조회에 실패하면 `503`과 `retryable=true`를 반환해 Scheduler 재전송을 유도한다. 응답·로그에 사용자 식별자나 원본 내용을 넣지 않는다. 삭제 완료 계정을 다시 처리해도 데이터가 재생성되지 않는다.

Scheduler 작업이 없으면 서버가 꺼져 있는 동안 삭제 재시도가 실행되지 않으므로, 저비용 배포 완료 검사에 예약 작업의 인증·실행 성공을 포함한다. 로컬 기본값 `background`는 기존의 30초 루프를 사용한다.

## 공개 URL에서 최종 확인

- 실제 Firebase 계정으로 가입·인증·로그인·닉네임 설정·로그아웃한다.
- 프로젝트 생성 → 동의 → 원본 업로드 → 실제 AI 분석 → 개념 생성 → 설명·추가 질문 → 결과·근거 → 홈·기록을 확인한다.
- 두 번째 계정이 첫 계정의 자료·세션에 접근하지 못하는지 확인한다.
- 원본 재분석, 모든 기기 로그아웃, 탈퇴 후 DB·파일·Firebase 삭제와 실패 삭제 재시도를 확인한다. 탈퇴는 전용 시연 계정으로 수행한다.
- 공개 검증 결과·배포 버전·검증 일시를 기록한다. 키가 없거나 공개 환경이 없으면 이 단계는 미완료로 남긴다.

## 공식 참고

- [Cloud SQL 버전](https://docs.cloud.google.com/sql/docs/postgres/db-versions), [확장](https://docs.cloud.google.com/sql/docs/postgres/extensions), [Cloud Run 연결](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud Tasks OIDC](https://docs.cloud.google.com/tasks/docs/reference/rest/v2/OidcToken), [작업 제한](https://docs.cloud.google.com/tasks/docs/reference/rest/v2/projects.locations.queues.tasks)
- [Cloud Run 공개 접근](https://docs.cloud.google.com/run/docs/authenticating/public), [Secret Manager 연결](https://docs.cloud.google.com/run/docs/configuring/services/secrets), [CPU 과금 설정](https://docs.cloud.google.com/run/docs/configuring/billing-settings)
- [GCS 서명](https://docs.cloud.google.com/storage/docs/access-control/signing-urls-with-helpers), [CORS](https://docs.cloud.google.com/storage/docs/cross-origin), [Vercel 환경변수](https://vercel.com/docs/environment-variables)
