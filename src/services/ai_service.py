"""
Orquestra chamadas ao modelo de IA no ciclo do POST /chat.
Carrega contexto do cache via ContextService, mantém histórico no Redis,
chama AIClient e avalia condições de escalonamento do AgentContext.
"""
import uuid
import time
from datetime import datetime, timezone

from src.clients.ai_client import AIClient
from src.core.cache.client import CacheClient
from src.core.persistence.factory import get_driver
from src.core.schemas import HistoryMessage, SessionMeta, SessionRecord
from src.infrastructure.config import settings
from src.services.context_service import ContextService
from src.services import quality_analyzer


class AIService:

    def __init__(self):
        self.ai_client = AIClient()
        self.cache = CacheClient()
        self.context_service = ContextService()

    def process_message(
        self,
        agent_id: str,
        session_id: str,
        user_id: str | None,
        message: str,
    ) -> dict:
        system_prompt = self.context_service.load_system_prompt(agent_id) or ""
        history = self.cache.get_history(session_id)

        now = datetime.now(timezone.utc).isoformat()
        user_msg_id = str(uuid.uuid4())
        user_msg = HistoryMessage(
            message_id=user_msg_id,
            session_id=session_id,
            role="user",
            content=message,
            timestamp=now,
            status="delivered",
        )
        self.cache.append_message(session_id, user_msg)

        threshold = self._sentiment_threshold(agent_id)
        user_score = quality_analyzer.analyze(user_msg_id, "user", message, threshold)

        t0 = time.monotonic()
        ai_response = self.ai_client.complete(system=system_prompt, messages=history + [user_msg])
        response_time_ms = int((time.monotonic() - t0) * 1000)

        reply_now = datetime.now(timezone.utc).isoformat()
        assistant_msg_id = str(uuid.uuid4())
        assistant_msg = HistoryMessage(
            message_id=assistant_msg_id,
            session_id=session_id,
            role="assistant",
            content=ai_response.content,
            timestamp=reply_now,
            status="delivered",
            tokens=ai_response.usage.output_tokens,
            response_time_ms=response_time_ms,
        )
        self.cache.append_message(session_id, assistant_msg)

        assistant_score = quality_analyzer.analyze(
            assistant_msg_id, "assistant", ai_response.content, threshold
        )
        existing_scores = self.cache.get_scores(session_id)
        scores = quality_analyzer.update_session_scores(
            session_id, existing_scores, user_score, now, threshold
        )
        scores = quality_analyzer.update_session_scores(
            session_id, scores, assistant_score, reply_now, threshold
        )
        self.cache.set_scores(session_id, scores)

        meta = self.cache.get_session_meta(session_id)
        if meta is None:
            meta = SessionMeta(
                session_id=session_id,
                agent_id=agent_id,
                user_id=user_id,
                model=settings.AI_MODEL,
                started_at=now,
            )
        meta = meta.model_copy(update={
            "total_messages": meta.total_messages + 2,
            "input_tokens": meta.input_tokens + ai_response.usage.input_tokens,
            "output_tokens": meta.output_tokens + ai_response.usage.output_tokens,
            "total_tokens": meta.total_tokens + ai_response.usage.total_tokens,
        })
        self.cache.set_session_meta(session_id, meta)
        self._persist_snapshot(agent_id, session_id, meta, scores)

        return {
            "message_id": assistant_msg_id,
            "content": ai_response.content,
            "usage": ai_response.usage.model_dump(),
            "response_time_ms": response_time_ms,
        }

    def evaluate_escalation(self, agent_id: str, session_id: str) -> bool:
        record = self.context_service.load_context(agent_id)
        if not record or not record.context.escalation_trigger:
            return False

        trigger = record.context.escalation_trigger
        history = self.cache.get_history(session_id)
        scores = self.cache.get_scores(session_id)
        meta = self.cache.get_session_meta(session_id)

        results = [
            self._eval_condition(cond, history, scores, meta)
            for cond in trigger.conditions
        ]

        if trigger.operator == "OR":
            return any(results)
        return all(results)

    def get_fallback_message(self, agent_id: str) -> str | None:
        record = self.context_service.load_context(agent_id)
        if not record:
            return None
        return record.context.fallback_message

    # ── Incremental persistence ────────────────────────────────────────────────

    def _persist_snapshot(self, agent_id: str, session_id: str, meta: SessionMeta, scores) -> None:
        driver = get_driver()
        driver.save_session(SessionRecord(
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
        ))
        if scores:
            driver.save_scores(agent_id, scores)
        history = self.cache.get_history(session_id)
        if history:
            driver.save_history(agent_id, session_id, history)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _sentiment_threshold(self, agent_id: str) -> float:
        record = self.context_service.load_context(agent_id)
        if not record or not record.context.escalation_trigger:
            return 0.3
        for cond in record.context.escalation_trigger.conditions:
            if cond.type == "sentiment" and cond.threshold is not None:
                return cond.threshold
        return 0.3

    def _eval_condition(
        self,
        cond,
        history: list[HistoryMessage],
        scores,
        meta: SessionMeta | None,
    ) -> bool:
        user_messages = [m for m in history if m.role == "user"]

        if cond.type == "keyword":
            keywords = cond.values or ([cond.value] if cond.value else [])
            if not user_messages or not keywords:
                return False
            last = user_messages[-1].content.lower()
            return any(str(kw).lower() in last for kw in keywords)

        if cond.type == "sentiment":
            if not scores or scores.avg_sentiment_score is None:
                return False
            threshold = cond.threshold if cond.threshold is not None else 0.3
            return scores.avg_sentiment_score < -threshold

        if cond.type == "message_count":
            return len(user_messages) >= int(cond.value or 0)

        if cond.type == "topic":
            topics = cond.values or ([cond.value] if cond.value else [])
            if not scores or not topics:
                return False
            return any(t in (scores.all_topics or []) for t in topics)

        if cond.type == "time_elapsed":
            if not meta or cond.value is None:
                return False
            started = datetime.fromisoformat(meta.started_at)
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            return elapsed >= float(cond.value)

        if cond.type == "intent":
            if not scores or not cond.value:
                return False
            return scores.intent == cond.value

        return False
