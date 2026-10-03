"""现场照片本地回传访问（仅登录用户）。"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models
from ..config import DATA_DIR
from ..database import get_db
from ..security import current_user

router = APIRouter(prefix="/api/photos", tags=["photo"])


@router.get("/{record_id}")
def get_photo(
    record_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    r = db.get(models.WorkRecord, record_id)
    if not r or not r.photo_path:
        raise HTTPException(status_code=404, detail="照片不存在")
    # 规范化后限制在 DATA_DIR 内，防止路径穿越
    target = (DATA_DIR / r.photo_path).resolve()
    if DATA_DIR.resolve() not in target.parents and target.parent != DATA_DIR.resolve():
        raise HTTPException(status_code=400, detail="非法路径")
    if not target.exists():
        raise HTTPException(status_code=404, detail="照片文件丢失")
    suffix = Path(target.name).suffix.lower().lstrip(".")
    media = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
             "webp": "webp", "gif": "gif"}.get(suffix, "octet-stream")
    return FileResponse(target, media_type=f"image/{media}")
