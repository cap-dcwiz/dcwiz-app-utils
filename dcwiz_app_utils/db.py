from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from redis import Redis

DBBase = declarative_base()


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
