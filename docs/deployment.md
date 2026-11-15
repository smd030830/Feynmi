# 운영 배포와 검증

PRD 9.1과 architecture 11장의 Vercel·Cloud Run·Cloud SQL·Cloud Storage·Cloud Tasks 구성을 따른다. 이 문서는 배포 실행 또는 공개 환경 검증 완료를 뜻하지 않는다.

## 이번 배포의 비용 조건

- 프론트엔드는 Vercel Hobby 플랜만 사용하며 유료 플랜으로 전환하지 않는다.
- Google Cloud는 유료 전환하지 않은 무료체험 계정의 남은 크레딧과 기간이 확인될 때만 배포한다. 일반 유료 결제 계정의 무료 사용량만으로 비용 0원을 보장하지 않는다.
- CLI의 결제 계정 `open=true`나 `My Billing Account`라는 이름은 무료체험 증거가 아니다. 계정 종류·잔액·기한이 확인되기 전에는 결제를 연결하거나 사용량이 발생하는 자원을 생성하지 않는다.
- 기존 프로젝트를 변경하지 않고 Feynmi 전용 프로젝트를 사용한다. 생성된 프로젝트·연결 상태는 Git 제외 로컬 기록으로 관리한다.
- Vercel 업로드는 `.vercelignore`로 개인 환경변수·인증·로컬 테스트·자료를 제외한다. 프로젝트 Root Directory는 `apps/frontend`, 공유 타입을 위해 루트 외 소스 포함을 켠다.
- 배포 검증 중 OpenRouter 유료 AI 호출은 수행하지 않는다. 사용자가 배포 후 직접 실행하는 AI 분석·평가는 별도의 API 비용이 발생할 수 있다.

## 배포 전

1. GCP 프로젝트·리전·Cloud Run 서비스·이미지 저장소·Cloud SQL 연결 이름과 Vercel 프로젝트를 확정한다.
2. Cloud SQL PostgreSQL 18에 pgvector를 활성화한다. `show server_version_num`이 180000 이상 190000 미만인지 확인하고 `select extversion from pg_extension where extname = 'vector'`로 확장을 확인한다.
3. 비공개 GCS 버킷을 만들고 실제 프론트엔드 오리진에만 PUT CORS를 허용한다. Firebase의 Google·이메일 로그인과 프론트엔드 승인 도메인을 설정한다.
4. Cloud Run 런타임 계정에 필요한 Cloud SQL Client, Secret Accessor, Cloud Tasks Enqueuer, 버킷 객체 접근 권한을 부여한다. URL 서명 계정의 signBlob 권한과 Tasks OIDC 계정에 대한 actAs 권한도 확인한다. OIDC 계정은 큐와 같은 프로젝트에 둔다.
5. DB 접속 주소와 AI 키는 Secret Manager에 보관한다. 실제 값은 명령 기록·Git·화면 캡처에 남기지 않는다. 모델 ID와 effort는 환경변수로 지정한다.

## 실행 순서

1. 기존 `apps/backend/Dockerfile`의 운영 이미지를 빌드한다. 같은 이미지·계정·DB 연결·비밀 참조를 사용하는 별도 작업에서 `alembic upgrade head`를 실행한다. Cloud SQL 소켓은 `/cloudsql/PROJECT:REGION:INSTANCE`이며 기존 asyncpg URL의 host 옵션을 사용한다.
2. Cloud Run에 이미지를 배포한다. 브라우저 Firebase 토큰과 Tasks OIDC를 애플리케이션이 검증하는 단일 서비스이므로 플랫폼 접근은 공개로 두고 앱 인증을 유지한다. 요청 제한은 분석 제한과 맞추고 최대 1800초 이내로 설정한다. 삭제 재시도 루프가 유휴 시에도 실행되도록 인스턴스 기반 CPU와 최소 인스턴스 1개를 사용한다.
3. 실제 서비스의 HTTPS 오리진을 `PUBLIC_BASE_URL`에 넣는다. 워커 경로를 포함하지 않는다. `QUEUE_MODE=cloud_tasks`, 큐 위치·이름·OIDC 계정을 지정한다. 분석 제한은 1~30분이고 큐 재시도 정책은 architecture 7.1을 따른다.
4. 운영 환경변수를 안전하게 내보낸 셸에서 `python scripts/deployment_preflight.py`를 실행한다. 이 검사는 값을 출력하지 않고 형식만 확인하며 클라우드 권한이나 접속 성공을 증명하지 않는다. 에뮬레이터 설정은 비운다.
5. Vercel 루트를 `apps/frontend`로 지정하고 Firebase 공개 설정과 API 주소를 빌드 환경변수로 설정한다. `NEXT_PUBLIC_*` 변경 후에는 다시 빌드한다. 확정된 프론트엔드 HTTPS 오리진을 API·버킷 CORS·Firebase 승인 도메인에 반영한다.

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
