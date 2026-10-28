import imghdr
import json
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.ml import classifier
from app.models import InspectionBatch, InspectionImage, Prediction
from app.storage import storage

router = APIRouter(prefix="/api/v1", tags=["inspections"])
CLASS_NAMES = {"apple_healthy": "사과 정상", "apple_fire_blight": "사과 과수화상병 의심"}
MIME_TYPES = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def result(image: InspectionImage) -> dict:
    prediction = image.prediction
    return {"image_id": image.id, "batch_id": image.batch_id, "filename": image.original_filename, "status": image.status, "error_message": image.error_message, "image_url": f"/api/v1/images/{image.id}", "class_code": prediction.class_code if prediction else None, "class_name_ko": CLASS_NAMES.get(prediction.class_code) if prediction else None, "confidence": prediction.confidence if prediction else None, "model_version": prediction.model_version if prediction else None, "detection_count": prediction.detection_count if prediction else 0, "detections": json.loads(prediction.boxes_json) if prediction and prediction.boxes_json else [], "created_at": image.created_at.isoformat()}


@router.post("/inspections", status_code=201)
async def create_inspection(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    if not files or len(files) > settings.max_upload_files:
        raise HTTPException(422, f"이미지는 1~{settings.max_upload_files}장만 업로드할 수 있습니다.")
    batch = InspectionBatch(status="processing", total_count=len(files)); db.add(batch); db.flush()
    for upload in files:
        data = await upload.read(); detected = imghdr.what(None, data)
        if detected not in MIME_TYPES or len(data) > settings.max_upload_size:
            image = InspectionImage(batch_id=batch.id, original_filename=upload.filename or "unknown", content_type=upload.content_type or "", file_size=len(data), object_key="invalid", status="failed", error_message="JPG, PNG, WEBP 파일만 허용하며 파일당 크기 제한을 확인하세요.")
            batch.failed_count += 1; db.add(image); continue
        suffix = ".jpg" if detected == "jpeg" else f".{detected}"; key = storage.new_key(suffix)
        image = InspectionImage(batch_id=batch.id, original_filename=Path(upload.filename or "image").name, content_type=MIME_TYPES[detected], file_size=len(data), object_key=key, status="processing")
        db.add(image); db.flush()
        try:
            saved = storage.save(key, data, MIME_TYPES[detected])
            if not classifier.status.ready: raise RuntimeError(classifier.status.detail)
            if saved: code, confidence, detections = classifier.predict(str(saved))
            else:
                with NamedTemporaryFile(suffix=suffix) as temp:
                    temp.write(data); temp.flush(); code, confidence, detections = classifier.predict(temp.name)
            image.prediction = Prediction(class_code=code, confidence=confidence, model_version=settings.model_version, detection_count=len(detections), boxes_json=json.dumps(detections)); image.status = "completed"; batch.completed_count += 1
        except Exception as error:
            image.status = "failed"; image.error_message = f"분석 실패: {error}"; batch.failed_count += 1
    batch.status = "completed" if batch.completed_count else "failed"; db.commit(); db.refresh(batch)
    return {"inspection_id": batch.id, "status": batch.status, "results": [result(item) for item in batch.images]}


@router.get("/inspections")
def list_inspections(status: str | None = None, class_code: str | None = None, start: datetime | None = None, end: datetime | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    query = select(InspectionImage).options(joinedload(InspectionImage.prediction)).order_by(InspectionImage.created_at.desc())
    if status: query = query.where(InspectionImage.status == status)
    if class_code: query = query.join(Prediction).where(Prediction.class_code == class_code)
    if start: query = query.where(InspectionImage.created_at >= start)
    if end: query = query.where(InspectionImage.created_at <= end)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    images = db.scalars(query.offset((page - 1) * size).limit(size)).unique().all()
    return {"items": [result(image) for image in images], "page": page, "size": size, "total": total}


@router.get("/inspections/{batch_id}")
def get_inspection(batch_id: int, db: Session = Depends(get_db)):
    batch = db.scalar(select(InspectionBatch).options(joinedload(InspectionBatch.images).joinedload(InspectionImage.prediction)).where(InspectionBatch.id == batch_id))
    if not batch: raise HTTPException(404, "검사 기록을 찾을 수 없습니다.")
    return {"inspection_id": batch.id, "status": batch.status, "created_at": batch.created_at.isoformat(), "results": [result(image) for image in batch.images]}


@router.get("/images/{image_id}")
def get_image(image_id: int, db: Session = Depends(get_db)):
    image = db.get(InspectionImage, image_id)
    if not image or image.object_key == "invalid": raise HTTPException(404, "이미지를 찾을 수 없습니다.")
    return Response(storage.read(image.object_key), media_type=image.content_type)
