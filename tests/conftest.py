"""
Shared fixtures for test_agent, test_chat, and test_data.
Sets env vars BEFORE any src/ imports; uses fakeredis for isolation
and a temporary directory for local storage.
"""
import os
import pytest
import fakeredis

# ── env vars set before any src/ import ───────────────────────────────────────
os.environ.setdefault("AI_API_KEY", "test_key")
os.environ.setdefault("AI_MODEL", "gpt-4o")
os.environ.setdefault("AI_TIMEOUT", "30")
os.environ.setdefault("RUN_MODE", "development")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("STORAGE_TYPE", "local")
os.environ.setdefault("DATA_PATH", "/tmp/ai_chatbot_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("SESSION_TTL", "86400")
os.environ.setdefault("ANALYZER_LANGUAGES", '["en"]')

# Prevents the interactive setup wizard from blocking
open(".initialized", "w").close()

from unittest.mock import patch  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402
from src.infrastructure.ai.client import AIClient, AIResponse, AIUsage  # noqa: E402
from src.infrastructure.cache.redis_client import CacheClient  # noqa: E402
import src.infrastructure.security as _security  # noqa: E402

# Treat PII sanitization as identity in tests — avoids false positives from Presidio
_security.sanitize_pii = lambda text: text


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fake_redis_server():
    return fakeredis.FakeServer()


@pytest.fixture(autouse=True)
def patch_env(fake_redis_server, monkeypatch, tmp_path):
    """Injects fakeredis and an isolated temp storage directory per test."""
    fake = fakeredis.FakeRedis(server=fake_redis_server, decode_responses=True)
    fake.flushall()

    def _fake_cache_init(self):
        self._redis = fake

    monkeypatch.setattr(CacheClient, "__init__", _fake_cache_init)

    from src.infrastructure.config import settings
    monkeypatch.setattr(settings, "DATA_PATH", str(tmp_path))


@pytest.fixture
def mock_ai():
    """Returns a fixed AI response without calling litellm."""
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
    """Creates an agent and returns (agent_id, api_key, headers)."""
    resp = client.post("/agent", json={
        "name": "Test Agent",
        "owner": "test_owner",
        "context": {
            "tone": "formal",
            "language": "pt",
            "persona": "Assistente de testes",
        },
    })
    assert resp.status_code == 201
    data = resp.json()
    headers = {"Authorization": f"Bearer {data['api_key']}"}
    return data["agent_id"], data["api_key"], headers
