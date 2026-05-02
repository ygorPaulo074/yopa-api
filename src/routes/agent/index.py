"""
Endpoints do agente:
  POST   /agent                    — cria agente, gera context.xml e retorna API Key
  GET    /agent                    — retorna dados do agente autenticado
  GET    /agent/context            — retorna contexto atual com versão
  GET    /agent/context/history    — histórico de versões e campos alterados
  GET    /agent/metrics            — métricas agregadas de sessões e mensagens
  PUT    /agent/context            — atualiza contexto, incrementa versão, regenera XML
  DELETE /agent                    — remove agente, context.xml e todos os dados associados
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status

from src.core.auth import authenticate_agent
from src.services.agent_service import AgentService
from src.services.context_service import ContextService
from src.routes.base_schemas import AgentContext
from .schemas import (
    AgentCreateRequest, AgentCreateResponse, AgentGetResponse,
    AgentContextResponse, AgentContextHistoryResponse, AgentContextHistoryItem,
    AgentMetricsResponse, AgentUpdateContextResponse, AgentDeleteResponse,
)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("", response_model=AgentCreateResponse, status_code=201)
def create_agent(body: AgentCreateRequest):
    result = AgentService().create_agent(body.name, body.owner, body.context)
    return AgentCreateResponse(**result)


@router.get("", response_model=AgentGetResponse)
def get_agent(agent_id: str = Depends(authenticate_agent)):
    agent = AgentService().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentGetResponse(**agent.model_dump())


@router.get("/context", response_model=AgentContextResponse)
def get_context(agent_id: str = Depends(authenticate_agent)):
    record = ContextService().load_context(agent_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Context not found")
    return AgentContextResponse(agent_id=agent_id, version=record.version, **record.context.model_dump())


@router.get("/context/history", response_model=AgentContextHistoryResponse)
def get_context_history(agent_id: str = Depends(authenticate_agent)):
    history = ContextService().load_context_history(agent_id)
    versions = [
        AgentContextHistoryItem(version=r.version, updated_at=r.updated_at, changes=r.changes)
        for r in history
    ]
    return AgentContextHistoryResponse(agent_id=agent_id, versions=versions)


@router.get("/metrics", response_model=AgentMetricsResponse)
def get_metrics(agent_id: str = Depends(authenticate_agent)):
    agent = AgentService().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    metrics = AgentService().get_metrics(agent_id)
    return AgentMetricsResponse(
        agent_id=agent_id,
        active_since=agent.active_since,
        last_activity_at=agent.last_activity_at,
        **metrics,
    )


@router.put("/context", response_model=AgentUpdateContextResponse)
def update_context(body: AgentContext, agent_id: str = Depends(authenticate_agent)):
    record = ContextService().update_context(agent_id, body)
    return AgentUpdateContextResponse(
        agent_id=agent_id,
        version=record.version,
        updated_at=record.updated_at,
    )


@router.delete("", response_model=AgentDeleteResponse)
def delete_agent(agent_id: str = Depends(authenticate_agent)):
    AgentService().delete_agent(agent_id)
    return AgentDeleteResponse(deleted_at=datetime.now(timezone.utc).isoformat())
