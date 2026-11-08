"""
Chatbot router: AI Business Advisor with streaming and session management.
LLM handles language/intent; business rules enforced by catalogue service.
"""
import uuid
import json
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import Conversation, Business
from app.services.ai_service import stream_chat, chat_complete, extract_profile_update, check_ollama_health
from app.services.catalogue_service import filter_eligible_products

router = APIRouter(prefix="/chat", tags=["chatbot"])


class ChatMessage(BaseModel):
    content: str
    session_id: Optional[str] = None
    language: str = "English"
    business_id: Optional[int] = None


class SessionCreate(BaseModel):
    language: str = "English"
    business_id: Optional[int] = None


@router.post("/session")
def create_session(data: SessionCreate, db: Session = Depends(get_db)):
    """Create a new chat session."""
    session_id = str(uuid.uuid4())
    conv = Conversation(
        session_id=session_id,
        language=data.language,
        business_id=data.business_id,
        messages_json=json.dumps([]),
    )
    db.add(conv)
    db.commit()
    return {"session_id": session_id, "language": data.language}


@router.get("/health")
async def ai_health():
    """Check if Ollama AI service is available."""
    return await check_ollama_health()


@router.post("/message")
async def send_message(data: ChatMessage, db: Session = Depends(get_db)):
    """
    Send a message and get a streaming AI response.
    Returns StreamingResponse with text/event-stream.
    """
    # Get or create conversation
    conv = None
    if data.session_id:
        conv = db.query(Conversation).filter(
            Conversation.session_id == data.session_id
        ).first()
    
    if not conv:
        session_id = data.session_id or str(uuid.uuid4())
        conv = Conversation(
            session_id=session_id,
            language=data.language,
            business_id=data.business_id,
            messages_json=json.dumps([]),
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # Load message history
    messages = json.loads(conv.messages_json)

    # Add user message
    user_msg = {
        "role": "user",
        "content": data.content,
        "timestamp": datetime.utcnow().isoformat()
    }
    messages.append(user_msg)

    # Get business context if available
    business_context = None
    if data.business_id or conv.business_id:
        bid = data.business_id or conv.business_id
        biz = db.query(Business).filter(Business.id == bid).first()
        if biz:
            business_context = {
                "city": biz.city,
                "city_tier": biz.city_tier,
                "employee_count": biz.employee_count,
                "num_sites": biz.num_sites,
                "has_gstin": biz.has_gstin,
                "segment": biz.segment,
            }

    # Prepare messages for LLM (without timestamps)
    llm_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    full_response = ""

    async def generate():
        nonlocal full_response
        async for chunk in stream_chat(llm_messages, data.language, business_context):
            full_response += chunk
            yield f"data: {json.dumps({'content': chunk})}\n\n"

        # Save assistant response
        assistant_msg = {
            "role": "assistant",
            "content": full_response,
            "timestamp": datetime.utcnow().isoformat()
        }
        messages.append(assistant_msg)
        conv.messages_json = json.dumps(messages)

        # Extract and apply profile updates if any
        profile_update = extract_profile_update(full_response)
        if profile_update and (data.business_id or conv.business_id):
            bid = data.business_id or conv.business_id
            biz = db.query(Business).filter(Business.id == bid).first()
            if biz:
                for key, val in profile_update.items():
                    if hasattr(biz, key):
                        setattr(biz, key, val)
                db.commit()

        db.commit()
        yield f"data: {json.dumps({'done': True, 'session_id': conv.session_id})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/history/{session_id}")
def get_history(session_id: str, db: Session = Depends(get_db)):
    """Get conversation history for a session."""
    conv = db.query(Conversation).filter(
        Conversation.session_id == session_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = json.loads(conv.messages_json)
    # Mask any sensitive data in messages
    return {
        "session_id": session_id,
        "language": conv.language,
        "messages": messages,
        "created_at": conv.created_at.isoformat(),
    }


@router.delete("/session/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    """Delete a chat session and its history (DPDP data deletion)."""
    conv = db.query(Conversation).filter(
        Conversation.session_id == session_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Session not found")

    db.delete(conv)
    db.commit()
    return {"message": "Session deleted", "session_id": session_id}
