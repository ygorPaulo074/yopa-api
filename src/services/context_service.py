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
from src.core.schemas import AgentContextBase, AgentContextRecord, AgentSkillRecord, SqlDatasourceConfig
from src.core.security import encrypt_secret
from src.routes.base_schemas import AgentContext


class ContextService:

    def __init__(self):
        self.driver: PersistenceDriver = get_driver()
        self.cache = CacheClient()

    def _encrypt_sql_credentials(self, context: AgentContext) -> AgentContext:
        """Encripta a connection string do sql_datasource antes de persistir."""
        if not context.sql_datasource:
            return context
        enc = encrypt_secret(context.sql_datasource.connection_string)
        updated_sql = SqlDatasourceConfig(
            connection_string=enc,
            allowed_tables=context.sql_datasource.allowed_tables,
            max_rows=context.sql_datasource.max_rows,
        )
        return context.model_copy(update={"sql_datasource": updated_sql})

    def create_context(self, agent_id: str, context: AgentContext) -> None:
        context = self._encrypt_sql_credentials(context)
        now = datetime.now(timezone.utc).isoformat()
        system_prompt = build_system_prompt(context)
        record = AgentContextRecord(
            agent_id=agent_id,
            version=1,
            context=AgentContextBase(**context.model_dump(exclude={"tags"})),
            changes=[],
            updated_at=now,
        )
        self.driver.save_context(record)
        self.cache.set_context(agent_id, system_prompt)
        self.driver.save_skill(agent_id, AgentSkillRecord(
            agent_id=agent_id,
            version=1,
            system_prompt=system_prompt,
            context_snapshot=record.context.model_dump(mode="json"),
            compiled_at=now,
        ))

    def update_context(self, agent_id: str, new_context: AgentContext) -> AgentContextRecord:
        new_context = self._encrypt_sql_credentials(new_context)
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
        self.driver.save_skill(agent_id, AgentSkillRecord(
            agent_id=agent_id,
            version=record.version,
            system_prompt=system_prompt,
            context_snapshot=record.context.model_dump(mode="json"),
            compiled_at=record.updated_at,
        ))

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
