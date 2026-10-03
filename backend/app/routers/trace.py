"""路段详情（含全部作业/故障/复核历史）与审计时间线，保证可追查。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..security import current_user
from ..serializers import dispatch_out, review_out, segment_out

router = APIRouter(prefix="/api", tags=["trace"])


@router.get("/segments/{segment_id}/detail")
def segment_detail(
    segment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    s = db.get(models.RoadSegment, segment_id)
    if not s:
        raise HTTPException(status_code=404, detail="路段不存在")
    dispatches = db.scalars(
        select(models.Dispatch).where(models.Dispatch.segment_id == segment_id)
        .order_by(models.Dispatch.id)
    ).all()
    reviews = db.scalars(
        select(models.Review).where(models.Review.segment_id == segment_id)
        .order_by(models.Review.id)
    ).all()
    data = segment_out(s)
    data["dispatches"] = [dispatch_out(d) for d in dispatches]
    data["reviews"] = [review_out(r) for r in reviews]
    return data


@router.get("/segments/{segment_id}/timeline")
def segment_timeline(
    segment_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    """按时间合并展示：派车/作业/故障/复核以及每次状态变化。"""
    s = db.get(models.RoadSegment, segment_id)
    if not s:
        raise HTTPException(status_code=404, detail="路段不存在")

    dispatch_ids = {d.id for d in s.dispatches}
    record_ids = {r.id for d in s.dispatches for r in d.records}
    breakdown_ids = {b.id for d in s.dispatches for b in d.breakdowns}
    review_ids = {r.id for r in s.reviews}

    logs = db.scalars(
        select(models.AuditLog).order_by(models.AuditLog.id)
    ).all()
    related = [
        e for e in logs
        if (e.entity_type == "segment" and e.entity_id == segment_id)
        or (e.entity_type == "dispatch" and e.entity_id in dispatch_ids)
        or (e.entity_type == "work_record" and e.entity_id in record_ids)
        or (e.entity_type == "review" and e.entity_id in review_ids)
        or (e.entity_type == "breakdown" and e.entity_id in breakdown_ids)
    ]
    return [
        {
            "id": e.id, "entity_type": e.entity_type, "entity_id": e.entity_id,
            "action": e.action, "actor_name": e.actor_name,
            "from_status": e.from_status, "to_status": e.to_status,
            "detail": e.detail, "created_at": e.created_at,
        }
        for e in related
    ]
