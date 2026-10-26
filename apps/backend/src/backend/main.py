from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import Settings, get_settings
from backend.errors import register_error_handlers

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Feynmi API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_error_handlers(app)

    # 헬스 체크는 인증 없이 접두사 밖에 둔다 (Cloud Run, compose 확인용).
    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    api = APIRouter(prefix=API_PREFIX)
    # 기능 라우터는 여기에 등록한다: api.include_router(...)
    app.include_router(api)

    return app


app = create_app()
