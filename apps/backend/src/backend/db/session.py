from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # 커밋 뒤에도 응답 직렬화에서 속성을 읽을 수 있게 만료시키지 않는다.
    return async_sessionmaker(engine, expire_on_commit=False)
