"""
Contrato abstrato dos drivers de persistência (Strategy Pattern).
Define a interface que Local, Database e Webhook devem implementar.
Qualquer chamada de persistência nos services deve operar sobre este contrato,
nunca sobre um driver concreto diretamente — permite trocar o storage via .env
sem alterar a lógica de negócio.

Segurança é responsabilidade dos drivers concretos:
  - Sanitização de PII ocorre nos métodos save_* de cada driver
  - Cada driver importa diretamente de src.core.security o que precisar
"""

from abc import ABC, abstractmethod
from src.core.schemas import (
    AgentRecord,
    AgentContextRecord,
    UserContextRecord,
    SessionRecord,
    InsightRecord,
    ScoreData,
)


class PersistenceDriver(ABC):

    # ── Agent ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_agent(self, agent: AgentRecord) -> None: ...

    @abstractmethod
    def load_agent(self, agent_id: str) -> AgentRecord | None: ...

    @abstractmethod
    def delete_agent(self, agent_id: str) -> None: ...

    # ── Agent context ──────────────────────────────────────────────────────────

    @abstractmethod
    def save_context(self, record: AgentContextRecord) -> None: ...

    @abstractmethod
    def load_context(self, agent_id: str) -> AgentContextRecord | None: ...

    @abstractmethod
    def load_context_history(self, agent_id: str) -> list[AgentContextRecord]: ...

    # ── User context ───────────────────────────────────────────────────────────

    @abstractmethod
    def save_user_context(self, record: UserContextRecord) -> None: ...

    @abstractmethod
    def load_user_context(self, agent_id: str, user_id: str) -> UserContextRecord | None: ...

    @abstractmethod
    def list_user_contexts(self, agent_id: str) -> list[UserContextRecord]: ...

    @abstractmethod
    def delete_user_context(self, agent_id: str, user_id: str) -> None: ...

    # ── Session ────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_session(self, session: SessionRecord) -> None: ...

    @abstractmethod
    def load_session(self, agent_id: str, session_id: str) -> SessionRecord | None: ...

    @abstractmethod
    def list_sessions(self, agent_id: str) -> list[SessionRecord]: ...

    @abstractmethod
    def delete_session(self, agent_id: str, session_id: str) -> None: ...

    # ── Scores ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def save_scores(self, agent_id: str, scores: ScoreData) -> None: ...

    @abstractmethod
    def load_scores(self, agent_id: str, session_id: str) -> ScoreData | None: ...

    # ── Insights ───────────────────────────────────────────────────────────────

    @abstractmethod
    def save_insight(self, agent_id: str, insight: InsightRecord) -> None: ...

    @abstractmethod
    def load_insight(self, agent_id: str, session_id: str) -> InsightRecord | None: ...
