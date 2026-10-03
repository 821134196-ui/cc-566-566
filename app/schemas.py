"""Pydantic 请求 / 响应模型。

作业回传走 ``multipart/form-data``（含现场照片），在路由内直接解析，
不在此定义。
"""
from pydantic import BaseModel, Field


class DispatchIn(BaseModel):
    segment_id: int
    vehicle_id: int
    note: str = ""


class InterruptionIn(BaseModel):
    reason: str = Field(min_length=2, max_length=255)
    follow_up: str = Field(default="", max_length=255)


class InterruptionResolveIn(BaseModel):
    follow_up: str = Field(default="车辆修复，继续作业", max_length=255)
    resume: bool = True  # 是否恢复原派车单作业


class PositionIn(BaseModel):
    lng: float
    lat: float


class SimTickIn(BaseModel):
    # 每辆作业中车辆沿路段折线推进的比例步长（0~1），缺省 0.08
    step: float = Field(default=0.08, ge=0.0, le=1.0)


class ReviewIn(BaseModel):
    snow_status_ok: bool
    surface_status_ok: bool
    comment: str = Field(default="", max_length=255)
