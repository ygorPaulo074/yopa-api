"""
Endpoints de chat:
  POST /chat                        — envia mensagem para a IA, injeta context.xml do agente via ai_service,
                                      avalia condições de escalonamento, executa quality_analyzer pós-resposta
                                      e retorna resposta estruturada com metadados de sessão e tokens.

Ciclo de vida da sessão:
  POST /chat/{session_id}/end       — encerra a sessão, grava ended_at e persiste no driver
  POST /chat/{session_id}/resolve   — marca a sessão como resolvida (resolved=true)
  POST /chat/{session_id}/escalate  — marca a sessão como escalonada (escalated=true)
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.core.auth import authenticate_agent
from src.core.cache.client import CacheClient
from src.core.persistence.factory import get_driver
from src.core.schemas import SessionRecord, UserContextRecord
from src.infrastructure.config import LIMITER, settings
from src.services.ai_service import AIService
from src.services.context_service import ContextService
from src.services.escalation_service import dispatch_escalation
from src.services import quality_analyzer
from .schemas import (
    ChatRequest, ChatResponse, SessionInfo, TokenUsage, Message, ConversationEntry,
    SessionEndResponse, SessionResolveResponse, SessionEscalateResponse,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def _meta_to_session_record(meta, agent_id: str) -> SessionRecord:
    return SessionRecord(
        session_id=meta.session_id,
        agent_id=agent_id,
        user_id=meta.user_id,
        model=meta.model,
        started_at=meta.started_at,
        ended_at=meta.ended_at,
        total_messages=meta.total_messages,
        input_tokens=meta.input_tokens,
        output_tokens=meta.output_tokens,
        total_tokens=meta.total_tokens,
        resolved=meta.resolved,
        escalated=meta.escalated,
    )


@router.post("", response_model=ChatResponse)
@LIMITER.limit(settings.RATE_LIMIT_CHAT)
def send_message(request: Request, body: ChatRequest, agent_id: str = Depends(authenticate_agent)):
    ai = AIService()
    result = ai.process_message(agent_id, body.session_id, body.user_id, body.message)

    escalated = ai.evaluate_escalation(agent_id, body.session_id)
    if escalated:
        cache = CacheClient()
        meta = cache.get_session_meta(body.session_id)
        history = cache.get_history(body.session_id)
        if meta and not meta.escalated:
            meta = meta.model_copy(update={"escalated": True})
            cache.set_session_meta(body.session_id, meta)
            context_record = ContextService().load_context(agent_id)
            if context_record:
                dispatch_escalation(agent_id, body.session_id, "automatic",
                                    context_record.context, meta, history)

    cache = CacheClient()
    meta = cache.get_session_meta(body.session_id)
    history = cache.get_history(body.session_id)

    last_two = history[-2:] if len(history) >= 2 else history
    conversation = [
        ConversationEntry(message=Message(
            id=m.message_id,
            role=m.role,
            content=m.content,
            timestamp=m.timestamp,
            status=m.status,
            tokens=m.tokens,
            response_time_ms=m.response_time_ms,
        ))
        for m in last_two
    ]

    return ChatResponse(
        session=SessionInfo(
            session_id=body.session_id,
            agent_id=agent_id,
            model=meta.model if meta else "unknown",
            started_at=meta.started_at if meta else datetime.now(timezone.utc).isoformat(),
            response_time_ms=result["response_time_ms"],
            tokens=TokenUsage(
                input=result["usage"]["input_tokens"],
                output=result["usage"]["output_tokens"],
                total=result["usage"]["total_tokens"],
            ),
        ),
        conversation=conversation,
    )


@router.post("/{session_id}/end", response_model=SessionEndResponse)
def end_session(session_id: str, agent_id: str = Depends(authenticate_agent)):
    cache = CacheClient()
    meta = cache.get_session_meta(session_id)
    if not meta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    now = datetime.now(timezone.utc).isoformat()
    meta = meta.model_copy(update={"ended_at": now})
    cache.set_session_meta(session_id, meta)

    driver = get_driver()
    driver.save_session(_meta_to_session_record(meta, agent_id))

    scores = cache.get_scores(session_id)
    if scores:
        driver.save_scores(agent_id, scores)

    history = cache.get_history(session_id)
    if history:
        driver.save_history(agent_id, session_id, history)

    if meta.user_id and history:
        _update_user_context(driver, agent_id, meta.user_id, history, now)

    return SessionEndResponse(session_id=session_id, ended_at=now)


def _update_user_context(driver, agent_id: str, user_id: str, history, now: str) -> None:
    lang = quality_analyzer.detect_dominant_language(history)
    context_record = ContextService().load_context(agent_id)
    segment = context_record.context.segment if context_record else None

    existing = driver.load_user_context(agent_id, user_id)
    if existing:
        driver.save_user_context(existing.model_copy(update={
            "language": lang or existing.language,
            "segment": segment or existing.segment,
            "updated_at": now,
        }))
    else:
        driver.save_user_context(UserContextRecord(
            user_id=user_id,
            agent_id=agent_id,
            language=lang,
            segment=segment,
            created_at=now,
            updated_at=now,
        ))


@router.post("/{session_id}/resolve", response_model=SessionResolveResponse)
def resolve_session(session_id: str, agent_id: str = Depends(authenticate_agent)):
    cache = CacheClient()
    meta = cache.get_session_meta(session_id)
    if not meta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    now = datetime.now(timezone.utc).isoformat()
    meta = meta.model_copy(update={"resolved": True})
    cache.set_session_meta(session_id, meta)

    driver = get_driver()
    driver.save_session(_meta_to_session_record(meta, agent_id))

    return SessionResolveResponse(session_id=session_id, resolved=True, updated_at=now)


@router.post("/{session_id}/escalate", response_model=SessionEscalateResponse)
def escalate_session(session_id: str, agent_id: str = Depends(authenticate_agent)):
    cache = CacheClient()
    meta = cache.get_session_meta(session_id)
    if not meta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    now = datetime.now(timezone.utc).isoformat()
    meta = meta.model_copy(update={"escalated": True})
    cache.set_session_meta(session_id, meta)

    driver = get_driver()
    driver.save_session(_meta_to_session_record(meta, agent_id))

    history = cache.get_history(session_id)
    context_record = ContextService().load_context(agent_id)
    if context_record:
        dispatch_escalation(agent_id, session_id, "manual",
                            context_record.context, meta, history)

    return SessionEscalateResponse(session_id=session_id, escalated=True, updated_at=now)
