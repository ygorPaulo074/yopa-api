"""
Modelos internos de persistência e cache.
Usados por drivers, CacheClient e services — nunca expostos diretamente pela API.
Os schemas de rota (src/routes/*/schemas.py) são derivados destes ao montar respostas.
"""

from pydantic import BaseModel, HttpUrl
from typing import Any, Literal


# ── Agent context base (compartilhado entre core e routes) ────────────────────

class FileReference(BaseModel):
    name: str
    url: HttpUrl


class RestrictionsConfig(BaseModel):
    topics: list[str] = []
    files: list[FileReference] = []


class KnowledgeBaseConfig(BaseModel):
    urls: list[HttpUrl] = []
    files: list[FileReference] = []


class EscalationCondition(BaseModel):
    type: Literal["keyword", "sentiment", "message_count", "topic", "time_elapsed", "intent"]
    value: str | int | float | None = None
    values: list[str] | None = None
    threshold: float | None = None


class EscalationTrigger(BaseModel):
    operator: Literal["OR", "AND"]
    conditions: list[EscalationCondition]


class AgentContextBase(BaseModel):
    tone: Literal["formal", "informal", "neutro"] | None = None
    language: str | None = None
    segment: str | None = None
    persona: str | None = None
    behavior: str | None = None
    fallback_message: str | None = None
    restrictions: RestrictionsConfig | None = None
    knowledge_base: KnowledgeBaseConfig | None = None
    escalation_trigger: EscalationTrigger | None = None


# ── Cache: session history ────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    message_id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    status: Literal["delivered", "pending", "failed", "escalated"]
    tokens: int | None = None
    response_time_ms: int | None = None


# ── Cache: session metadata ───────────────────────────────────────────────────

class SessionMeta(BaseModel):
    session_id: str
    agent_id: str
    user_id: str | None = None
    model: str
    started_at: str
    ended_at: str | None = None
    total_messages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    resolved: bool = False
    escalated: bool = False


# ── Cache: NLP scores ─────────────────────────────────────────────────────────

class MessageScore(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    text_length: int | None = None
    sentiment_score: float | None = None
    sentiment_label: Literal["positive", "neutral", "negative"] | None = None
    topics: list[str] | None = None
    intent: str | None = None


class ScoreData(BaseModel):
    session_id: str
    messages: list[MessageScore] = []
    avg_sentiment_score: float | None = None
    sentiment_label: Literal["positive", "neutral", "negative"] | None = None
    all_topics: list[str] = []
    main_topic: str | None = None
    intent: str | None = None
    avg_user_message_length: float | None = None
    updated_at: str


# ── Persistence: agent ────────────────────────────────────────────────────────

class AgentRecord(BaseModel):
    agent_id: str
    name: str
    owner: str
    api_key_hash: str
    tags: list[str] = []
    created_at: str
    updated_at: str
    active_since: str | None = None
    last_activity_at: str | None = None


# ── Persistence: agent context (versioned) ────────────────────────────────────

class AgentContextRecord(BaseModel):
    agent_id: str
    version: int
    context: AgentContextBase
    changes: list[str] = []
    updated_at: str


# ── Persistence: user context ─────────────────────────────────────────────────

class UserContextRecord(BaseModel):
    user_id: str
    agent_id: str
    segment: str | None = None
    language: str | None = None
    form_answers: dict[str, Any] | None = None
    created_at: str
    updated_at: str


# ── Persistence: session (cold storage) ──────────────────────────────────────

class SessionRecord(BaseModel):
    session_id: str
    agent_id: str
    user_id: str | None = None
    model: str
    started_at: str
    ended_at: str | None = None
    total_messages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    resolved: bool = False
    escalated: bool = False


# ── Persistence: AI-generated insight ────────────────────────────────────────

class InsightRecord(BaseModel):
    session_id: str
    generated_at: str
    key_points: list[str] = []
    suggested_actions: list[str] = []
    summary: str


# ── Persistence: knowledge base file ─────────────────────────────────────────

class KnowledgeFileRecord(BaseModel):
    file_id: str
    agent_id: str
    filename: str
    file_type: Literal["csv", "json", "pdf", "excel"]
    records: list[dict[str, Any]] = []
    uploaded_at: str
    updated_at: str
