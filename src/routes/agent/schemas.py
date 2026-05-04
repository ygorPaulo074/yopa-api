from pydantic import BaseModel
from src.core.schemas import AgentContextBase
from ..base_schemas import AgentContext


class AgentCreateRequest(BaseModel):
    name: str
    owner: str
    context: AgentContext


class AgentCreateResponse(BaseModel):
    agent_id: str
    api_key: str
    created_at: str


class AgentGetResponse(BaseModel):
    agent_id: str
    name: str
    owner: str
    tags: list[str] = []
    created_at: str
    updated_at: str
    active_since: str | None = None
    last_activity_at: str | None = None


class AgentContextResponse(AgentContextBase):
    agent_id: str
    version: int


class AgentContextHistoryItem(BaseModel):
    version: int
    updated_at: str
    changes: list[str]


class AgentContextHistoryResponse(BaseModel):
    agent_id: str
    versions: list[AgentContextHistoryItem]


class AgentMetricsResponse(BaseModel):
    agent_id: str
    total_sessions: int
    total_messages: int
    total_tokens: int
    resolution_rate: float
    escalation_rate: float
    active_since: str | None = None
    last_activity_at: str | None = None


class AgentUpdateContextResponse(BaseModel):
    agent_id: str
    version: int
    updated_at: str


class AgentDeleteResponse(BaseModel):
    deleted_at: str


class KnowledgeFileUploadResponse(BaseModel):
    file_id: str
    filename: str
    file_type: str
    record_count: int
    uploaded_at: str


class KnowledgeFileItem(BaseModel):
    file_id: str
    filename: str
    file_type: str
    record_count: int
    uploaded_at: str
    updated_at: str


class KnowledgeFileListResponse(BaseModel):
    files: list[KnowledgeFileItem]


class KnowledgeFileDeleteResponse(BaseModel):
    file_id: str
    deleted: bool
