"""
Despacha escalações para o destino configurado em AgentContextBase.escalation_destination.

Destinos implementados:
  webhook      — POST JSON para a URL configurada
  none         — não faz nada (comportamento padrão)

Stubs (aceitos no schema, não implementados ainda):
  email, github_issue, queue
"""
from datetime import datetime, timezone
from typing import Literal

import requests

from src.core.schemas import AgentContextBase, HistoryMessage, SessionMeta


def dispatch_escalation(
    agent_id: str,
    session_id: str,
    reason: Literal["automatic", "manual"],
    context: AgentContextBase,
    meta: SessionMeta,
    history: list[HistoryMessage],
) -> None:
    dest = context.escalation_destination
    if not dest or dest.type == "none":
        return

    payload = {
        "event": "escalation",
        "session_id": session_id,
        "agent_id": agent_id,
        "user_id": meta.user_id,
        "reason": reason,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "last_messages": [
            {"role": m.role, "content": m.content}
            for m in history[-5:]
        ],
    }

    if dest.type == "webhook":
        _dispatch_webhook(dest.url, dest.token, payload)


def _dispatch_webhook(url: str, token: str | None, payload: dict) -> None:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception:
        pass
