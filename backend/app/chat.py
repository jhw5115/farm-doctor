"""Chatbot foundation endpoints.

LLM and RAG calls are deliberately not made until a server-side API key and
official knowledge documents have been configured.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import ChatMessage, ChatSession, InspectionImage, Prediction

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class LocalChatRequest(BaseModel):
    client_token: str = Field(min_length=8, max_length=128)
    message: str = Field(min_length=1, max_length=1000)


def _local_guidance(message: str, db: Session) -> str:
    text = message.lower()
    if any(word in text for word in ("최근", "검사", "결과", "통계")):
        total = db.scalar(select(func.count()).select_from(InspectionImage)) or 0
        healthy = db.scalar(select(func.count()).select_from(Prediction).where(Prediction.class_code == "apple_healthy")) or 0
        suspicious = db.scalar(select(func.count()).select_from(Prediction).where(Prediction.class_code == "apple_fire_blight")) or 0
        failed = db.scalar(select(func.count()).select_from(InspectionImage).where(InspectionImage.status == "failed")) or 0
        return f"저장된 검사 기록 기준으로 전체 {total}건, 정상 판별 {healthy}건, 과수화상병 의심 {suspicious}건, 분석 오류 {failed}건입니다. 이는 AI 참고용 판별 집계이며 확진 결과가 아닙니다."
    if any(word in text for word in ("신뢰도", "confidence")):
        return "신뢰도는 모델이 해당 이미지에서 판별한 결과에 대한 내부 점수입니다. 과수화상병 확진 확률이나 심각도를 의미하지 않으며, 의심 증상은 전문 기관의 현장 확인이 필요합니다."
    if any(word in text for word in ("업로드", "검사", "사용", "pdf", "보고서")):
        return "사진 분석 화면에서 JPG, JPEG, PNG 또는 WEBP 이미지를 선택해 검사를 시작할 수 있습니다. 검사 결과는 갤러리에서 확인하고, 리포트 메뉴에서 기간과 결과 조건을 선택해 PDF로 출력할 수 있습니다."
    return "현재는 외부 AI 챗봇을 연결하지 않은 안내 모드입니다. 서비스 사용법, 검사 결과 요약, AI 신뢰도 의미를 안내할 수 있습니다. 의심 증상은 관할 농업기술센터 등 전문 기관에 문의하세요."


@router.get("/status")
def chat_status() -> dict:
    return {
        "available": bool(settings.openai_api_key and settings.chat_model),
        "mode": "ready" if settings.openai_api_key and settings.chat_model else "waiting_for_configuration",
        "message": "챗봇 API 키와 모델 설정을 기다리는 중입니다.",
        "inspection_lookup_enabled": False,
        "rag_enabled": bool(settings.openai_vector_store_id),
    }


@router.post("/messages")
def local_message(payload: LocalChatRequest, db: Session = Depends(get_db)) -> dict:
    if settings.openai_api_key and settings.chat_model:
        raise HTTPException(409, "외부 LLM 연결 전환 시 별도 메시지 처리 경로를 사용합니다.")
    session = db.scalar(select(ChatSession).where(ChatSession.client_token == payload.client_token))
    if not session:
        session = ChatSession(client_token=payload.client_token)
        db.add(session)
        db.flush()
    question = payload.message.strip()
    answer = _local_guidance(question, db)
    db.add_all([ChatMessage(session_id=session.id, role="user", content=question), ChatMessage(session_id=session.id, role="assistant", content=answer)])
    session.updated_at = datetime.utcnow()
    db.commit()
    return {"mode": "local_guidance", "answer": answer, "sources": [], "inspection_lookup": "aggregate_only"}
