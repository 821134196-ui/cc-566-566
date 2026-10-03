"""应用配置：路径、数据库、盐量去重容差等。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
PROJECT_DIR = BASE_DIR.parent                               # /workspace
DATA_DIR = Path(os.environ.get("SNOW_DATA_DIR", PROJECT_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

PHOTO_DIR = DATA_DIR / "photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("SNOW_DB_PATH", DATA_DIR / "snow.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# 相同 (派车单, 车辆, 坐标) 的作业回传，若盐量差值与时间间隔均在容差内，视为重复回传
SALT_DEDUP_TOLERANCE_KG = float(os.environ.get("SNOW_SALT_TOLERANCE", "0.5"))
DEDUP_WINDOW_SECONDS = int(os.environ.get("SNOW_DEDUP_WINDOW", "300"))
