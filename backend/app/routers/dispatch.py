"""调度员派车与派车单查询、撒盐完成。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..audit import log
from ..database import get_db
from ..schemas import DispatchIn, CompleteIn
from ..security import current_user, require_roles
from ..serializers import dispatch_out

router = APIRouter(prefix="/api", tags=["dispatch"])


@router.post("/dispatches")
def create_dispatch(
    body: DispatchIn,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_roles(models.ROLE_DISPATCHER)),
):
    segment = db.get(models.RoadSegment, body.segment_id)
    vehicle = db.get(models.Vehicle, body.vehicle_id)
    if not segment or not vehicle:
        raise HTTPException(status_code=404, detail="路段或车辆不存在")

    # 调度员按道路等级派车：车辆可承担等级 min_level 数字越小能力越强，
    # 只能派给不低于路段要求的车（如三级车不能上一级路）。
    if vehicle.min_level > segment.road_level:
        raise HTTPException(
            status_code=400,
            detail=(
                f"车辆 {vehicle.plate} 只能承担{models.ROAD_LEVELS[vehicle.min_level]}及以下，"
                f"不能派往{models.ROAD_LEVELS[segment.road_level]}"
            ),
        )

    if vehicle.status == models.VEHICLE_BROKEN:
        raise HTTPException(status_code=409, detail=f"车辆 {vehicle.plate} 故障中，暂不可派")
    if vehicle.status == models.VEHICLE_WORKING:
        raise HTTPException(status_code=409, detail=f"车辆 {vehicle.plate} 正在执行其他派车单")

    if segment.status == models.SEGMENT_OPEN:
        raise HTTPException(status_code=409, detail="该路段已开放，无需再派车")
    if segment.status == models.SEGMENT_IN_REVIEW:
        raise HTTPException(status_code=409, detail="该路段正在待复核，不能重复派车；如被驳回可再派")
    if segment.current_dispatch_id:
        old = db.get(models.Dispatch, segment.current_dispatch_id)
        if old and old.status == models.DISPATCH_ACTIVE:
            raise HTTPException(status_code=409, detail="该路段已有进行中的派车单")

    d = models.Dispatch(
        segment_id=segment.id, vehicle_id=vehicle.id, dispatcher_id=actor.id,
        salt_planned_kg=body.salt_planned_kg, note=body.note,
    )
    db.add(d)
    db.flush()

    seg_from = segment.status
    segment.current_dispatch_id = d.id
    # 注意：派车本身不改变路段清理状态——只有真正回传作业后才由 untreated→salted，
    # 保证地图如实反映“尚未撒盐”。
    vehicle.status = models.VEHICLE_WORKING
    vehicle.current_segment_id = segment.id

    log(db, "segment", segment.id, "dispatch_created", actor,
        detail=f"派车 {vehicle.plate}，计划融雪剂 {body.salt_planned_kg:.0f}kg；派车单 #{d.id}")
    log(db, "dispatch", d.id, "created", actor, to_status=models.DISPATCH_ACTIVE,
        detail=f"{segment.code} {segment.name} ← {vehicle.plate}")

    db.commit()
    db.refresh(d)
    return dispatch_out(d)


@router.get("/dispatches")
def list_dispatches(
    segment_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    stmt = select(models.Dispatch).order_by(models.Dispatch.id.desc())
    if segment_id is not None:
        stmt = stmt.where(models.Dispatch.segment_id == segment_id)
    rows = db.scalars(stmt.limit(100)).all()
    return [dispatch_out(d) for d in rows]


@router.get("/dispatches/{dispatch_id}")
def get_dispatch(
    dispatch_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    d = db.get(models.Dispatch, dispatch_id)
    if not d:
        raise HTTPException(status_code=404, detail="派车单不存在")
    return dispatch_out(d)


@router.post("/dispatches/complete")
def complete_dispatch(
    body: CompleteIn,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_roles(models.ROLE_OPERATOR, models.ROLE_DISPATCHER)),
):
    """撒盐完成 → 路段进入待复核。未上传任何作业记录不允许完成。"""
    d = db.get(models.Dispatch, body.dispatch_id)
    if not d:
        raise HTTPException(status_code=404, detail="派车单不存在")

    if actor.role == models.ROLE_OPERATOR:
        vehicle = db.get(models.Vehicle, d.vehicle_id)
        if not vehicle or vehicle.operator_id != actor.id:
            raise HTTPException(status_code=403, detail="只能完成自己负责车辆的派车单")

    if d.status == models.DISPATCH_COMPLETED:
        raise HTTPException(status_code=409, detail="派车单已完成，路段已在待复核")
    if d.status != models.DISPATCH_ACTIVE:
        raise HTTPException(status_code=409, detail=f"派车单当前状态为 {d.status}，无法完成")

    open_breakdown = any(b.status == "interrupted" for b in d.breakdowns)
    if open_breakdown:
        raise HTTPException(status_code=409, detail="存在未处理的故障中断，需先记录后续安排")
    if not d.records:
        raise HTTPException(status_code=400, detail="尚未回传任何作业记录，不能标记撒盐完成")

    segment = db.get(models.RoadSegment, d.segment_id)
    vehicle = db.get(models.Vehicle, d.vehicle_id)
    seg_from = segment.status

    d.status = models.DISPATCH_COMPLETED
    d.completed_at = datetime.utcnow()
    segment.status = models.SEGMENT_IN_REVIEW
    vehicle.status = models.VEHICLE_IDLE
    vehicle.current_segment_id = None

    log(db, "dispatch", d.id, "completed", actor,
        from_status=models.DISPATCH_ACTIVE, to_status=models.DISPATCH_COMPLETED,
        detail=f"撒盐完成，累计融雪剂 {segment.salt_total_kg:.1f}kg")
    log(db, "segment", segment.id, "submit_review", actor,
        from_status=seg_from, to_status=models.SEGMENT_IN_REVIEW,
        detail="申请复核，等待复核员确认")

    db.commit()
    db.refresh(d)
    return dispatch_out(d)
