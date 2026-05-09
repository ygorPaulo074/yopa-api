"""
Entidades do domínio Knowledge: arquivos e URLs indexados por agente para uso como contexto no chat.
"""
from typing import Any, Literal
from pydantic import BaseModel


class KnowledgeFileRecord(BaseModel):
    file_id: str
    agent_id: str
    filename: str
    file_type: Literal["csv", "json", "pdf", "excel", "txt", "docx", "url"]
    records: list[dict[str, Any]] = []
    uploaded_at: str
    updated_at: str
