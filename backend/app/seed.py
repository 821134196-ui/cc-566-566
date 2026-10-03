"""初始化数据库表与演示数据（幂等：已有数据则跳过）。"""
import json

from sqlalchemy import select

from . import models
from .database import Base, engine, SessionLocal

# 归一化坐标的模拟路网（x/y ∈ 0~1），前端按比例绘制
_SEGMENTS = [
    ("R101", "解放路一段", 1, 2.4, [[.05, .22], [.30, .22], [.55, .22], [.95, .22]]),
    ("R102", "中山大道",   1, 3.1, [[.05, .70], [.35, .70], [.65, .70], [.95, .70]]),
    ("R201", "建设大街",   2, 2.0, [[.20, .05], [.20, .35], [.20, .60], [.20, .95]]),
    ("R202", "人民西路",   2, 2.6, [[.55, .05], [.55, .30], [.55, .55], [.55, .95]]),
    ("R203", "滨河路",     2, 1.8, [[.30, .88], [.55, .88], [.80, .88]]),
    ("R301", "和平支路",   3, 1.1, [[.05, .45], [.25, .45], [.45, .45]]),
    ("R302", "文化巷",     3, 0.9, [[.78, .28], [.78, .55], [.90, .55], [.90, .85]]),
    ("R303", "站前街",     3, 0.7, [[.35, .12], [.55, .12], [.70, .05]]),
]

# username, name, role, password
_USERS = [
    ("manager",    "张管理", models.ROLE_MANAGER,                   "123456"),
    ("dispatcher", "刁调度", models.ROLE_DISPATCHER,                "123456"),
    ("reviewer",   "王复核", models.ROLE_REVIEWER,                  "123456"),
    ("li",         "李作业", models.ROLE_OPERATOR,                  "123456"),
    ("zhao",       "赵作业", models.ROLE_OPERATOR,                  "123456"),
    ("sun",        "孙作业", models.ROLE_OPERATOR,                  "123456"),
    # 同时具备作业与复核身份，用于验证“作业人员不能签发自己路段”的职责分离
    ("chen",       "陈兼岗", f"{models.ROLE_OPERATOR},{models.ROLE_REVIEWER}", "123456"),
]

# plate, min_level, capacity, operator_username
_VEHICLES = [
    ("黑A·X101", 1, 3000, "li"),
    ("黑A·X102", 1, 2800, "zhao"),
    ("黑A·X201", 2, 2000, "chen"),
    ("黑A·X301", 3, 1500, "sun"),
]


def init_db(seed: bool = True):
    Base.metadata.create_all(bind=engine)
    if not seed:
        return
    db = SessionLocal()
    try:
        if db.scalar(select(models.User).limit(1)):
            return

        users = {}
        for username, name, role, pwd in _USERS:
            u = models.User(username=username, name=name, role=role, password=pwd)
            db.add(u)
            users[username] = u
        db.flush()

        for code, name, level, length, geom in _SEGMENTS:
            db.add(models.RoadSegment(
                code=code, name=name, road_level=level, length_km=length,
                geometry_json=json.dumps(geom),
            ))

        for plate, min_level, cap, op_username in _VEHICLES:
            db.add(models.Vehicle(
                plate=plate, min_level=min_level, capacity_kg=cap,
                status=models.VEHICLE_IDLE, operator_id=users[op_username].id,
            ))

        db.commit()
    finally:
        db.close()
