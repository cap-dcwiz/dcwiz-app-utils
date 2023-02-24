from contextlib import contextmanager, asynccontextmanager

from redis import Redis
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker, declarative_base

_DBBase = declarative_base()


class DBBase(_DBBase):
    @classmethod
    async def get(cls, session, **query):
        q = select(cls).filter_by(**query)
        result = await session.execute(q)
        return result.scalars().first()

    async def update(self, session, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        session.add(self)
        await session.commit()
        await session.refresh(self)

    @classmethod
    async def add(cls, session, **kwargs):
        obj = cls(**kwargs)
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj

    async def delete(self, session):
        session.delete(self)
        await session.commit()


class WithDB:
    def __init__(self, *args, sql_uri=None, **kwargs):
        self.db_engine = create_engine(sql_uri)
        self.session_cls = sessionmaker(
            autocommit=False, autoflush=False, bind=self.db_engine
        )
        super().__init__(*args, **kwargs)

    @contextmanager
    def db_session(self):
        session = self.session_cls()
        try:
            yield session
        finally:
            session.close()

    @classmethod
    def from_config(cls, config=None):
        if config is None:
            from .app import get_config

            config = get_config()
        return cls(sql_uri=config["sqlalchemy.url"])


class WithAsyncDB:
    def __init__(self, *args, sql_uri=None, **kwargs):
        self.db_engine = create_async_engine(sql_uri)
        self.session_cls = async_sessionmaker(
            autocommit=False, autoflush=False, bind=self.db_engine
        )
        super().__init__(*args, **kwargs)

    @asynccontextmanager
    async def db_session(self):
        session = self.session_cls()
        try:
            yield session
        finally:
            await session.close()

    @classmethod
    def from_config(cls, config=None):
        if config is None:
            from .app import get_config

            config = get_config()
        return cls(sql_uri=config["sqlalchemy.url"])


@contextmanager
def db_session_from_config(config=None):
    if config is None:
        from .app import get_config

        config = get_config()
    engine = create_engine(config["sqlalchemy.url"])
    session_cls = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_cls()
    try:
        yield session
    finally:
        session.close()


@asynccontextmanager
async def async_db_session_from_config(config=None):
    if config is None:
        from .app import get_config

        config = get_config()
    engine = create_async_engine(config["sqlalchemy.url"])
    session_cls = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_cls()
    try:
        yield session
    finally:
        await session.close()


@contextmanager
def redis_from_config(config=None):
    if config is None:
        from .app import get_config

        config = get_config()
    redis = Redis(
        host=config.get("redis.host", "localhost"),
        port=config.get("redis.port", 6379),
        db=config.get("redis.db", 0),
        password=config.get("redis.password", None),
    )
    yield redis
    redis.close()
