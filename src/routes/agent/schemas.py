from pydantic import BaseModel, Field
from typing import Optional, List
from ..base_schemas import AgentContext, AgentContextBase


class AgentCreateRequest(BaseModel):
    name: str 
    context: AgentContext


class AgentCreateResponse(BaseModel):
    agent_id: str
    api_key: str
    created_at: str


class AgentGetResponse(BaseModel):
    agent_id: str
    name: str
    owner: str
    tags: List[str] = []
    created_at: str
    updated_at: str
    active_since: Optional[str] = None
    last_activity_at: Optional[str] = None


class AgentContextResponse(AgentContextBase):
    agent_id: str
    version: int


class AgentContextHistoryItem(BaseModel):
    version: int
    updated_at: str
    changes: List[str]


class AgentContextHistoryResponse(BaseModel):
    agent_id: str
    versions: List[AgentContextHistoryItem]


class AgentMetricsResponse(BaseModel):
    agent_id: str
    total_sessions: int
    total_messages: int
    avg_response_time_ms: float
    resolution_rate: float
    escalation_rate: float
    active_since: Optional[str] = None
    last_activity_at: Optional[str] = None


# Todos os campos opcionais — PATCH semântico
class AgentUpdateContextRequest(AgentContext):
    pass


class AgentUpdateContextResponse(BaseModel):
    agent_id: str
    version: int
    updated_at: str


class AgentDeleteResponse(BaseModel):
    deleted_at: str
