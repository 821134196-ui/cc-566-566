"""Pydantic 请求/响应模型。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# --- 认证 -------------------------------------------------------------------

class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    role: str
    roles: List[str] = []
    role_name: str
    perms: dict = {}

    class Config:
        from_attributes = True


# --- 基础资料 ---------------------------------------------------------------

class VehicleOut(BaseModel):
    id: int
    plate: str
    min_level: int
    capacity_kg: float
    status: str
    operator_id: Optional[int] = None
    operator_name: Optional[str] = None
    current_segment_id: Optional[int] = None


class SegmentOut(BaseModel):
    id: int
    code: str
    name: str
    road_level: int
    road_level_name: str
    length_km: float
    geometry: List[List[float]]
    status: str
    status_name: str
    salt_total_kg: float
    current_dispatch_id: Optional[int] = None
    opened_at: Optional[datetime] = None


# --- 派车 -------------------------------------------------------------------

class DispatchIn(BaseModel):
    segment_id: int
    vehicle_id: int
    salt_planned_kg: float = Field(ge=0, default=0)
    note: Optional[str] = None


class DispatchOut(BaseModel):
    id: int
    segment_id: int
    vehicle_id: int
    vehicle_plate: str
    dispatcher_name: str
    salt_planned_kg: float
    status: str
    note: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    records: List["WorkRecordOut"] = []
    breakdowns: List["BreakdownOut"] = []


# --- 作业回传 ---------------------------------------------------------------

class WorkRecordInJSON(BaseModel):
    """无照片时的纯 JSON 回传。"""
    dispatch_id: int
    worked_at: Optional[datetime] = None
    salt_kg: float = Field(ge=0)
    pos_x: float = Field(ge=0, le=1)
    pos_y: float = Field(ge=0, le=1)
    client_token: Optional[str] = Field(default=None, max_length=64)


class WorkRecordOut(BaseModel):
    id: int
    dispatch_id: int
    segment_id: int
    vehicle_id: int
    operator_name: str
    worked_at: datetime
    salt_kg: float
    photo_url: Optional[str] = None
    pos_x: float
    pos_y: float
    client_token: Optional[str] = None
    created_at: datetime
    duplicate: bool = False


class CompleteIn(BaseModel):
    dispatch_id: int


# --- 故障 -------------------------------------------------------------------

class BreakdownIn(BaseModel):
    dispatch_id: int
    occurred_at: Optional[datetime] = None
    reason: str = Field(min_length=1)
    follow_up: str = Field(min_length=1)


class BreakdownResolveIn(BaseModel):
    follow_up_result: str = Field(min_length=1)


class BreakdownOut(BaseModel):
    id: int
    dispatch_id: int
    vehicle_id: int
    vehicle_plate: str
    operator_name: str
    occurred_at: datetime
    reason: str
    follow_up: str
    status: str
    created_at: datetime


# --- 复核 -------------------------------------------------------------------

class ReviewIn(BaseModel):
    segment_id: int
    snow_cleared: bool
    surface_safe: bool
    note: Optional[str] = None


class ReviewOut(BaseModel):
    id: int
    segment_id: int
    reviewer_name: str
    passed: bool
    snow_cleared: bool
    surface_safe: bool
    note: Optional[str] = None
    reviewed_at: datetime


# --- 时间线 -----------------------------------------------------------------

class AuditOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    action: str
    actor_name: Optional[str] = None
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    detail: Optional[str] = None
    created_at: datetime


class SegmentDetailOut(SegmentOut):
    dispatches: List[DispatchOut] = []
    reviews: List[ReviewOut] = []


# 前向引用补全
DispatchOut.model_rebuild()
