"""SQLite / SQLAlchemy 基础配置。

通过环境变量 ``SNOW_DB_PATH`` 可指定数据库文件位置，
测试时把它指向临时目录即可做到数据隔离。
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

_DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "snow.db"
)
DB_PATH = os.environ.get("SNOW_DB_PATH", _DEFAULT_DB)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
