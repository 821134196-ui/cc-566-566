"""SQLAlchemy ORM 模型。

关键关系：

* ``RoadSegment`` 一条路段可对应多张派车单与多条作业记录（同一路段可被再次撒盐）；
* ``WorkOperation`` 只追加、不更新，首次与补充作业各自独立成行；
* ``StatusHistory`` 记录路段每一次状态变化，配合 ``AuditLog`` 实现全程可追查；
* ``OperationDedup`` 保存已接受回传的幂等指纹，防止重复定位 / 重复回传多算融雪剂。
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base
from .enums import ROAD_UNCLEARED, VEHICLE_IDLE, ASSIGN_DISPATCHED


def _now():
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    display_name = Column(String(64), nullable=False)
    # 逗号分隔的角色集合：dispatcher / worker / reviewer / admin
    roles = Column(String(128), nullable=False, default="")
    created_at = Column(DateTime, default=_now)

    def has_role(self, role: str) -> bool:
        return role in (self.roles or "").split(",")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "roles": [r for r in (self.roles or "").split(",") if r],
        }


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True)
    plate = Column(String(32), unique=True, nullable=False)  # 车牌号
    driver_name = Column(String(64), nullable=False)         # 随车作业负责人
    status = Column(String(16), nullable=False, default=VEHICLE_IDLE)
    # 模拟 GPS 位置（火星坐标之类的真实坐标此处不涉及，直接用平面经纬度）
    lng = Column(Float, nullable=False, default=126.63)
    lat = Column(Float, nullable=False, default=45.75)

    def to_dict(self):
        return {
            "id": self.id,
            "plate": self.plate,
            "driver_name": self.driver_name,
            "status": self.status,
            "lng": self.lng,
            "lat": self.lat,
        }


class RoadSegment(Base):
    __tablename__ = "road_segments"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    grade = Column(String(16), nullable=False)          # 道路等级
    district = Column(String(64), nullable=False, default="")
    # 模拟地图用折线，"lng,lat;lng,lat;..."
    path = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default=ROAD_UNCLEARED)

    # 累计融雪剂用量由作业记录聚合而来，冗余存一份便于列表展示；
    # 只在服务层确认“非重复回传”后才累加。
    total_salt_kg = Column(Float, nullable=False, default=0.0)
    salt_count = Column(Integer, nullable=False, default=0)  # 有效撒盐次数

    opened_at = Column(DateTime, nullable=True)

    assignments = relationship(
        "Assignment", back_populates="segment", cascade="all, delete-orphan"
    )

    def path_points(self):
        pts = []
        for pair in (self.path or "").split(";"):
            pair = pair.strip()
            if not pair:
                continue
            lng, lat = pair.split(",")
            pts.append((float(lng), float(lat)))
        return pts

    def to_dict(self):
        pts = self.path_points()
        return {
            "id": self.id,
            "name": self.name,
            "grade": self.grade,
            "district": self.district,
            "path": [[lng, lat] for lng, lat in pts],
            "status": self.status,
            "total_salt_kg": round(self.total_salt_kg, 2),
            "salt_count": self.salt_count,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
        }


class Assignment(Base):
    """派车单：调度员把某辆车派往某条路段。

    同一路段可反复派车（故障改派、补充撒盐），每张单子独立留痕，
    不覆盖任何历史记录。
    """
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True)
    segment_id = Column(ForeignKey("road_segments.id"), nullable=False, index=True)
    vehicle_id = Column(ForeignKey("vehicles.id"), nullable=False, index=True)
    dispatcher_id = Column(ForeignKey("users.id"), nullable=False)
    status = Column(String(16), nullable=False, default=ASSIGN_DISPATCHED)
    note = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime, default=_now)
    completed_at = Column(DateTime, nullable=True)

    segment = relationship("RoadSegment", back_populates="assignments")
    vehicle = relationship("Vehicle")
    dispatcher = relationship("User")
    operations = relationship(
        "WorkOperation", back_populates="assignment", cascade="all, delete-orphan"
    )
    interruptions = relationship(
        "Interruption", back_populates="assignment", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "segment_id": self.segment_id,
            "vehicle_id": self.vehicle_id,
            "dispatcher_id": self.dispatcher_id,
            "status": self.status,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "segment_name": self.segment.name if self.segment else None,
            "vehicle_plate": self.vehicle.plate if self.vehicle else None,
        }


class WorkOperation(Base):
    """一条作业（撒盐）记录，只追加，不修改不覆盖。"""
    __tablename__ = "work_operations"

    id = Column(Integer, primary_key=True)
    assignment_id = Column(
        ForeignKey("assignments.id"), nullable=False, index=True
    )
    segment_id = Column(ForeignKey("road_segments.id"), nullable=False, index=True)
    vehicle_id = Column(ForeignKey("vehicles.id"), nullable=False)
    worker_id = Column(ForeignKey("users.id"), nullable=False)

    operated_at = Column(DateTime, nullable=False)   # 现场作业时间
    salt_kg = Column(Float, nullable=False, default=0.0)
    lng = Column(Float, nullable=False)
    lat = Column(Float, nullable=False)
    photo_path = Column(String(255), nullable=True)  # 本地相对路径
    remark = Column(String(255), nullable=False, default="")
    is_supplement = Column(Boolean, nullable=False, default=False)  # 是否补充撒盐
    sequence_no = Column(Integer, nullable=False, default=1)        # 该路段第几次有效撒盐
    client_uid = Column(String(64), nullable=True)  # 客户端幂等号（可选）
    created_at = Column(DateTime, default=_now)

    assignment = relationship("Assignment", back_populates="operations")
    segment = relationship("RoadSegment")
    vehicle = relationship("Vehicle")
    worker = relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "assignment_id": self.assignment_id,
            "segment_id": self.segment_id,
            "vehicle_id": self.vehicle_id,
            "worker_id": self.worker_id,
            "worker_name": self.worker.display_name if self.worker else None,
            "operated_at": self.operated_at.isoformat() if self.operated_at else None,
            "salt_kg": round(self.salt_kg, 2),
            "lng": self.lng,
            "lat": self.lat,
            "photo_path": self.photo_path,
            "photo_url": f"/api/photos/{self.photo_path.split('/')[-1]}"
            if self.photo_path
            else None,
            "remark": self.remark,
            "is_supplement": self.is_supplement,
            "sequence_no": self.sequence_no,
            "client_uid": self.client_uid,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OperationDedup(Base):
    """已接受作业回传的幂等记录。

    * ``client_uid``：同一客户端重复点击 / 网络重试时携带的唯一号，直接拒绝；
    * 无 client_uid 时按“派车单 + 坐标 + 时间窗口”判断重复定位，避免同一现场
      重复上报导致融雪剂用量被多算。
    """
    __tablename__ = "operation_dedup"
    __table_args__ = (
        UniqueConstraint("assignment_id", "client_uid", name="uq_dedup_uid"),
    )

    id = Column(Integer, primary_key=True)
    assignment_id = Column(ForeignKey("assignments.id"), nullable=False, index=True)
    client_uid = Column(String(64), nullable=True)
    lng = Column(Float, nullable=False)
    lat = Column(Float, nullable=False)
    operated_at = Column(DateTime, nullable=False)
    operation_id = Column(ForeignKey("work_operations.id"), nullable=False)
    created_at = Column(DateTime, default=_now)


class Interruption(Base):
    """车辆中途故障：记录中断时间、原因以及后续安排。"""
    __tablename__ = "interruptions"

    id = Column(Integer, primary_key=True)
    assignment_id = Column(
        ForeignKey("assignments.id"), nullable=False, index=True
    )
    vehicle_id = Column(ForeignKey("vehicles.id"), nullable=False)
    reporter_id = Column(ForeignKey("users.id"), nullable=False)
    reason = Column(String(255), nullable=False)
    follow_up = Column(String(255), nullable=False, default="")  # 后续安排
    status = Column(String(16), nullable=False, default="interrupted")
    started_at = Column(DateTime, nullable=False, default=_now)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now)

    assignment = relationship("Assignment", back_populates="interruptions")
    vehicle = relationship("Vehicle")
    reporter = relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "assignment_id": self.assignment_id,
            "vehicle_id": self.vehicle_id,
            "reporter_id": self.reporter_id,
            "reason": self.reason,
            "follow_up": self.follow_up,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class Review(Base):
    """复核结论。只有复核通过才允许把路段置为已开放。"""
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    segment_id = Column(ForeignKey("road_segments.id"), nullable=False, index=True)
    reviewer_id = Column(ForeignKey("users.id"), nullable=False)
    snow_status_ok = Column(Boolean, nullable=False)     # 积雪清理达标
    surface_status_ok = Column(Boolean, nullable=False)  # 路面状态达标
    passed = Column(Boolean, nullable=False)
    comment = Column(String(255), nullable=False, default="")
    reviewed_at = Column(DateTime, nullable=False, default=_now)

    segment = relationship("RoadSegment")
    reviewer = relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "segment_id": self.segment_id,
            "reviewer_id": self.reviewer_id,
            "reviewer_name": self.reviewer.display_name if self.reviewer else None,
            "snow_status_ok": self.snow_status_ok,
            "surface_status_ok": self.surface_status_ok,
            "passed": self.passed,
            "comment": self.comment,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


class StatusHistory(Base):
    """路段状态流转历史：每次 uncleared -> pending_review -> open 都留痕。"""
    __tablename__ = "status_history"

    id = Column(Integer, primary_key=True)
    segment_id = Column(ForeignKey("road_segments.id"), nullable=False, index=True)
    from_status = Column(String(16), nullable=True)
    to_status = Column(String(16), nullable=False)
    actor_id = Column(ForeignKey("users.id"), nullable=True)
    trigger = Column(String(32), nullable=False)  # dispatch / salting_done / review_pass / review_fail
    detail = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime, default=_now)

    segment = relationship("RoadSegment")
    actor = relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "segment_id": self.segment_id,
            "segment_name": self.segment.name if self.segment else None,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "actor_id": self.actor_id,
            "actor_name": self.actor.display_name if self.actor else "系统",
            "trigger": self.trigger,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(Base):
    """通用审计日志：所有关键操作（派车 / 回传 / 去重命中 / 故障 / 复核 / 越权拒绝）。"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    actor_id = Column(ForeignKey("users.id"), nullable=True)
    action = Column(String(48), nullable=False)
    target_type = Column(String(32), nullable=False, default="")
    target_id = Column(String(32), nullable=False, default="")
    detail = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=_now)

    actor = relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "actor_id": self.actor_id,
            "actor_name": self.actor.display_name if self.actor else "系统",
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
