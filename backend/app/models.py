"""数据模型：用户 / 车辆 / 路段 / 派车单 / 作业记录 / 故障中断 / 复核 / 审计日志。

路段状态机：
    untreated（未清理）
      -- 派车并上传作业记录、完成撒盐 --> in_review（待复核）
      -- 复核通过 --> open（已开放/可通行）
      -- 复核不通过 --> salted（需补盐，仍不可通行）
      -- 再次派车补盐完成 --> in_review
作业记录只追加，不覆盖；融雪剂用量按记录累加。
"""
import json
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship

from .database import Base

# --- 常量 ------------------------------------------------------------------

ROLE_DISPATCHER = "dispatcher"   # 清雪调度员
ROLE_OPERATOR = "operator"       # 作业人员（随车）
ROLE_REVIEWER = "reviewer"       # 复核员
ROLE_MANAGER = "manager"         # 管理人员

ROLE_NAMES = {
    ROLE_DISPATCHER: "调度员",
    ROLE_OPERATOR: "作业人员",
    ROLE_REVIEWER: "复核员",
    ROLE_MANAGER: "管理人员",
}

ROAD_LEVELS = {1: "一级道路（主干道）", 2: "二级道路（次干道）", 3: "三级道路（支路）"}

SEGMENT_UNTREATED = "untreated"   # 未清理
SEGMENT_SALTED = "salted"         # 已撒盐但未申请复核 / 复核驳回待补盐
SEGMENT_IN_REVIEW = "in_review"   # 待复核
SEGMENT_OPEN = "open"             # 已开放（可通行）

SEGMENT_STATUS_NAMES = {
    SEGMENT_UNTREATED: "未清理",
    SEGMENT_SALTED: "已撒盐/待补盐",
    SEGMENT_IN_REVIEW: "待复核",
    SEGMENT_OPEN: "已开放",
}

DISPATCH_ACTIVE = "active"
DISPATCH_COMPLETED = "completed"       # 本单撒盐完成，路段进入待复核
DISPATCH_INTERRUPTED = "interrupted"   # 车辆故障中断
DISPATCH_CANCELLED = "cancelled"

VEHICLE_IDLE = "idle"
VEHICLE_WORKING = "working"
VEHICLE_BROKEN = "broken"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(32), nullable=False)
    role = Column(String(16), nullable=False)
    password = Column(String(64), nullable=False)  # 本地演示：明文口令
    created_at = Column(DateTime, default=datetime.utcnow)


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True)
    plate = Column(String(16), unique=True, nullable=False)
    # 可承担的最高道路等级（1 最高）：一级路优先安排能力 1 级的车
    min_level = Column(Integer, nullable=False, default=3)
    capacity_kg = Column(Float, nullable=False, default=2000.0)
    status = Column(String(16), nullable=False, default=VEHICLE_IDLE)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    current_segment_id = Column(Integer, ForeignKey("road_segments.id"), nullable=True)

    operator = relationship("User", foreign_keys=[operator_id])
    current_segment = relationship("RoadSegment", foreign_keys=[current_segment_id])


class RoadSegment(Base):
    __tablename__ = "road_segments"

    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True, nullable=False)
    name = Column(String(64), nullable=False)
    road_level = Column(Integer, nullable=False)          # 1/2/3
    length_km = Column(Float, nullable=False, default=1.0)
    # 归一化地图折线 [[x, y], ...]，坐标 0~1，前端按比例绘制
    geometry_json = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default=SEGMENT_UNTREATED, index=True)
    salt_total_kg = Column(Float, nullable=False, default=0.0)  # 所有有效作业记录累加
    # 逻辑指向 dispatches.id；不设数据库外键以避免与 dispatches.segment_id 形成循环外键
    current_dispatch_id = Column(Integer, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    dispatches = relationship(
        "Dispatch", back_populates="segment", foreign_keys="Dispatch.segment_id"
    )
    reviews = relationship(
        "Review", back_populates="segment",
        primaryjoin="RoadSegment.id==Review.segment_id",
    )

    @property
    def geometry(self):
        return json.loads(self.geometry_json)


class Dispatch(Base):
    """派车单：调度员按道路等级把车派到路段。同一路段可多次派单（补盐）。"""
    __tablename__ = "dispatches"

    id = Column(Integer, primary_key=True)
    segment_id = Column(Integer, ForeignKey("road_segments.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    dispatcher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    salt_planned_kg = Column(Float, nullable=False, default=0.0)
    status = Column(String(16), nullable=False, default=DISPATCH_ACTIVE, index=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    segment = relationship("RoadSegment", back_populates="dispatches", foreign_keys=[segment_id])
    vehicle = relationship("Vehicle")
    dispatcher = relationship("User")
    records = relationship(
        "WorkRecord", back_populates="dispatch",
        cascade="all, delete-orphan", order_by="WorkRecord.id",
    )
    breakdowns = relationship(
        "Breakdown", back_populates="dispatch", cascade="all, delete-orphan",
        order_by="Breakdown.id",
    )


class WorkRecord(Base):
    """逐路段作业回传：作业时间、融雪剂用量、现场照片、定位。只追加，不覆盖。"""
    __tablename__ = "work_records"

    id = Column(Integer, primary_key=True)
    dispatch_id = Column(Integer, ForeignKey("dispatches.id"), nullable=False, index=True)
    segment_id = Column(Integer, ForeignKey("road_segments.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    worked_at = Column(DateTime, nullable=False)          # 现场作业时间
    salt_kg = Column(Float, nullable=False)
    photo_path = Column(String(256), nullable=True)       # 本地相对路径
    pos_x = Column(Float, nullable=False)                 # 归一化定位
    pos_y = Column(Float, nullable=False)
    client_token = Column(String(64), unique=True, nullable=True)  # 客户端幂等键
    created_at = Column(DateTime, default=datetime.utcnow)

    dispatch = relationship("Dispatch", back_populates="records")
    segment = relationship("RoadSegment")
    vehicle = relationship("Vehicle")
    operator = relationship("User")


class Breakdown(Base):
    """车辆中途故障：中断记录与后续安排。"""
    __tablename__ = "breakdowns"

    id = Column(Integer, primary_key=True)
    dispatch_id = Column(Integer, ForeignKey("dispatches.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    occurred_at = Column(DateTime, nullable=False)
    reason = Column(Text, nullable=False)
    follow_up = Column(Text, nullable=False)              # 后续安排
    status = Column(String(16), nullable=False, default="interrupted")  # interrupted/resolved
    created_at = Column(DateTime, default=datetime.utcnow)

    dispatch = relationship("Dispatch", back_populates="breakdowns")
    vehicle = relationship("Vehicle")
    operator = relationship("User")


class Review(Base):
    """路段复核结论。驳回可多次，通过一次即开放；全程留痕。"""
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    segment_id = Column(Integer, ForeignKey("road_segments.id"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    passed = Column(Boolean, nullable=False)
    snow_cleared = Column(Boolean, nullable=False)        # 积雪清除达标
    surface_safe = Column(Boolean, nullable=False)        # 路面状态达标
    note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, default=datetime.utcnow)

    segment = relationship("RoadSegment")
    reviewer = relationship("User")


class AuditLog(Base):
    """每次状态变化都写一条，可按对象追查完整轨迹。"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(24), nullable=False, index=True)  # segment/dispatch/...
    entity_id = Column(Integer, nullable=False, index=True)
    action = Column(String(48), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_name = Column(String(32), nullable=True)
    from_status = Column(String(24), nullable=True)
    to_status = Column(String(24), nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
