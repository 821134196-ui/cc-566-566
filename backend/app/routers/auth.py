"""登录与当前用户。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..schemas import LoginIn
from ..security import current_user, issue_token
from ..serializers import user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.username == body.username))
    if not user or user.password != body.password:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {"token": issue_token(user.id), "user": user_out(user)}


@router.get("/me")
def me(user: models.User = Depends(current_user)):
    return user_out(user)
