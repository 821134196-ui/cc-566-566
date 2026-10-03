"""SQLAlchemy 引擎与会话。SQLite 开启外键约束。"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

connect_args = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)


@event.listens_for(engine, "connect")
def _enable_fk(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
