from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import me
from backend.auth.firebase import TokenVerifier, make_token_verifier
from backend.config import Settings, get_settings
from backend.db.session import make_engine, make_session_factory
from backend.errors import register_error_handlers

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None, token_verifier: TokenVerifier | None = None
) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    app = FastAPI(title="Feynmi API", lifespan=lifespan)
    app.state.session_factory = make_session_factory(engine)
    # 테스트는 Firebase 없이 검증 함수를 바꿔 끼운다.
    app.state.token_verifier = token_verifier or make_token_verifier(settings.firebase_project_id)

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
    # 기능 라우터는 여기에 등록한다: api.include_router(...)
    app.include_router(api)

    return app


app = create_app()
