"""作业回传：逐路段上传作业时间、融雪剂用量、现场照片与定位。

关键规则：
1. 同一路段再次撒盐 → 追加新作业记录，首次记录永不覆盖，盐量累加；
2. 重复定位/重复回传不能多算融雪剂：client_token 命中，或
   （同派车单 + 近似定位 + 近似盐量 + 时间窗内）均判定为重复回传，
   返回已存在的记录并标记 duplicate=true，不写库、不加盐量，但记审计；
3. 只有该派车单车辆所属作业人员能回传。
"""
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..audit import log
from ..config import DEDUP_WINDOW_SECONDS, PHOTO_DIR, SALT_DEDUP_TOLERANCE_KG
from ..database import get_db
from ..security import current_user, require_roles
from ..serializers import record_out
from ..schemas import WorkRecordInJSON

router = APIRouter(prefix="/api/work-records", tags=["work"])

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_POS_GRID = 1000  # 定位去重网格：归一化坐标千分之一（约百米级）
MAX_PHOTO_BYTES = 10 * 1024 * 1024


def _find_duplicate(db: Session, dispatch_id: int, salt_kg: float,
                    pos_x: float, pos_y: float, worked_at: datetime,
                    client_token: str | None):
    """先按 client_token 精确去重，再按定位+用量+时间窗启发式去重。"""
    if client_token:
        hit = db.scalar(
            select(models.WorkRecord).where(
                models.WorkRecord.client_token == client_token
            )
        )
        if hit:
            return hit, "client_token"

    gx, gy = round(pos_x * _POS_GRID), round(pos_y * _POS_GRID)
    since = worked_at - timedelta(seconds=DEDUP_WINDOW_SECONDS)
    until = worked_at + timedelta(seconds=DEDUP_WINDOW_SECONDS)
    candidates = db.scalars(
        select(models.WorkRecord).where(
            models.WorkRecord.dispatch_id == dispatch_id,
            models.WorkRecord.worked_at >= since,
            models.WorkRecord.worked_at <= until,
        ).order_by(models.WorkRecord.id.desc())
    ).all()
    for r in candidates:
        same_spot = (round(r.pos_x * _POS_GRID) == gx and round(r.pos_y * _POS_GRID) == gy)
        same_salt = abs(r.salt_kg - salt_kg) <= SALT_DEDUP_TOLERANCE_KG
        if same_spot and same_salt:
            return r, "position+salt"
    return None, None


def _save_photo(record_id: int, upload: UploadFile) -> str:
    ext = Path(upload.filename or "").suffix.lower()
    if upload.content_type and upload.content_type not in _ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="照片格式不支持，请上传图片文件")
    if not ext or ext not in _ALLOWED_EXT:
        ext = ".jpg"  # 某些客户端不带扩展名，按 content_type 已校验
    data = upload.file.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="照片不能超过 10MB")
    name = f"r{record_id}_{uuid.uuid4().hex[:10]}{ext}"
    (PHOTO_DIR / name).write_bytes(data)
    return os.path.join("photos", name)  # 相对 data/ 的路径


def _create_record(db: Session, actor: models.User, *, dispatch_id: int,
                   salt_kg: float, pos_x: float, pos_y: float,
                   worked_at: datetime | None, client_token: str | None,
                   photo: UploadFile | None) -> dict:
    worked_at = worked_at or datetime.utcnow()

    d = db.get(models.Dispatch, dispatch_id)
    if not d:
        raise HTTPException(status_code=404, detail="派车单不存在")
    segment = db.get(models.RoadSegment, d.segment_id)

    vehicle = db.get(models.Vehicle, d.vehicle_id)
    if actor.role == models.ROLE_OPERATOR and vehicle.operator_id != actor.id:
        raise HTTPException(status_code=403, detail="只能为本车辆负责的派车单回传作业")

    if d.status == models.DISPATCH_COMPLETED:
        raise HTTPException(status_code=409, detail="派车单已完成（路段待复核），不能再回传；如被驳回会生成新派车单")
    if d.status != models.DISPATCH_ACTIVE:
        raise HTTPException(status_code=409, detail=f"派车单状态为 {d.status}，不能回传作业")
    if segment.status == models.SEGMENT_OPEN:
        raise HTTPException(status_code=409, detail="路段已开放，无需继续作业")

    # 幂等去重——重复回传直接返回原记录，不加盐量、不覆盖任何历史
    dup, reason = _find_duplicate(
        db, dispatch_id, salt_kg, pos_x, pos_y, worked_at, client_token
    )
    if dup:
        log(db, "work_record", dup.id, "duplicate_upload_ignored", actor,
            detail=(
                f"重复回传被忽略（判定依据 {reason}）：盐量 {salt_kg:.1f}kg @ "
                f"({pos_x:.3f},{pos_y:.3f})，未重复计盐量"
            ))
        db.commit()
        return record_out(dup, duplicate=True)

    record = models.WorkRecord(
        dispatch_id=dispatch_id, segment_id=d.segment_id, vehicle_id=d.vehicle_id,
        operator_id=actor.id, worked_at=worked_at, salt_kg=salt_kg,
        pos_x=pos_x, pos_y=pos_y, client_token=client_token,
    )
    db.add(record)
    db.flush()  # 取 id

    if photo is not None and photo.filename:
        record.photo_path = _save_photo(record.id, photo)

    # 追加而非覆盖：路段累计盐量只增；历史记录全部保留
    seg_from = segment.status
    segment.salt_total_kg = round(segment.salt_total_kg + salt_kg, 3)
    if segment.status == models.SEGMENT_UNTREATED:
        segment.status = models.SEGMENT_SALTED

    log(db, "work_record", record.id, "uploaded", actor,
        detail=(
            f"派车单 #{d.id} 第 {len(d.records)} 次作业，本次 {salt_kg:.1f}kg，"
            f"路段累计 {segment.salt_total_kg:.1f}kg"
            + ("，含现场照片" if record.photo_path else "")
        ))
    if seg_from != segment.status:
        log(db, "segment", segment.id, "status_change", actor,
            from_status=seg_from, to_status=segment.status, detail="首次作业回传")

    db.commit()
    db.refresh(record)
    return record_out(record)


@router.post("")
async def upload_json(
    body: WorkRecordInJSON,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_roles(models.ROLE_OPERATOR, models.ROLE_DISPATCHER)),
):
    """纯 JSON 回传（无照片）。"""
    return _create_record(
        db, actor, dispatch_id=body.dispatch_id, salt_kg=body.salt_kg,
        pos_x=body.pos_x, pos_y=body.pos_y, worked_at=body.worked_at,
        client_token=body.client_token, photo=None,
    )


@router.post("/photo")
async def upload_photo(
    dispatch_id: int = Form(...),
    salt_kg: float = Form(..., ge=0),
    pos_x: float = Form(..., ge=0, le=1),
    pos_y: float = Form(..., ge=0, le=1),
    worked_at: datetime | None = Form(default=None),
    client_token: str | None = Form(default=None, max_length=64),
    photo: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_roles(models.ROLE_OPERATOR, models.ROLE_DISPATCHER)),
):
    """带现场照片的作业回传（multipart），照片保存到本地 data/photos。"""
    return _create_record(
        db, actor, dispatch_id=dispatch_id, salt_kg=salt_kg,
        pos_x=pos_x, pos_y=pos_y, worked_at=worked_at,
        client_token=client_token, photo=photo,
    )


@router.get("")
def list_records(
    segment_id: int | None = None,
    dispatch_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    stmt = select(models.WorkRecord).order_by(models.WorkRecord.id.desc())
    if segment_id is not None:
        stmt = stmt.where(models.WorkRecord.segment_id == segment_id)
    if dispatch_id is not None:
        stmt = stmt.where(models.WorkRecord.dispatch_id == dispatch_id)
    rows = db.scalars(stmt.limit(200)).all()
    return [record_out(r) for r in rows]
