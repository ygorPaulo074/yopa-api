"""
Driver de persistência em sistema de arquivos local.
Armazena agentes, sessões e scores como arquivos JSON em DATA_PATH.
Estrutura de diretórios:
  {DATA_PATH}/agents/{agent_id}/agent.json
  {DATA_PATH}/agents/{agent_id}/context/current.json
  {DATA_PATH}/agents/{agent_id}/context/history/v{n}.json
  {DATA_PATH}/agents/{agent_id}/users/{user_id}.json
  {DATA_PATH}/agents/{agent_id}/chats/{session_id}/session.json
  {DATA_PATH}/agents/{agent_id}/chats/{session_id}/scores.json
  {DATA_PATH}/agents/{agent_id}/chats/{session_id}/insights.json
Indicado para desenvolvimento e ambientes sem banco de dados.
"""

import json
import shutil
from pathlib import Path
from src.infrastructure.config import settings
from src.core.persistence.base import PersistenceDriver
from src.core.schemas import (
    AgentRecord,
    AgentContextRecord,
    UserContextRecord,
    SessionRecord,
    InsightRecord,
    ScoreData,
)
from src.core.security import sanitize_pii


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class LocalDriver(PersistenceDriver):

    def __init__(self):
        self._base = Path(settings.DATA_PATH)

    # ── Path helpers ───────────────────────────────────────────────────────────

    def _agent_dir(self, agent_id: str) -> Path:
        return self._base / "agents" / agent_id

    def _agent_file(self, agent_id: str) -> Path:
        return self._agent_dir(agent_id) / "agent.json"

    def _context_current(self, agent_id: str) -> Path:
        return self._agent_dir(agent_id) / "context" / "current.json"

    def _context_version(self, agent_id: str, version: int) -> Path:
        return self._agent_dir(agent_id) / "context" / "history" / f"v{version}.json"

    def _context_history_dir(self, agent_id: str) -> Path:
        return self._agent_dir(agent_id) / "context" / "history"

    def _user_file(self, agent_id: str, user_id: str) -> Path:
        return self._agent_dir(agent_id) / "users" / f"{user_id}.json"

    def _users_dir(self, agent_id: str) -> Path:
        return self._agent_dir(agent_id) / "users"

    def _session_file(self, agent_id: str, session_id: str) -> Path:
        return self._agent_dir(agent_id) / "chats" / session_id / "session.json"

    def _chats_dir(self, agent_id: str) -> Path:
        return self._agent_dir(agent_id) / "chats"

    def _scores_file(self, agent_id: str, session_id: str) -> Path:
        return self._agent_dir(agent_id) / "chats" / session_id / "scores.json"

    def _insights_file(self, agent_id: str, session_id: str) -> Path:
        return self._agent_dir(agent_id) / "chats" / session_id / "insights.json"

    # ── Agent ──────────────────────────────────────────────────────────────────

    def save_agent(self, agent: AgentRecord) -> None:
        sanitized = agent.model_copy(update={"name": sanitize_pii(agent.name)})
        _write(self._agent_file(agent.agent_id), sanitized.model_dump())

    def load_agent(self, agent_id: str) -> AgentRecord | None:
        data = _read(self._agent_file(agent_id))
        return AgentRecord.model_validate(data) if data else None

    def delete_agent(self, agent_id: str) -> None:
        agent_dir = self._agent_dir(agent_id)
        if agent_dir.exists():
            shutil.rmtree(agent_dir)

    # ── Agent context ──────────────────────────────────────────────────────────

    def save_context(self, record: AgentContextRecord) -> None:
        data = record.model_dump()
        _write(self._context_current(record.agent_id), data)
        _write(self._context_version(record.agent_id, record.version), data)

    def load_context(self, agent_id: str) -> AgentContextRecord | None:
        data = _read(self._context_current(agent_id))
        return AgentContextRecord.model_validate(data) if data else None

    def load_context_history(self, agent_id: str) -> list[AgentContextRecord]:
        history_dir = self._context_history_dir(agent_id)
        if not history_dir.exists():
            return []
        records = []
        for file in history_dir.glob("v*.json"):
            data = _read(file)
            if data:
                records.append(AgentContextRecord.model_validate(data))
        return sorted(records, key=lambda r: r.version, reverse=True)

    # ── User context ───────────────────────────────────────────────────────────

    def save_user_context(self, record: UserContextRecord) -> None:
        _write(self._user_file(record.agent_id, record.user_id), record.model_dump())

    def load_user_context(self, agent_id: str, user_id: str) -> UserContextRecord | None:
        data = _read(self._user_file(agent_id, user_id))
        return UserContextRecord.model_validate(data) if data else None

    def list_user_contexts(self, agent_id: str) -> list[UserContextRecord]:
        users_dir = self._users_dir(agent_id)
        if not users_dir.exists():
            return []
        records = []
        for file in users_dir.glob("*.json"):
            data = _read(file)
            if data:
                records.append(UserContextRecord.model_validate(data))
        return records

    def delete_user_context(self, agent_id: str, user_id: str) -> None:
        path = self._user_file(agent_id, user_id)
        if path.exists():
            path.unlink()

    # ── Session ────────────────────────────────────────────────────────────────

    def save_session(self, session: SessionRecord) -> None:
        _write(self._session_file(session.agent_id, session.session_id), session.model_dump())

    def load_session(self, agent_id: str, session_id: str) -> SessionRecord | None:
        data = _read(self._session_file(agent_id, session_id))
        return SessionRecord.model_validate(data) if data else None

    def list_sessions(self, agent_id: str) -> list[SessionRecord]:
        chats_dir = self._chats_dir(agent_id)
        if not chats_dir.exists():
            return []
        records = []
        for session_dir in chats_dir.iterdir():
            if session_dir.is_dir():
                data = _read(session_dir / "session.json")
                if data:
                    records.append(SessionRecord.model_validate(data))
        return records

    def delete_session(self, agent_id: str, session_id: str) -> None:
        session_dir = self._agent_dir(agent_id) / "chats" / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)

    # ── Scores ─────────────────────────────────────────────────────────────────

    def save_scores(self, agent_id: str, scores: ScoreData) -> None:
        _write(self._scores_file(agent_id, scores.session_id), scores.model_dump())

    def load_scores(self, agent_id: str, session_id: str) -> ScoreData | None:
        data = _read(self._scores_file(agent_id, session_id))
        return ScoreData.model_validate(data) if data else None

    # ── Insights ───────────────────────────────────────────────────────────────

    def save_insight(self, agent_id: str, insight: InsightRecord) -> None:
        _write(self._insights_file(agent_id, insight.session_id), insight.model_dump())

    def load_insight(self, agent_id: str, session_id: str) -> InsightRecord | None:
        data = _read(self._insights_file(agent_id, session_id))
        return InsightRecord.model_validate(data) if data else None
