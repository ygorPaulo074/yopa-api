"""
Dependência FastAPI para autenticação por API Key.
Formato da chave: {agent_id}.{secret} — permite derivar o agent_id sem lookup por hash.
"""
from fastapi import Depends, HTTPException, status
from src.core.persistence.factory import get_driver
from src.core.security import get_api_key, verify_api_key


async def authenticate_agent(api_key: str = Depends(get_api_key)) -> str:
    try:
        agent_id, secret = api_key.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    driver = get_driver()
    agent = driver.load_agent(agent_id)
    if not agent or not verify_api_key(secret, agent.api_key_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return agent_id
