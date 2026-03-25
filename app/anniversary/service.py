"""
纪念日服务层
"""
import time
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.anniversary import Anniversary
from app.models.diary import Diary
from app.response import ApiException, NOT_FOUND


def _now_ms() -> int:
    return int(time.time() * 1000)


def ann_to_dict(a: Anniversary) -> dict:
    return {
        "id": a.id,
        "user_id": a.user_id,
        "title": a.title,
        "date": a.date,
        "year": a.year,
        "source": a.source or "manual",
        "related_person": a.related_person or "",
        "diary_id": a.diary_id,
        "created_at": a.created_at,
    }


def list_anniversaries(db: Session, user_id: str) -> List[dict]:
    """获取所有纪念日"""
    items = (
        db.query(Anniversary)
        .filter(Anniversary.user_id == user_id)
        .order_by(Anniversary.date)
        .all()
    )
    return [ann_to_dict(a) for a in items]


def create_anniversary(db: Session, user_id: str, data: dict) -> dict:
    """手动创建纪念日"""
    ann = Anniversary(
        user_id=user_id,
        title=data["title"],
        date=data["date"],
        year=data.get("year"),
        source="manual",
        related_person=data.get("related_person", ""),
        created_at=_now_ms(),
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    return ann_to_dict(ann)


def update_anniversary(db: Session, user_id: str, ann_id: str, data: dict) -> dict:
    """更新纪念日"""
    a = db.query(Anniversary).filter(
        Anniversary.id == ann_id, Anniversary.user_id == user_id
    ).first()
    if not a:
        raise ApiException(code=NOT_FOUND, message="纪念日不存在", status_code=404)

    if "title" in data and data["title"] is not None:
        a.title = data["title"]
    if "date" in data and data["date"] is not None:
        a.date = data["date"]
    if "year" in data:
        a.year = data["year"]
    if "related_person" in data and data["related_person"] is not None:
        a.related_person = data["related_person"]

    db.commit()
    db.refresh(a)
    return ann_to_dict(a)


def delete_anniversary(db: Session, user_id: str, ann_id: str) -> None:
    """删除纪念日"""
    a = db.query(Anniversary).filter(
        Anniversary.id == ann_id, Anniversary.user_id == user_id
    ).first()
    if not a:
        raise ApiException(code=NOT_FOUND, message="纪念日不存在", status_code=404)
    db.delete(a)
    db.commit()


def get_today_anniversaries(db: Session, user_id: str, today: str) -> dict:
    """
    查询今日纪念日 + 那年今日的日记
    today 格式: "2026-03-25" -> 月日部分 "03-25"
    """
    month_day = today[5:]  # "03-25"

    # 今日纪念日
    anniversaries = (
        db.query(Anniversary)
        .filter(Anniversary.user_id == user_id, Anniversary.date == month_day)
        .all()
    )

    # 那年今日：查日记中 date 字段以 month_day 结尾（但不是今年）
    past_diaries = (
        db.query(Diary)
        .filter(
            Diary.user_id == user_id,
            Diary.date.like(f"%-{month_day}"),
            Diary.date != today,
        )
        .order_by(Diary.date.desc())
        .limit(5)
        .all()
    )

    return {
        "today": [ann_to_dict(a) for a in anniversaries],
        "on_this_day": [
            {"id": d.id, "date": d.date, "title": d.title or "日记", "content_preview": (d.content or "")[:100]}
            for d in past_diaries
        ],
    }
