# Feynmi
팀플 github

## 개인 설정

저장소 루트의 `.env.example`을 `.env`로 복사하고 Firebase 값을 채웁니다.
`NEXT_PUBLIC_API_BASE_URL`은 로컬에서 `http://localhost:8000`을 사용합니다.
`.env`와 개인 IDE·에이전트 설정(`.idea`, `.vscode`, `.run`, `.claude`, `.codex`)은
Git 추적에서 제외합니다. 실행 설정은 각 PC에 유지하며 공유할 환경변수 이름은
값이 없는 `.env.example`에 추가합니다.

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

## 학습자료 업로드와 분석 시험

자료를 올리면 글자 추출(그림은 OCR) → 조각·임베딩 저장 → 개념 추출까지 백엔드가 처리합니다.

**준비**

- 저장소 루트 `.env.llm`에 AI 키와 모델을 넣습니다(`.env.llm.example` 참고).
  없으면 업로드와 글자 추출까지만 되고 개념은 만들어지지 않습니다.
- `.env`의 `GCS_BUCKET`을 비워 두면 원본을 로컬 GCS 에뮬레이터(compose의 `gcs` 서비스)에 보관합니다.
  개발용 버킷이나 클라우드 설정 없이 시험할 수 있습니다. 버킷을 넣으면 그 버킷을 씁니다.

**실행**

`Backend start` → `Frontend dev` 순서로 실행합니다. `Backend start`는 DB, GCS 에뮬레이터, 백엔드를 함께 켜고
백엔드 의존성(파서·OCR 라이브러리, Tesseract)이 바뀌었으면 이미지를 다시 만듭니다.
pull 뒤 첫 실행은 이미지 빌드로 몇 분 걸릴 수 있습니다. 이미 켜 둔 `Frontend dev`가 있으면 pull 뒤에 다시 시작합니다(이전 화면 코드가 남아 업로드가 404로 실패할 수 있음).
터미널에서는 저장소 루트에서 `docker compose up -d --build --wait db gcs backend`로 같은 동작을 합니다.

**화면에서 확인**

1. 로그인 → 프로젝트 만들기 → 학습자료 탭에서 파일을 끌어다 놓거나 `학습자료 업로드`를 누릅니다.
   PDF, PPTX, HWP, HWPX, DOCX, TXT, PNG, JPG, HEIC를 여러 개 한 번에 올릴 수 있습니다(파일당 50MB).
2. 처음 올릴 때 외부 AI 전송 안내에 동의합니다.
3. 상태가 `업로드 중 → 분석 대기 → 글자 추출 중 → 개념 생성 중 → 분석 완료`로 바뀝니다.
   그림이 많은 자료는 1~2분 걸립니다. 실패하면 사유와 `재시도` 버튼이 나옵니다.
4. 개념 탭에서 개념을 확인하고 `학습하기`로 설명 학습을 시작합니다.

**DB에서 확인 (선택)**

IntelliJ Database 창에서 PostgreSQL `localhost:5432`, 사용자·비밀번호 `feynmi`, DB `feynmi`로 연결합니다.

```sql
-- 자료별 쪽·조각 수와 임베딩 차원(1536)
select m.title, m.page_count as 쪽, count(c.id) as 조각, min(vector_dims(c.embedding)) as 차원
from materials m left join chunks c on c.material_id = m.id
group by m.id order by m.created_at desc;

-- 개념과 요소 수
select k.title as 개념, count(e.id) as 요소
from concepts k left join concept_elements e on e.concept_id = k.id
group by k.id order by k.material_id, k.ordinal;
```
터미널에서는 `apps/frontend`에서 `pnpm backend:start`, `pnpm backend:stop`으로도 실행할 수 있습니다.
