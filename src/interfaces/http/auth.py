"""
Dependência FastAPI para autenticação de agente — suporta dois modos via AUTH_MODE:

  standalone: Bearer {agent_id}.{secret} no header Authorization.
              Usado em deploy direto sem o Yopa Proxy.

  internal:   X-Agent-Id injetado pelo Yopa Proxy após validação da api_key.
              A API confia no header sem re-validar credenciais — o proxy é
              a única entrada e já autenticou antes de repassar.
"""
from fastapi import HTTPException, Request, status

from src.infrastructure.persistence.factory import get_driver
from src.infrastructure.security import verify_api_key
from src.infrastructure.config import settings


async def authenticate_agent(request: Request) -> str:
    if settings.AUTH_MODE == "internal":
        agent_id = request.headers.get("X-Agent-Id", "")
        if not agent_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
        return agent_id

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    api_key = auth_header[7:]
    try:
        agent_id, secret = api_key.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key format")

    agent = get_driver().load_agent(agent_id)
    if not agent or not verify_api_key(secret, agent.api_key_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return agent_id
