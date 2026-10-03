"""复核：复核员确认积雪与路面状态达标后路段才能开放。

权限与状态约束：
- 仅复核员可提交复核结论（作业人员/调度员/管理人员均不能开放路段）；
- 作业人员不能签发自己负责路段的开放结论：凡在该路段上传过作业记录者，
  即使具备复核身份也一律拒绝（职责分离，纵深防御）；
- 只有 in_review（待复核）路段可被复核；
- 积雪清除、路面状态两项同时达标才算通过 → open（可通行）；
  任一不达标 → 驳回，退回 salted（需补盐），调度员可再次派车补盐；
- 每次结论都留存，状态变化全部写审计日志。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from .. import models
from ..audit import log
from ..database import get_db
from ..schemas import ReviewIn
from ..security import require_roles
from ..serializers import review_out

router = APIRouter(prefix="/api/reviews", tags=["review"])


def _worked_on_segment(db: Session, user_id: int, segment_id: int) -> bool:
    return db.scalar(
        select(exists().where(
            models.WorkRecord.operator_id == user_id,
            models.WorkRecord.segment_id == segment_id,
        ))
    )


@router.post("")
def submit_review(
    body: ReviewIn,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_roles(models.ROLE_REVIEWER)),
):
    segment = db.get(models.RoadSegment, body.segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="路段不存在")

    # 作业人员不能签发自己负责路段的开放结论
    if _worked_on_segment(db, actor.id, segment.id):
        raise HTTPException(
            status_code=403,
            detail="职责分离：您在该路段上传过作业记录，不能签发本路段的开放结论",
        )

    if segment.status == models.SEGMENT_OPEN:
        raise HTTPException(status_code=409, detail="该路段已开放，无需重复复核")
    if segment.status != models.SEGMENT_IN_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"路段当前为「{models.SEGMENT_STATUS_NAMES[segment.status]}」，"
                   "只有撒盐完成并进入待复核后才能复核；未复核路段不能开放",
        )

    passed = bool(body.snow_cleared and body.surface_safe)
    review = models.Review(
        segment_id=segment.id, reviewer_id=actor.id, passed=passed,
        snow_cleared=body.snow_cleared, surface_safe=body.surface_safe,
        note=body.note,
    )
    db.add(review)

    from_status = segment.status
    if passed:
        segment.status = models.SEGMENT_OPEN
        segment.opened_at = datetime.utcnow()
        action, detail = "review_passed", "复核通过：积雪清除、路面状态达标，路段开放通行"
    else:
        segment.status = models.SEGMENT_SALTED
        segment.current_dispatch_id = None  # 旧单封存，等待调度员重新派车补盐
        reasons = []
        if not body.snow_cleared:
            reasons.append("积雪清除不达标")
        if not body.surface_safe:
            reasons.append("路面结冰/湿滑不达标")
        action, detail = "review_rejected", "复核驳回：" + "、".join(reasons) + "，需补盐后重新申请复核"

    db.add(review)
    db.flush()  # 取得 review.id 后再写审计

    log(db, "review", review.id, action, actor,
        detail=(detail + (f"；意见：{body.note}" if body.note else "")))
    log(db, "segment", segment.id, action, actor,
        from_status=from_status, to_status=segment.status, detail=detail)

    db.commit()
    db.refresh(review)
    return review_out(review)


@router.get("")
def list_reviews(
    segment_id: int | None = None,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_roles(
        models.ROLE_REVIEWER, models.ROLE_MANAGER, models.ROLE_DISPATCHER
    )),
):
    stmt = select(models.Review).order_by(models.Review.id.desc())
    if segment_id is not None:
        stmt = stmt.where(models.Review.segment_id == segment_id)
    return [review_out(r) for r in db.scalars(stmt.limit(200)).all()]
