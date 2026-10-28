from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.database import get_db
from app.inspections import result
from app.models import InspectionBatch, InspectionImage, Prediction
from sqlalchemy.orm import joinedload

router = APIRouter(prefix="/api/v1", tags=["statistics"])

@router.get("/statistics")
def statistics(db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count()).select_from(InspectionImage)) or 0
    failed = db.scalar(select(func.count()).select_from(InspectionImage).where(InspectionImage.status == "failed")) or 0
    counts = dict(db.execute(select(Prediction.class_code, func.count()).group_by(Prediction.class_code)).all())
    return {"total": total, "apple_healthy": counts.get("apple_healthy", 0), "apple_fire_blight": counts.get("apple_fire_blight", 0), "failed": failed}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict:
    """대시보드용 실제 검사 요약. 외부 캐시 없이 DB 최신값을 반환한다."""
    summary = statistics(db)
    processing = db.scalar(select(func.count()).select_from(InspectionImage).where(InspectionImage.status == "processing")) or 0
    recent = db.scalars(
        select(InspectionImage)
        .options(joinedload(InspectionImage.prediction))
        .order_by(InspectionImage.created_at.desc())
        .limit(8)
    ).unique().all()
    cutoff = datetime.utcnow() - timedelta(days=6)
    daily_rows = db.execute(
        select(InspectionImage.created_at, InspectionImage.status, Prediction.class_code)
        .outerjoin(Prediction, Prediction.image_id == InspectionImage.id)
        .where(InspectionImage.created_at >= cutoff)
    ).all()
    days: dict[str, dict[str, int | str]] = {}
    for offset in range(6, -1, -1):
        day = (datetime.utcnow() - timedelta(days=offset)).date().isoformat()
        days[day] = {"date": day, "total": 0, "healthy": 0, "blight": 0, "failed": 0}
    for created_at, status, class_code in daily_rows:
        day = created_at.date().isoformat()
        if day not in days:
            continue
        days[day]["total"] += 1
        if status == "failed":
            days[day]["failed"] += 1
        elif class_code == "apple_healthy":
            days[day]["healthy"] += 1
        elif class_code == "apple_fire_blight":
            days[day]["blight"] += 1
    return {"summary": summary, "processing": processing, "recent": [result(image) for image in recent], "daily": list(days.values())}
