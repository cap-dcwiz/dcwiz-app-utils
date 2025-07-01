import logging
import threading
from contextlib import contextmanager, asynccontextmanager
from typing import Dict

from redis import Redis, ConnectionPool
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker, declarative_base

DBBase = declarative_base()


class DBMixin:
    @classmethod
    async def get(cls, session, **query):
        q = select(cls).filter_by(**query)
        result = await session.execute(q)
        return result.scalars().first()

    @classmethod
    async def list(cls, session, **query):
        q = select(cls).filter_by(**query)
        result = await session.execute(q)
        return result.scalars().all()

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
        await session.delete(self)
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


_redis_pools: Dict[str, ConnectionPool] = {}
_pool_lock = threading.Lock()


def get_redis_pool(config=None) -> ConnectionPool:
    """Get or create a Redis connection pool for the given config"""
    if config is None:
        from .app import get_config
        config = get_config()

    # Create a cache key based on config
    pool_key = f"{config.get('redis.host', 'localhost')}:{config.get('redis.port', 6379)}:{config.get('redis.db', 0)}"

    with _pool_lock:
        if pool_key not in _redis_pools:
            _redis_pools[pool_key] = ConnectionPool(
                host=config.get("redis.host", "localhost"),
                port=config.get("redis.port", 6379),
                db=config.get("redis.db", 0),
                password=config.get("redis.password", None),
                max_connections=20,  # Adjust based on your needs
                retry_on_timeout=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
                decode_responses=True
            )

    return _redis_pools[pool_key]

def clean_redis_pool():
    with _pool_lock:
        for pool_key, pool in _redis_pools.items():
            try:
                pool.disconnect()
                logging.info(f"Closed Redis pool: {pool_key}")
            except Exception as e:
                logging.error(f"Error closing Redis pool {pool_key}: {e}")
        _redis_pools.clear()

@contextmanager
def redis_from_config(config=None):
    """
    Improved version with connection pooling.
    Creates connection pool once and reuses connections.
    """
    pool = get_redis_pool(config)
    redis = Redis(connection_pool=pool)
    try:
        yield redis
    finally:
        # Don't close the connection - it goes back to the pool
        pass


