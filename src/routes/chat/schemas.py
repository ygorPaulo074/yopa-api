from pydantic import BaseModel
from typing import Literal


class ChatRequest(BaseModel):
    session_id: str
    user_id: str | None = None
    message: str


class TokenUsage(BaseModel):
    input: int
    output: int
    total: int


class SessionInfo(BaseModel):
    session_id: str
    agent_id: str
    model: str
    started_at: str
    response_time_ms: int
    tokens: TokenUsage


class Message(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    status: Literal["delivered", "pending", "failed", "escalated"]
    tokens: int | None = None
    response_time_ms: int | None = None


class ConversationEntry(BaseModel):
    message: Message


class ChatResponse(BaseModel):
    session: SessionInfo
    conversation: list[ConversationEntry]


# ── Lifecycle ────────────────────────────────────────────────

class SessionEndResponse(BaseModel):
    session_id: str
    ended_at: str


class SessionResolveResponse(BaseModel):
    session_id: str
    resolved: bool
    updated_at: str


class SessionEscalateResponse(BaseModel):
    session_id: str
    escalated: bool
    updated_at: str
