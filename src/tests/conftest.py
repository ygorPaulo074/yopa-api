"""
Fixtures compartilhadas entre test_agent, test_chat e test_data.
Configura env vars ANTES de qualquer import do src/, usa fakeredis para isolar
o Redis e armazenamento local em diretório temporário.
"""
import os
import pytest
import fakeredis

# ── env vars definidas antes de qualquer import de src/ ───────────────────────
os.environ.setdefault("AI_API_KEY", "test_key")
os.environ.setdefault("AI_MODEL", "gpt-4o")
os.environ.setdefault("AI_TIMEOUT", "30")
os.environ.setdefault("RUN_MODE", "development")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("STORAGE_TYPE", "local")
os.environ.setdefault("DATA_PATH", "/tmp/ai_chatbot_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("SESSION_TTL", "86400")
os.environ.setdefault('ALLOWED_ORIGINS', '["http://localhost"]')
os.environ.setdefault('ANALYZER_LANGUAGES', '["en"]')

# Impede o fluxo interativo de setup
open(".initialized", "w").close()

from unittest.mock import patch  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402
from src.clients.ai_client import AIClient, AIResponse, AIUsage  # noqa: E402
from src.core.cache.client import CacheClient  # noqa: E402
import src.core.security as _security  # noqa: E402

# sanitize_pii como identidade nos testes — evita falsos positivos do Presidio
_security.sanitize_pii = lambda text: text


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fake_redis_server():
    return fakeredis.FakeServer()


@pytest.fixture(autouse=True)
def patch_env(fake_redis_server, monkeypatch, tmp_path):
    """Injeta fakeredis e diretório temporário de storage em cada teste."""
    fake = fakeredis.FakeRedis(server=fake_redis_server, decode_responses=True)
    fake.flushall()  # isolamento: limpa entre testes

    def _fake_cache_init(self):
        self._redis = fake

    monkeypatch.setattr(CacheClient, "__init__", _fake_cache_init)

    # Garante que o LocalDriver use diretório isolado por teste
    from src.infrastructure.config import settings
    monkeypatch.setattr(settings, "DATA_PATH", str(tmp_path))

    # Reseta contadores do rate limiter entre testes para evitar falsos 429
    from src.infrastructure.config import LIMITER
    try:
        LIMITER._storage.clear()
    except Exception:
        pass


@pytest.fixture
def mock_ai():
    """Retorna resposta de IA fixa, sem chamar litellm."""
    fake_response = AIResponse(
        content="Test response from AI.",
        usage=AIUsage(input_tokens=10, output_tokens=5, total_tokens=15),
    )
    with patch.object(AIClient, "complete", return_value=fake_response) as mock:
        yield mock


@pytest.fixture
def client(patch_env):
    from main import app
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def agent(client):
    """Cria um agente e retorna (agent_id, api_key, headers)."""
    resp = client.post("/agent", json={
        "name": "Test Agent",
        "owner": "test_owner",
        "context": {
            "tone": "formal",
            "language": "pt",
            "persona": "Assistente de testes",
            "tags": ["test"],
        },
    })
    assert resp.status_code == 201
    data = resp.json()
    headers = {"Authorization": f"Bearer {data['api_key']}"}
    return data["agent_id"], data["api_key"], headers
