from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

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
