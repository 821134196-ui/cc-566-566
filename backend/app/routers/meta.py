"""基础资料、模拟地图与模拟车辆定位。"""
import math
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..security import current_user
from ..serializers import segment_out, vehicle_out

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/segments")
def list_segments(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    rows = db.scalars(select(models.RoadSegment).order_by(models.RoadSegment.id)).all()
    return [segment_out(s) for s in rows]


@router.get("/vehicles")
def list_vehicles(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    rows = db.scalars(select(models.Vehicle).order_by(models.Vehicle.id)).all()
    return [vehicle_out(v) for v in rows]


@router.get("/map")
def map_overview(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    """地图一次性返回路段状态 + 车辆实时（模拟）位置。"""
    segments = db.scalars(select(models.RoadSegment).order_by(models.RoadSegment.id)).all()
    vehicles = db.scalars(select(models.Vehicle).order_by(models.Vehicle.id)).all()
    return {
        "segments": [segment_out(s) for s in segments],
        "vehicles": [vehicle_out(v) for v in vehicles],
        "positions": [_simulate_position(v) for v in vehicles],
        "generated_at": datetime.utcnow(),
    }


def _simulate_position(v: models.Vehicle) -> dict:
    """模拟 GPS：作业中的车沿路段折线移动，其余车辆在驻留点小幅漂移。

    以当前时间派生确定性位置（同一秒内多次请求结果一致），无需后台线程。
    """
    now = datetime.utcnow()
    t = now.timestamp()
    segment = None
    if v.current_segment_id:
        # 避免懒加载外键在序列化会话外使用，这里通过关系取（仍在会话内）
        segment = v.current_segment

    if segment is not None and v.status == models.VEHICLE_WORKING:
        geom = segment.geometry
        # 沿折线按时间循环推进
        total = len(geom) - 1
        phase = (t / 12.0) % max(total, 1)
        i = int(phase)
        frac = phase - i
        if i >= total:
            x, y = geom[-1]
        else:
            x = geom[i][0] + (geom[i + 1][0] - geom[i][0]) * frac
            y = geom[i][1] + (geom[i + 1][1] - geom[i][1]) * frac
        moving, heading = True, 0.0
    else:
        # 空闲/故障车在固定驻留点按正弦漂移
        seed = v.id * 1.7
        x = 0.08 + 0.03 * math.sin(t / 9.0 + seed)
        y = 0.9 - 0.07 * v.id + 0.02 * math.cos(t / 11.0 + seed)
        x = min(max(x, 0.02), 0.98)
        y = min(max(y, 0.02), 0.98)
        moving, heading = False, 0.0

    return {
        "vehicle_id": v.id,
        "plate": v.plate,
        "status": v.status,
        "x": round(x, 4),
        "y": round(y, 4),
        "moving": moving,
        "segment_id": v.current_segment_id,
        "ts": now,
    }
