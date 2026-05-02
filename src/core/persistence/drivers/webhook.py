"""
Driver de persistência unidirecional via HTTP.
Despacha cada operação de escrita como POST para WEBHOOK_URL do .env.
Operações de leitura (load_*, list_*) lançam NotImplementedError.
"""

import requests
from src.infrastructure.config import settings
from src.core.persistence.base import PersistenceDriver
from src.core.schemas import (
    AgentRecord,
    AgentContextRecord,
    UserContextRecord,
    SessionRecord,
    InsightRecord,
    ScoreData,
)
from src.core.security import sanitize_pii


class WebhookDriver(PersistenceDriver):

    def _post(self, payload: dict) -> None:
        requests.post(settings.WEBHOOK_URL, json=payload, timeout=10)

    # ── Agent ──────────────────────────────────────────────────────────────────

    def save_agent(self, agent: AgentRecord) -> None:
        sanitized = agent.model_copy(update={"name": sanitize_pii(agent.name)})
        self._post({"type": "agent", "action": "save", "data": sanitized.model_dump()})

    def load_agent(self, agent_id: str) -> AgentRecord | None:
        raise NotImplementedError("WebhookDriver não suporta leitura.")

    def delete_agent(self, agent_id: str) -> None:
        self._post({"type": "agent", "action": "delete", "agent_id": agent_id})

    # ── Agent context ──────────────────────────────────────────────────────────

    def save_context(self, record: AgentContextRecord) -> None:
        self._post({"type": "agent_context", "action": "save", "data": record.model_dump()})

    def load_context(self, agent_id: str) -> AgentContextRecord | None:
        raise NotImplementedError("WebhookDriver não suporta leitura.")

    def load_context_history(self, agent_id: str) -> list[AgentContextRecord]:
        raise NotImplementedError("WebhookDriver não suporta leitura.")

    # ── User context ───────────────────────────────────────────────────────────

    def save_user_context(self, record: UserContextRecord) -> None:
        self._post({"type": "user_context", "action": "save", "data": record.model_dump()})

    def load_user_context(self, agent_id: str, user_id: str) -> UserContextRecord | None:
        raise NotImplementedError("WebhookDriver não suporta leitura.")

    def list_user_contexts(self, agent_id: str) -> list[UserContextRecord]:
        raise NotImplementedError("WebhookDriver não suporta leitura.")

    def delete_user_context(self, agent_id: str, user_id: str) -> None:
        self._post({"type": "user_context", "action": "delete", "agent_id": agent_id, "user_id": user_id})

    # ── Session ────────────────────────────────────────────────────────────────

    def save_session(self, session: SessionRecord) -> None:
        self._post({"type": "session", "action": "save", "data": session.model_dump()})

    def load_session(self, agent_id: str, session_id: str) -> SessionRecord | None:
        raise NotImplementedError("WebhookDriver não suporta leitura.")

    def list_sessions(self, agent_id: str) -> list[SessionRecord]:
        raise NotImplementedError("WebhookDriver não suporta leitura.")

    def delete_session(self, agent_id: str, session_id: str) -> None:
        self._post({"type": "session", "action": "delete", "agent_id": agent_id, "session_id": session_id})

    # ── Scores ─────────────────────────────────────────────────────────────────

    def save_scores(self, agent_id: str, scores: ScoreData) -> None:
        self._post({"type": "scores", "action": "save", "agent_id": agent_id, "data": scores.model_dump()})

    def load_scores(self, agent_id: str, session_id: str) -> ScoreData | None:
        raise NotImplementedError("WebhookDriver não suporta leitura.")

    # ── Insights ───────────────────────────────────────────────────────────────

    def save_insight(self, agent_id: str, insight: InsightRecord) -> None:
        self._post({"type": "insight", "action": "save", "agent_id": agent_id, "data": insight.model_dump()})

    def load_insight(self, agent_id: str, session_id: str) -> InsightRecord | None:
        raise NotImplementedError("WebhookDriver não suporta leitura.")
