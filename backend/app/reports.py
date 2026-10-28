from io import BytesIO
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.inspections import result
from app.models import InspectionBatch, InspectionImage, Prediction
from app.storage import storage

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
KOREAN_FONT = "HYSMyeongJo-Medium"
pdfmetrics.registerFont(UnicodeCIDFont(KOREAN_FONT))


def _filtered_images(
    db: Session,
    start: datetime | None,
    end: datetime | None,
    result_filter: str = "all",
    body_part: str = "all",
):
    if body_part != "all":
        raise HTTPException(422, "대상 부위는 기존 검사 데이터에 기록되지 않아 필터링할 수 없습니다.")
    if result_filter not in {"all", "healthy", "blight", "failed"}:
        raise HTTPException(422, "지원하지 않는 검사 결과 필터입니다.")
    query = select(InspectionImage).options(joinedload(InspectionImage.prediction)).order_by(InspectionImage.created_at.desc())
    if start:
        query = query.where(InspectionImage.created_at >= start)
    if end:
        query = query.where(InspectionImage.created_at <= end)
    images = db.scalars(query).unique().all()
    if result_filter == "healthy":
        return [image for image in images if image.prediction and image.prediction.class_code == "apple_healthy"]
    if result_filter == "blight":
        return [image for image in images if image.prediction and image.prediction.class_code == "apple_fire_blight"]
    if result_filter == "failed":
        return [image for image in images if image.status in {"failed", "processing"}]
    return images


def _summary_payload(images: list[InspectionImage], start: datetime | None, end: datetime | None) -> dict:
    summary = {"total": len(images), "apple_healthy": 0, "apple_fire_blight": 0, "failed": 0, "processing": 0}
    for image in images:
        if image.status == "failed":
            summary["failed"] += 1
        elif image.status == "processing":
            summary["processing"] += 1
        elif image.prediction and image.prediction.class_code in summary:
            summary[image.prediction.class_code] += 1
    if start:
        first_day = start.date()
    elif images:
        first_day = min(image.created_at.date() for image in images)
    else:
        first_day = datetime.utcnow().date()
    last_day = end.date() if end else datetime.utcnow().date()
    if last_day < first_day:
        first_day, last_day = last_day, first_day
    span = min((last_day - first_day).days, 90)
    daily: dict[str, dict[str, int | str]] = {}
    for offset in range(span + 1):
        date = (first_day + timedelta(days=offset)).isoformat()
        daily[date] = {"date": date, "total": 0, "healthy": 0, "blight": 0, "failed": 0}
    for image in images:
        record = daily.get(image.created_at.date().isoformat())
        if not record:
            continue
        record["total"] += 1
        if image.status == "failed":
            record["failed"] += 1
        elif image.prediction and image.prediction.class_code == "apple_healthy":
            record["healthy"] += 1
        elif image.prediction and image.prediction.class_code == "apple_fire_blight":
            record["blight"] += 1
    suspicious = [image for image in images if image.prediction and image.prediction.class_code == "apple_fire_blight"][:8]
    return {"period": {"start": start.isoformat() if start else None, "end": end.isoformat() if end else None}, "generated_at": datetime.utcnow().isoformat(), "summary": summary, "daily": list(daily.values()), "suspicious_cases": [result(image) for image in suspicious], "history": [result(image) for image in images[:100]], "body_part_available": False}


@router.get("/summary")
def report_summary(
    start: datetime | None = None,
    end: datetime | None = None,
    result_filter: str = "all",
    body_part: str = "all",
    db: Session = Depends(get_db),
) -> dict:
    if start and end and start > end:
        raise HTTPException(422, "시작일은 종료일보다 늦을 수 없습니다.")
    return _summary_payload(_filtered_images(db, start, end, result_filter, body_part), start, end)


def _draw_image(pdf: canvas.Canvas, image: InspectionImage, y: float) -> None:
    try:
        image_reader = ImageReader(BytesIO(storage.read(image.object_key)))
        pdf.drawImage(image_reader, 40, y - 130, width=180, height=120, preserveAspectRatio=True, anchor="sw")
    except Exception:
        pdf.drawString(40, y - 14, "이미지 미리보기를 불러오지 못했습니다.")


def _draw_footer(pdf: canvas.Canvas, width: float) -> None:
    pdf.setFont(KOREAN_FONT, 8)
    pdf.drawRightString(width - 40, 24, f"Farm Doctor · {pdf.getPageNumber()} 페이지")


def _next_page(pdf: canvas.Canvas, width: float, height: float) -> float:
    _draw_footer(pdf, width)
    pdf.showPage()
    pdf.setFont(KOREAN_FONT, 10)
    return height - 48


@router.get("/period.pdf")
def period_report(
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    result_filter: str = "all",
    body_part: str = "all",
    report_type: str = "summary",
    include_images: bool = True,
    suspicious_only: bool = False,
    db: Session = Depends(get_db),
):
    if start and end and start > end:
        raise HTTPException(422, "시작일은 종료일보다 늦을 수 없습니다.")
    if report_type not in {"summary", "detail"}:
        raise HTTPException(422, "보고서 유형은 summary 또는 detail이어야 합니다.")
    images = _filtered_images(db, start, end, result_filter, body_part)
    payload = _summary_payload(images, start, end)
    output = BytesIO(); pdf = canvas.Canvas(output, pagesize=A4); width, height = A4; y = height - 48
    pdf.setTitle("farm-doctor-period-report"); pdf.setFont(KOREAN_FONT, 17); pdf.drawString(40, y, "사과 과수화상병 AI 검사 보고서"); y -= 30
    pdf.setFont(KOREAN_FONT, 10)
    pdf.drawString(40, y, f"조회 기간: {start.date().isoformat() if start else '전체'} ~ {end.date().isoformat() if end else '현재'}"); y -= 18
    pdf.drawString(40, y, f"보고서 유형: {'상세' if report_type == 'detail' else '요약'} / 결과 필터: {result_filter} / 생성일: {datetime.utcnow().date().isoformat()}"); y -= 30
    s = payload["summary"]; pdf.setFont(KOREAN_FONT, 13); pdf.drawString(40, y, "검사 현황 요약"); y -= 20
    pdf.setFont(KOREAN_FONT, 10); pdf.drawString(40, y, f"전체 검사 {s['total']}건"); y -= 16
    pdf.drawString(40, y, f"정상 판별 {s['apple_healthy']}건 · 과수화상병 의심 {s['apple_fire_blight']}건"); y -= 16
    pdf.drawString(40, y, f"분석 오류·미완료 {s['failed'] + s['processing']}건"); y -= 18
    pdf.drawString(40, y, "검사 건수와 검출 객체 수는 다른 지표이며, 이 보고서는 검사 이미지 건수를 집계합니다.")

    y = _next_page(pdf, width, height)
    pdf.setFont(KOREAN_FONT, 13); pdf.drawString(40, y, "기간별 검사 추이 및 대상 부위 정보"); y -= 24
    pdf.setFont(KOREAN_FONT, 10)
    for day in payload["daily"]:
        if y < 72:
            y = _next_page(pdf, width, height)
        pdf.drawString(40, y, f"{day['date']}  전체 {day['total']} / 정상 {day['healthy']} / 의심 {day['blight']} / 실패 {day['failed']}"); y -= 15
    y -= 8
    pdf.drawString(40, y, "대상 부위(잎·열매·줄기·가지)는 현재 기존 검사 데이터에 저장되지 않아 부위별 통계를 제공하지 않습니다.")
    suspicious = [image for image in images if image.prediction and image.prediction.class_code == "apple_fire_blight"][:8]
    y -= 24; pdf.setFont(KOREAN_FONT, 13); pdf.drawString(40, y, "주요 과수화상병 의심 사례"); y -= 18
    pdf.setFont(KOREAN_FONT, 10)
    if suspicious:
        for image in suspicious:
            if y < 90:
                y = _next_page(pdf, width, height)
            pdf.drawString(40, y, f"{image.original_filename} / {image.prediction.confidence:.1%} / 검출 {image.prediction.detection_count}건"); y -= 15
    else:
        pdf.drawString(40, y, "조회 조건에 해당하는 과수화상병 의심 사례가 없습니다.")

    if report_type == "detail":
        details = [image for image in images if not suspicious_only or (image.prediction and image.prediction.class_code == "apple_fire_blight")]
        for image in details:
            y = _next_page(pdf, width, height)
            pdf.setFont(KOREAN_FONT, 13); pdf.drawString(40, y, "개별 검사 기록"); y -= 22
            pdf.setFont(KOREAN_FONT, 10)
            class_text = image.prediction.class_code if image.prediction else "분석 오류·미완료"
            confidence = f"{image.prediction.confidence:.1%}" if image.prediction else "-"
            pdf.drawString(40, y, f"파일: {image.original_filename}"); y -= 15
            pdf.drawString(40, y, f"검사일: {image.created_at.isoformat(sep=' ', timespec='minutes')} / 결과: {class_text} / 신뢰도: {confidence}"); y -= 15
            pdf.drawString(40, y, "대상 부위: 미기록"); y -= 15
            if image.prediction:
                pdf.drawString(40, y, f"검출 객체 수: {image.prediction.detection_count} / 모델: {image.prediction.model_version}")
            elif image.error_message:
                pdf.drawString(40, y, f"오류: {image.error_message[:80]}")
            y -= 18
            if include_images:
                _draw_image(pdf, image, y)

    y = _next_page(pdf, width, height)
    pdf.setFont(KOREAN_FONT, 11); pdf.drawString(40, y, "안내 및 한계"); y -= 20
    pdf.setFont(KOREAN_FONT, 10); pdf.drawString(40, y, "AI 판별 결과는 참고용 정보이며, 과수화상병 확진이나 심각도 평가를 의미하지 않습니다."); y -= 17
    pdf.drawString(40, y, "의심 증상이 있는 경우 관할 농업기술센터 등 전문 기관에 문의하고 공식 지침에 따라 대응하세요.")
    _draw_footer(pdf, width)
    pdf.save(); output.seek(0)
    return StreamingResponse(output, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="period-inspection-report.pdf"'})

@router.get("/{batch_id}.pdf")
def report(batch_id: int, db: Session = Depends(get_db)):
    batch = db.scalar(select(InspectionBatch).options(joinedload(InspectionBatch.images).joinedload(InspectionImage.prediction)).where(InspectionBatch.id == batch_id))
    if not batch: raise HTTPException(404, "검사 기록을 찾을 수 없습니다.")
    output = BytesIO(); pdf = canvas.Canvas(output, pagesize=A4); _, height = A4; y = height - 48
    pdf.setTitle(f"inspection-{batch_id}"); pdf.setFont(KOREAN_FONT, 16); pdf.drawString(40, y, f"사과 과수화상병 AI 검사 보고서 #{batch_id}"); y -= 30
    pdf.setFont(KOREAN_FONT, 9); pdf.drawString(40, y, "AI 참고용 결과이며 확진이 아닙니다. 의심 증상은 관할 농업기술센터에 문의하세요."); y -= 28
    for image in batch.images:
        if y < 205: pdf.showPage(); y = height - 48; pdf.setFont(KOREAN_FONT, 10)
        text = f"{image.original_filename}: {image.prediction.class_code} / {image.prediction.confidence:.1%} / detections={image.prediction.detection_count} / {image.prediction.model_version}" if image.prediction else f"{image.original_filename}: FAILED - {image.error_message or 'unknown error'}"
        pdf.drawString(40, y, text[:140]); y -= 16
        try:
            image_reader = ImageReader(BytesIO(storage.read(image.object_key)))
            pdf.drawImage(image_reader, 40, y - 130, width=180, height=120, preserveAspectRatio=True, anchor="sw")
        except Exception:
            pdf.drawString(40, y - 14, "이미지 미리보기를 불러오지 못했습니다.")
        y -= 140
    pdf.save(); output.seek(0)
    return StreamingResponse(output, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="inspection-{batch_id}.pdf"'})
