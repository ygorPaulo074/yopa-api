from pydantic import BaseModel

from src.core.schemas import AgentContextBase


class AgentContext(AgentContextBase):
    tags: list[str] = []
