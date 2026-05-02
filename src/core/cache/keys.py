"""
Funções auxiliares para nomeação de chaves Redis.
Centraliza o padrão de nomenclatura — garante consistência entre CacheClient,
qualquer outro módulo que acesse o Redis diretamente e os scripts de limpeza.
"""

def context_key(agent_id: str) -> str:
    return f"agent:{agent_id}:context"

def history_key(session_id: str) -> str:
    return f"session:{session_id}:history"

def scores_key(session_id: str) -> str:
    return f"session:{session_id}:scores"

def meta_key(session_id: str) -> str:
    return f"session:{session_id}:meta"
