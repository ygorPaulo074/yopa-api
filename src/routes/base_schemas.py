from pydantic import BaseModel
from typing import List

from src.core.schemas import AgentContextBase


class AgentContext(AgentContextBase):
    tags: List[str] = []
