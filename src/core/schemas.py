"""
Modelos internos de persistência e cache.
Usados por drivers, CacheClient e services — nunca expostos diretamente pela API.
Os schemas de rota (src/routes/*/schemas.py) são derivados destes ao montar respostas.
"""

from pydantic import BaseModel
from typing import Any, Dict, List, Literal, Optional
from src.routes.base_schemas import AgentContextBase


# ── Cache: session history ────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    message_id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    status: Literal["delivered", "pending", "failed", "escalated"]
    tokens: Optional[int] = None
    response_time_ms: Optional[int] = None


# ── Cache: session metadata ───────────────────────────────────────────────────

class SessionMeta(BaseModel):
    session_id: str
    agent_id: str
    user_id: Optional[str] = None
    model: str
    started_at: str
    ended_at: Optional[str] = None
    total_messages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    resolved: bool = False
    escalated: bool = False


# ── Cache: NLP scores (per message) ──────────────────────────────────────────

class ScoreData(BaseModel):
    session_id: str
    message_id: str
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[Literal["positive", "neutral", "negative"]] = None
    topics: Optional[List[str]] = None
    main_topic: Optional[str] = None
    intent: Optional[str] = None
    created_at: str


# ── Persistence: agent ────────────────────────────────────────────────────────

class AgentRecord(BaseModel):
    agent_id: str
    name: str
    owner: str
    api_key_hash: str
    tags: List[str] = []
    created_at: str
    updated_at: str
    active_since: Optional[str] = None
    last_activity_at: Optional[str] = None


# ── Persistence: agent context (versioned) ────────────────────────────────────

class AgentContextRecord(BaseModel):
    agent_id: str
    version: int
    context: AgentContextBase
    changes: List[str] = []
    updated_at: str


# ── Persistence: user context ─────────────────────────────────────────────────

class UserContextRecord(BaseModel):
    user_id: str
    agent_id: str
    segment: Optional[str] = None
    language: Optional[str] = None
    form_answers: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str


# ── Persistence: session (cold storage) ──────────────────────────────────────

class SessionRecord(BaseModel):
    session_id: str
    agent_id: str
    user_id: Optional[str] = None
    model: str
    started_at: str
    ended_at: Optional[str] = None
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
    key_points: List[str] = []
    suggested_actions: List[str] = []
    summary: str
