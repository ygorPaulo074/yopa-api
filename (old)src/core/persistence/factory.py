"""
Resolve e instancia o driver de persistência correto com base no STORAGE_TYPE do .env.
Valores válidos: 'local', 'database', 'webhook'.
"""

from src.infrastructure.config import settings
from src.core.persistence.base import PersistenceDriver


def get_driver() -> PersistenceDriver:
    storage_type = settings.STORAGE_TYPE.lower()

    if storage_type == "local":
        from src.core.persistence.drivers.local import LocalDriver
        return LocalDriver()

    if storage_type == "database":
        from src.core.persistence.drivers.database import DatabaseDriver
        return DatabaseDriver()

    if storage_type == "webhook":
        from src.core.persistence.drivers.webhook import WebhookDriver
        return WebhookDriver()

    raise ValueError(
        f"STORAGE_TYPE inválido: '{settings.STORAGE_TYPE}'. "
        "Valores aceitos: 'local', 'database', 'webhook'."
    )
