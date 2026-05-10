"""
Development-only routes — active exclusively when RUN_MODE=development.
All requests to /dev/* return 403 in production.

  GET  /agent-test                  — serve the Agent Test UI (chat + sessions + analytics)
  GET  /dev/agents                  — list all agents (id, name, owner, model, validated)
  POST /dev/token/{agent_id}        — rotate agent API key and return new bearer token
  POST /dev/agent/ephemeral         — create ephemeral agent in Redis (no DB, 24h TTL)
"""
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from src.application.context_builder import build_system_prompt
from src.domain.agent import AgentContextBase
from src.infrastructure.cache.redis_client import CacheClient
from src.infrastructure.config import settings
from src.infrastructure.persistence.factory import get_driver
from src.infrastructure.security import generate_api_key, hash_api_key

router = APIRouter()

_STATIC = Path(__file__).parents[2] / "static"


def _require_dev() -> None:
    if settings.RUN_MODE != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available in development mode (RUN_MODE=development).",
        )

@router.get("/dev/agents")
def list_agents():
    _require_dev()
    agents = get_driver().list_agents()
    return JSONResponse([
        {
            "agent_id":    a.agent_id,
            "name":        a.name,
            "owner":       a.owner,
            "ai_model":    a.ai_model,
            "ai_validated": a.ai_validated,
            "created_at":  a.created_at,
            "active_since": a.active_since,
            "last_activity_at": a.last_activity_at,
        }
        for a in agents
    ])


@router.post("/dev/token/{agent_id}")
def rotate_token(agent_id: str):
    _require_dev()
    driver = get_driver()
    agent = driver.load_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    new_secret = generate_api_key()
    new_hash = hash_api_key(new_secret)
    now = datetime.now(timezone.utc).isoformat()
    driver.save_agent(agent.model_copy(update={
        "api_key_hash": new_hash,
        "updated_at": now,
    }))

    return JSONResponse({"bearer_token": f"{agent_id}.{new_secret}"})


class EphemeralAgentRequest(BaseModel):
    name: str
    context: dict


@router.post("/dev/agent/ephemeral")
def create_ephemeral_agent(body: EphemeralAgentRequest):
    _require_dev()
    import uuid
    agent_id    = str(uuid.uuid4())
    secret      = generate_api_key()
    secret_hash = hash_api_key(secret)
    context     = AgentContextBase(**body.context)
    system_prompt = build_system_prompt(context)
    CacheClient().set_ephemeral_agent(agent_id, body.name, secret_hash, system_prompt)
    return JSONResponse({
        "agent_id": agent_id,
        "name":     body.name,
        "api_key":  f"{agent_id}.{secret}",
    })
