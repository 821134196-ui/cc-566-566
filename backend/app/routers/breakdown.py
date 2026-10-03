"""车辆中途故障：记录中断、后续安排，以及恢复处理。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..audit import log
from ..database import get_db
from ..schemas import BreakdownIn, BreakdownResolveIn
from ..security import current_user, require_roles
from ..serializers import breakdown_out

router = APIRouter(prefix="/api/breakdowns", tags=["breakdown"])


def _owned_dispatch(db: Session, dispatch_id: int, actor: models.User) -> models.Dispatch:
    d = db.get(models.Dispatch, dispatch_id)
    if not d:
        raise HTTPException(status_code=404, detail="派车单不存在")
    if actor.role == models.ROLE_OPERATOR:
        vehicle = db.get(models.Vehicle, d.vehicle_id)
        if vehicle.operator_id != actor.id:
            raise HTTPException(status_code=403, detail="只能登记自己负责车辆的故障")
    return d


@router.post("")
def report_breakdown(
    body: BreakdownIn,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_roles(models.ROLE_OPERATOR, models.ROLE_DISPATCHER)),
):
    d = _owned_dispatch(db, body.dispatch_id, actor)
    if d.status not in (models.DISPATCH_ACTIVE, models.DISPATCH_INTERRUPTED):
        raise HTTPException(status_code=409, detail=f"派车单状态为 {d.status}，不能登记故障")

    occurred_at = body.occurred_at or datetime.utcnow()
    b = models.Breakdown(
        dispatch_id=d.id, vehicle_id=d.vehicle_id, operator_id=actor.id,
        occurred_at=occurred_at, reason=body.reason, follow_up=body.follow_up,
        status="interrupted",
    )
    db.add(b)
    db.flush()

    segment = db.get(models.RoadSegment, d.segment_id)
    vehicle = db.get(models.Vehicle, d.vehicle_id)
    was_active = d.status == models.DISPATCH_ACTIVE
    d.status = models.DISPATCH_INTERRUPTED
    vehicle.status = models.VEHICLE_BROKEN
    vehicle.current_segment_id = segment.id  # 故障车仍停在该路段

    log(db, "breakdown", b.id, "reported", actor, to_status="interrupted",
        detail=f"车辆 {vehicle.plate} 在 {segment.code} 故障：{body.reason}；后续安排：{body.follow_up}")
    if was_active:
        log(db, "dispatch", d.id, "interrupted", actor,
            from_status=models.DISPATCH_ACTIVE, to_status=models.DISPATCH_INTERRUPTED,
            detail=f"车辆故障，作业中断（故障单 #{b.id}）")

    db.commit()
    db.refresh(b)
    return breakdown_out(b)


@router.post("/{breakdown_id}/resolve")
def resolve_breakdown(
    breakdown_id: int,
    body: BreakdownResolveIn,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_roles(models.ROLE_OPERATOR, models.ROLE_DISPATCHER)),
):
    b = db.get(models.Breakdown, breakdown_id)
    if not b:
        raise HTTPException(status_code=404, detail="故障记录不存在")
    d = _owned_dispatch(db, b.dispatch_id, actor)
    if b.status == "resolved":
        raise HTTPException(status_code=409, detail="该故障已处理")

    b.status = "resolved"
    vehicle = db.get(models.Vehicle, b.vehicle_id)
    vehicle.status = models.VEHICLE_WORKING
    d.status = models.DISPATCH_ACTIVE  # 维修/改派后继续作业

    log(db, "breakdown", b.id, "resolved", actor,
        from_status="interrupted", to_status="resolved",
        detail=f"后续处理结果：{body.follow_up_result}")
    log(db, "dispatch", d.id, "resume", actor,
        from_status=models.DISPATCH_INTERRUPTED, to_status=models.DISPATCH_ACTIVE,
        detail=f"故障解除，车辆 {vehicle.plate} 恢复作业")

    db.commit()
    db.refresh(b)
    return breakdown_out(b)


@router.get("")
def list_breakdowns(
    dispatch_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    from sqlalchemy import select
    stmt = select(models.Breakdown).order_by(models.Breakdown.id.desc())
    if dispatch_id is not None:
        stmt = stmt.where(models.Breakdown.dispatch_id == dispatch_id)
    return [breakdown_out(b) for b in db.scalars(stmt.limit(100)).all()]
