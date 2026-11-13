import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import account, materials, me, projects, sessions
from backend.auth.firebase import TokenVerifier, make_token_verifier
from backend.config import Settings, get_settings
from backend.db.session import make_engine, make_session_factory
from backend.errors import register_error_handlers
from backend.ingest import make_ocr
from backend.services.account import retry_deletions
from backend.services.analysis import load_llm_settings
from backend.services.cloud import AccountCloud, GoogleAccountCloud
from backend.services.storage import LocalStorage

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    token_verifier: TokenVerifier | None = None,
    account_cloud: AccountCloud | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        recovery = asyncio.create_task(
            retry_deletions(app.state.session_factory, app.state.account_cloud)
        )
        try:
            yield
        finally:
            recovery.cancel()
            with suppress(asyncio.CancelledError):
                await recovery
            await engine.dispose()

    app = FastAPI(title="Feynmi API", lifespan=lifespan)
    app.state.session_factory = make_session_factory(engine)
    # 테스트는 Firebase 없이 검증 함수를 바꿔 끼운다.
    app.state.token_verifier = token_verifier or make_token_verifier(settings.firebase_project_id)
    app.state.account_cloud = account_cloud or GoogleAccountCloud(
        settings.firebase_project_id, settings.gcs_bucket, settings.gcs_signer_service_account
    )
    # 자료 분석(architecture 7.1). 테스트는 보관소·OCR·LLM 설정을 바꿔 끼운다.
    app.state.storage = LocalStorage(settings.materials_dir)
    app.state.ocr_factory = make_ocr
    app.state.llm_settings = load_llm_settings()

    # 오류 처리 미들웨어를 먼저 등록해서 CORS 안쪽에 둔다. 서버 오류 응답에도 CORS 헤더가 붙는다.
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # 헬스 체크는 인증 없이 접두사 밖에 둔다 (Cloud Run, compose 확인용).
    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(me.router)
    api.include_router(projects.router)
    api.include_router(account.router)
    api.include_router(sessions.router)
    api.include_router(materials.router)
    # 기능 라우터는 여기에 등록한다: api.include_router(...)
    app.include_router(api)

    return app


app = create_app()
