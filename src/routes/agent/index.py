"""
Endpoints do agente:
  POST   /agent                    — cria agente, gera context.xml e retorna API Key
  GET    /agent                    — retorna dados do agente autenticado
  GET    /agent/context            — retorna contexto atual com versão
  GET    /agent/context/history    — histórico de versões e campos alterados
  GET    /agent/metrics            — métricas agregadas de sessões e mensagens
  PUT    /agent/context            — atualiza contexto, incrementa versão, regenera XML
  DELETE /agent                    — remove agente, context.xml e todos os dados associados
  POST   /agent/parse-context      — parseia texto livre em AgentContextBase via LLM
"""
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from src.clients.ai_client import AIClient
from src.core.auth import authenticate_agent
from src.infrastructure.config import LIMITER, settings
from src.core.ingestion.file_extractor import extract
from src.core.ingestion.url_fetcher import fetch as fetch_url
from src.core.persistence.factory import get_driver
from src.core.schemas import KnowledgeFileRecord
from src.services.agent_service import AgentService
from src.services.context_service import ContextService
from src.routes.base_schemas import AgentContext
from .schemas import (
    AgentCreateRequest, AgentCreateResponse, AgentGetResponse,
    AgentContextResponse, AgentContextHistoryResponse, AgentContextHistoryItem,
    AgentMetricsResponse, AgentUpdateContextResponse, AgentDeleteResponse,
    KnowledgeFileUploadResponse, KnowledgeFileListResponse,
    KnowledgeFileItem, KnowledgeFileDeleteResponse,
    KnowledgeFetchUrlRequest,
    ParseContextRequest, ParseContextResponse,
    ValidateSqlRequest, ValidateSqlResponse,
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


@router.post("/knowledge/upload", response_model=KnowledgeFileUploadResponse, status_code=201)
async def upload_knowledge_file(
    file: UploadFile = File(...),
    agent_id: str = Depends(authenticate_agent),
):
    content = await file.read()
    try:
        records = extract(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    now = datetime.now(timezone.utc).isoformat()
    file_id = str(uuid.uuid4())
    ext = file.filename.rsplit(".", 1)[-1].lower()
    file_type = "excel" if ext in ("xls", "xlsx") else ext

    record = KnowledgeFileRecord(
        file_id=file_id,
        agent_id=agent_id,
        filename=file.filename,
        file_type=file_type,
        records=records,
        uploaded_at=now,
        updated_at=now,
    )
    get_driver().save_knowledge_file(agent_id, record)

    return KnowledgeFileUploadResponse(
        file_id=file_id,
        filename=file.filename,
        file_type=file_type,
        record_count=len(records),
        uploaded_at=now,
    )


@router.post("/knowledge/fetch-url", response_model=KnowledgeFileUploadResponse, status_code=201)
def fetch_knowledge_url(
    body: KnowledgeFetchUrlRequest,
    agent_id: str = Depends(authenticate_agent),
):
    try:
        records = fetch_url(body.url)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    if not records:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No content extracted from URL")

    now = datetime.now(timezone.utc).isoformat()
    file_id = str(uuid.uuid4())
    hostname = body.url.split("/")[2] if "//" in body.url else body.url

    record = KnowledgeFileRecord(
        file_id=file_id,
        agent_id=agent_id,
        filename=hostname,
        file_type="url",
        records=records,
        uploaded_at=now,
        updated_at=now,
    )
    get_driver().save_knowledge_file(agent_id, record)

    return KnowledgeFileUploadResponse(
        file_id=file_id,
        filename=hostname,
        file_type="url",
        record_count=len(records),
        uploaded_at=now,
    )


@router.get("/knowledge", response_model=KnowledgeFileListResponse)
def list_knowledge_files(agent_id: str = Depends(authenticate_agent)):
    files = get_driver().list_knowledge_files(agent_id)
    return KnowledgeFileListResponse(files=[
        KnowledgeFileItem(
            file_id=f.file_id,
            filename=f.filename,
            file_type=f.file_type,
            record_count=len(f.records),
            uploaded_at=f.uploaded_at,
            updated_at=f.updated_at,
        )
        for f in files
    ])


@router.delete("/knowledge/{file_id}", response_model=KnowledgeFileDeleteResponse)
def delete_knowledge_file(file_id: str, agent_id: str = Depends(authenticate_agent)):
    driver = get_driver()
    record = driver.load_knowledge_file(agent_id, file_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    driver.delete_knowledge_file(agent_id, file_id)
    return KnowledgeFileDeleteResponse(file_id=file_id, deleted=True)


_PARSE_SYSTEM = """You are a JSON extractor. Given a free-text description of a chatbot agent,
extract structured configuration. Return ONLY valid JSON — no markdown, no explanation.
Omit fields not mentioned. Use these types:
{
  "tone": "formal" | "informal" | "neutro" | null,
  "language": "<BCP-47 code>" | null,
  "segment": "<business segment>" | null,
  "persona": "<agent identity description>" | null,
  "behavior": "<behavioral guidelines>" | null,
  "fallback_message": "<default reply when out of scope>" | null,
  "restrictions": {"topics": ["<topic>", ...]} | null,
  "escalation_trigger": {
    "operator": "OR" | "AND",
    "conditions": [{
      "type": "keyword" | "sentiment" | "message_count" | "topic" | "time_elapsed" | "intent",
      "value": "<string or number>" | null,
      "values": ["<string>", ...] | null,
      "threshold": <number> | null
    }]
  } | null,
  "escalation_destination": {
    "type": "webhook" | "email" | "github_issue" | "queue" | "none",
    "url": "<webhook URL>" | null,
    "token": "<bearer token>" | null,
    "address": "<email address>" | null,
    "repo": "<owner/repo>" | null,
    "github_token": "<GitHub token>" | null,
    "queue_url": "<queue URL>" | null
  } | null
}"""


@router.post("/validate-sql", response_model=ValidateSqlResponse)
@LIMITER.limit(settings.RATE_LIMIT_VALIDATE_SQL)
def validate_sql_connection(request: Request, body: ValidateSqlRequest):
    from urllib.parse import urlparse
    from src.core.tools.sql_tool import validate_connection_string
    from sqlalchemy import create_engine, inspect

    try:
        validate_connection_string(body.connection_string)
    except ValueError as e:
        return ValidateSqlResponse(valid=False, error=str(e))

    parsed = urlparse(body.connection_string)
    dialect = parsed.scheme.split("+")[0].lower()

    try:
        engine = create_engine(body.connection_string, pool_pre_ping=True)
        insp = inspect(engine)
        tables = insp.get_table_names()
        engine.dispose()
        return ValidateSqlResponse(valid=True, dialect=dialect, tables=tables)
    except Exception as e:
        return ValidateSqlResponse(valid=False, dialect=dialect, error=str(e)[:200])


@router.post("/parse-context", response_model=ParseContextResponse)
@LIMITER.limit(settings.RATE_LIMIT_PARSE_CONTEXT)
def parse_context_from_text(request: Request, body: ParseContextRequest):
    from src.core.schemas import HistoryMessage
    dummy_msg = HistoryMessage(
        message_id="0", session_id="0", role="user",
        content=body.text, timestamp="", status="delivered",
    )
    try:
        response = AIClient().complete(
            system=_PARSE_SYSTEM,
            messages=[dummy_msg],
            max_tokens=512,
        )
        parsed = json.loads(response.content)
    except Exception:
        raise HTTPException(status_code=422, detail="Não foi possível estruturar o texto fornecido.")

    from src.core.schemas import AgentContextBase
    try:
        context = AgentContextBase.model_validate(parsed)
    except Exception:
        raise HTTPException(status_code=422, detail="Resposta da IA fora do formato esperado.")

    return ParseContextResponse(context=context)
