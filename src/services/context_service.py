"""
Gerencia o versionamento de contexto dos agentes.
Cada criação ou atualização persiste um AgentContextRecord com versão incrementada,
registra os campos alterados em changes e mantém o system prompt sincronizado no Redis.
"""
from datetime import datetime, timezone

from src.core.persistence.factory import get_driver
from src.core.persistence.base import PersistenceDriver
from src.core.cache.client import CacheClient
from src.core.context_builder import build_system_prompt
from src.core.schemas import AgentContextBase, AgentContextRecord
from src.routes.base_schemas import AgentContext


class ContextService:

    def __init__(self):
        self.driver: PersistenceDriver = get_driver()
        self.cache = CacheClient()

    def create_context(self, agent_id: str, context: AgentContext) -> None:
        system_prompt = build_system_prompt(context)
        record = AgentContextRecord(
            agent_id=agent_id,
            version=1,
            context=AgentContextBase(**context.model_dump(exclude={"tags"})),
            changes=[],
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.driver.save_context(record)
        self.cache.set_context(agent_id, system_prompt)

    def update_context(self, agent_id: str, new_context: AgentContext) -> AgentContextRecord:
        current = self.driver.load_context(agent_id)
        current_version = current.version if current else 0
        current_base = current.context if current else None

        changes = self.diff_context(current_base, new_context) if current_base else []

        record = AgentContextRecord(
            agent_id=agent_id,
            version=current_version + 1,
            context=AgentContextBase(**new_context.model_dump(exclude={"tags"})),
            changes=changes,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.driver.save_context(record)

        system_prompt = build_system_prompt(new_context)
        self.cache.set_context(agent_id, system_prompt)

        return record

    def load_context(self, agent_id: str) -> AgentContextRecord | None:
        return self.driver.load_context(agent_id)

    def load_system_prompt(self, agent_id: str) -> str | None:
        cached = self.cache.get_context(agent_id)
        if cached:
            return cached

        record = self.driver.load_context(agent_id)
        if not record:
            return None

        context = AgentContext(**record.context.model_dump())
        system_prompt = build_system_prompt(context)
        self.cache.set_context(agent_id, system_prompt)
        return system_prompt

    def load_context_history(self, agent_id: str) -> list[AgentContextRecord]:
        return self.driver.load_context_history(agent_id)

    def diff_context(
        self,
        old: AgentContextBase | AgentContext,
        new: AgentContextBase | AgentContext,
    ) -> list[str]:
        old_data = old.model_dump(exclude={"tags"})
        new_data = new.model_dump(exclude={"tags"})
        return [field for field in new_data if new_data[field] != old_data.get(field)]
