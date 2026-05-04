"""
Testes de integração para os endpoints do agente:
  POST   /agent                  — criação, geração de API Key e context.xml
  GET    /agent                  — leitura de dados do agente autenticado
  GET    /agent/context          — contexto atual com versão
  GET    /agent/context/history  — histórico de versões e campos alterados
  GET    /agent/metrics          — métricas agregadas de sessões
  PUT    /agent/context          — atualização de contexto e incremento de versão
  DELETE /agent                  — remoção do agente e dados associados
"""
import io
import uuid
from unittest.mock import patch, MagicMock

import httpx
import pytest


AGENT_PAYLOAD = {
    "name": "Support Bot",
    "owner": "acme_corp",
    "context": {
        "tone": "formal",
        "language": "pt",
        "persona": "Assistente de suporte",
        "tags": ["support", "pt"],
    },
}


class TestCreateAgent:
    def test_returns_201_with_agent_id_and_api_key(self, client):
        resp = client.post("/agent", json=AGENT_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert "agent_id" in body
        assert "api_key" in body
        assert "created_at" in body

    def test_api_key_contains_agent_id(self, client):
        resp = client.post("/agent", json=AGENT_PAYLOAD)
        body = resp.json()
        assert body["api_key"].startswith(body["agent_id"] + ".")

    def test_missing_name_returns_422(self, client):
        resp = client.post("/agent", json={"owner": "x", "context": {}})
        assert resp.status_code == 422

    def test_missing_owner_returns_422(self, client):
        resp = client.post("/agent", json={"name": "x", "context": {}})
        assert resp.status_code == 422


class TestGetAgent:
    def test_returns_agent_data(self, client, agent):
        agent_id, _, headers = agent
        resp = client.get("/agent", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_id"] == agent_id
        assert body["name"] == "Test Agent"
        assert body["owner"] == "test_owner"

    def test_invalid_key_returns_401(self, client):
        resp = client.get("/agent", headers={"Authorization": "Bearer fake.key"})
        assert resp.status_code == 401

    def test_missing_auth_returns_403(self, client):
        resp = client.get("/agent")
        assert resp.status_code in (401, 403)


class TestGetContext:
    def test_returns_context_with_version(self, client, agent):
        _, _, headers = agent
        resp = client.get("/agent/context", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == 1
        assert body["tone"] == "formal"
        assert body["language"] == "pt"

    def test_context_history_has_one_entry_after_create(self, client, agent):
        _, _, headers = agent
        resp = client.get("/agent/context/history", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["versions"]) == 1
        assert body["versions"][0]["version"] == 1


class TestUpdateContext:
    def test_increments_version(self, client, agent):
        _, _, headers = agent
        resp = client.put("/agent/context", headers=headers, json={
            "tone": "informal",
            "language": "en",
            "tags": [],
        })
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

    def test_history_grows_after_update(self, client, agent):
        _, _, headers = agent
        client.put("/agent/context", headers=headers, json={"tone": "informal", "tags": []})
        resp = client.get("/agent/context/history", headers=headers)
        body = resp.json()
        assert len(body["versions"]) == 2

    def test_changes_field_reflects_updated_keys(self, client, agent):
        _, _, headers = agent
        client.put("/agent/context", headers=headers, json={"tone": "informal", "tags": []})
        resp = client.get("/agent/context/history", headers=headers)
        versions = resp.json()["versions"]
        latest = next(v for v in versions if v["version"] == 2)
        assert "tone" in latest["changes"]

    def test_context_reflects_new_values(self, client, agent):
        _, _, headers = agent
        client.put("/agent/context", headers=headers, json={"tone": "informal", "tags": []})
        resp = client.get("/agent/context", headers=headers)
        assert resp.json()["tone"] == "informal"


class TestGetMetrics:
    def test_returns_zero_metrics_with_no_sessions(self, client, agent):
        agent_id, _, headers = agent
        resp = client.get("/agent/metrics", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_id"] == agent_id
        assert body["total_sessions"] == 0
        assert body["total_messages"] == 0
        assert body["resolution_rate"] == 0.0
        assert body["escalation_rate"] == 0.0


class TestDeleteAgent:
    def test_returns_deleted_at(self, client, agent):
        _, _, headers = agent
        resp = client.delete("/agent", headers=headers)
        assert resp.status_code == 200
        assert "deleted_at" in resp.json()

    def test_agent_not_accessible_after_delete(self, client, agent):
        _, _, headers = agent
        client.delete("/agent", headers=headers)
        resp = client.get("/agent", headers=headers)
        assert resp.status_code == 401


class TestWebhookDatasource:
    def test_create_agent_with_webhook_datasource(self, client):
        resp = client.post("/agent", json={
            "name": "Webhook Bot",
            "owner": "acme",
            "context": {
                "webhook_datasource": {
                    "url": "https://hooks.example.com/query",
                    "token": "secret123",
                },
                "tags": [],
            },
        })
        assert resp.status_code == 201

    def test_context_stores_webhook_datasource(self, client):
        resp = client.post("/agent", json={
            "name": "Webhook Bot",
            "owner": "acme",
            "context": {
                "webhook_datasource": {
                    "url": "https://hooks.example.com/query",
                },
                "tags": [],
            },
        })
        body = resp.json()
        headers = {"Authorization": f"Bearer {body['api_key']}"}
        ctx = client.get("/agent/context", headers=headers).json()
        assert ctx["webhook_datasource"] is not None
        assert "hooks.example.com" in ctx["webhook_datasource"]["url"]

    def test_update_context_with_webhook_datasource(self, client, agent):
        _, _, headers = agent
        resp = client.put("/agent/context", headers=headers, json={
            "webhook_datasource": {
                "url": "https://hooks.example.com/v2",
                "token": "newtoken",
            },
            "tags": [],
        })
        assert resp.status_code == 200
        ctx = client.get("/agent/context", headers=headers).json()
        assert "v2" in ctx["webhook_datasource"]["url"]


class TestWebhookTool:
    def test_execute_returns_formatted_results(self):
        from src.core.tools.webhook_tool import WebhookTool

        fake_response = MagicMock()
        fake_response.json.return_value = [
            {"product": "Widget A", "price": "10.00"},
            {"product": "Widget B", "price": "20.00"},
        ]
        fake_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=fake_response) as mock_post:
            tool = WebhookTool(url="https://hooks.example.com/query", token="tok")
            result = tool.execute("widget")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["json"] == {"query": "widget"}
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer tok"
        assert "Widget A" in result

    def test_execute_raises_timeout_error(self):
        from src.core.tools.webhook_tool import WebhookTool

        with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
            tool = WebhookTool(url="https://hooks.example.com/query")
            with pytest.raises(TimeoutError):
                tool.execute("test")

    def test_execute_raises_runtime_error_on_http_error(self):
        from src.core.tools.webhook_tool import WebhookTool

        with patch("httpx.post", side_effect=httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )):
            tool = WebhookTool(url="https://hooks.example.com/query")
            with pytest.raises(RuntimeError):
                tool.execute("test")

    def test_execute_no_token_omits_auth_header(self):
        from src.core.tools.webhook_tool import WebhookTool

        fake_response = MagicMock()
        fake_response.json.return_value = []
        fake_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=fake_response) as mock_post:
            tool = WebhookTool(url="https://hooks.example.com/query")
            tool.execute("test")

        headers = mock_post.call_args.kwargs["headers"]
        assert "Authorization" not in headers

    def test_build_tools_includes_webhook_when_configured(self, client, agent, mock_ai):
        from unittest.mock import patch as _patch
        from src.core.tools.webhook_tool import WebhookTool

        _, _, headers = agent
        client.put("/agent/context", headers=headers, json={
            "webhook_datasource": {
                "url": "https://hooks.example.com/query",
            },
            "tags": [],
        })

        fake_response = MagicMock()
        fake_response.json.return_value = [{"answer": "42"}]
        fake_response.raise_for_status = MagicMock()

        with _patch("httpx.post", return_value=fake_response):
            resp = client.post("/chat", headers=headers, json={
                "session_id": str(uuid.uuid4()),
                "message": "What is the answer?",
            })
        assert resp.status_code == 200


class TestSkillPersistence:
    def test_skill_saved_on_create(self, client, tmp_path):
        resp = client.post("/agent", json={
            "name": "Skill Bot",
            "owner": "acme",
            "context": {"tone": "formal", "language": "pt", "tags": []},
        })
        assert resp.status_code == 201
        agent_id = resp.json()["agent_id"]

        from src.core.persistence.factory import get_driver
        skill = get_driver().load_skill(agent_id)
        assert skill is not None
        assert skill.version == 1
        assert skill.agent_id == agent_id
        assert isinstance(skill.system_prompt, str)
        assert "context_snapshot" in skill.model_dump()

    def test_skill_version_increments_with_context_update(self, client, agent):
        agent_id, _, headers = agent
        client.put("/agent/context", headers=headers, json={"tone": "informal", "tags": []})

        from src.core.persistence.factory import get_driver
        skill = get_driver().load_skill(agent_id)
        assert skill.version == 2

    def test_skill_context_snapshot_reflects_latest_context(self, client, agent):
        _, _, headers = agent
        client.put("/agent/context", headers=headers, json={"tone": "informal", "language": "en", "tags": []})

        resp = client.get("/agent/context", headers=headers)
        ctx = resp.json()

        from src.core.persistence.factory import get_driver
        agent_id = resp.json()["agent_id"]
        skill = get_driver().load_skill(agent_id)
        assert skill.context_snapshot["tone"] == ctx["tone"]
        assert skill.context_snapshot["language"] == ctx["language"]

    def test_skill_file_versions_exist_on_disk(self, client, tmp_path):
        from src.infrastructure.config import settings
        resp = client.post("/agent", json={
            "name": "File Bot", "owner": "acme",
            "context": {"tone": "formal", "tags": []},
        })
        agent_id = resp.json()["agent_id"]
        skills_dir = tmp_path / "agents" / agent_id / "skills"
        assert (skills_dir / "current.json").exists()
        assert (skills_dir / "v1.json").exists()


class TestParseContext:
    def test_returns_structured_context(self, client, mock_ai):
        import json
        from src.clients.ai_client import AIClient, AIResponse, AIUsage
        from unittest.mock import patch

        parsed_json = json.dumps({
            "tone": "formal",
            "language": "pt",
            "persona": "Assistente de suporte técnico",
            "restrictions": {"topics": ["concorrentes"]},
        })
        fake = AIResponse(content=parsed_json, usage=AIUsage(input_tokens=10, output_tokens=20, total_tokens=30))
        with patch.object(AIClient, "complete", return_value=fake):
            resp = client.post("/agent/parse-context", json={"text": "Sou formal, falo português, não falo de concorrentes."})

        assert resp.status_code == 200
        body = resp.json()
        assert body["context"]["tone"] == "formal"
        assert body["context"]["language"] == "pt"
        assert "concorrentes" in body["context"]["restrictions"]["topics"]

    def test_returns_422_on_invalid_ai_response(self, client):
        from src.clients.ai_client import AIClient, AIResponse, AIUsage
        from unittest.mock import patch

        fake = AIResponse(content="not json at all", usage=AIUsage(input_tokens=1, output_tokens=1, total_tokens=2))
        with patch.object(AIClient, "complete", return_value=fake):
            resp = client.post("/agent/parse-context", json={"text": "qualquer coisa"})
        assert resp.status_code == 422

    def test_empty_text_still_processes(self, client):
        from src.clients.ai_client import AIClient, AIResponse, AIUsage
        from unittest.mock import patch

        fake = AIResponse(content="{}", usage=AIUsage(input_tokens=1, output_tokens=1, total_tokens=2))
        with patch.object(AIClient, "complete", return_value=fake):
            resp = client.post("/agent/parse-context", json={"text": ""})
        assert resp.status_code == 200
        assert resp.json()["context"] is not None


class TestSqlTool:
    def _make_sqlite_tool(self, agent_id: str = "test-agent") -> "SqlTool":
        from src.core.tools.sql_tool import SqlTool
        from src.core.security import encrypt_secret
        conn = encrypt_secret("sqlite:///:memory:")
        return SqlTool(connection_string_enc=conn, agent_id=agent_id)

    def test_validate_connection_string_accepts_postgresql(self):
        from src.core.tools.sql_tool import validate_connection_string
        assert validate_connection_string("postgresql://user:pass@localhost/db") == "postgresql://user:pass@localhost/db"

    def test_validate_connection_string_rejects_unknown_dialect(self):
        from src.core.tools.sql_tool import validate_connection_string
        with pytest.raises(ValueError, match="não permitido"):
            validate_connection_string("mssql://user:pass@host/db")

    def test_validate_connection_string_rejects_no_scheme(self):
        from src.core.tools.sql_tool import validate_connection_string
        with pytest.raises(ValueError):
            validate_connection_string("not-a-url")

    def test_select_only_rejects_insert(self):
        from src.core.tools.sql_tool import _validate_sql
        with pytest.raises(ValueError, match="SELECT"):
            _validate_sql("INSERT INTO t VALUES (1)")

    def test_select_only_rejects_drop(self):
        from src.core.tools.sql_tool import _validate_sql
        with pytest.raises(ValueError):
            _validate_sql("DROP TABLE users")

    def test_select_only_rejects_multiple_statements(self):
        from src.core.tools.sql_tool import _validate_sql
        with pytest.raises(ValueError, match="Múltiplos"):
            _validate_sql("SELECT 1; DROP TABLE users")

    def test_select_passes_validation(self):
        from src.core.tools.sql_tool import _validate_sql
        assert _validate_sql("SELECT id, name FROM users") == "SELECT id, name FROM users"

    def test_execute_returns_results_from_sqlite(self, tmp_path):
        import os
        os.environ["DATA_PATH"] = str(tmp_path)

        from src.core.tools.sql_tool import SqlTool
        from src.core.security import encrypt_secret
        from sqlalchemy import create_engine, text as stext

        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(stext("CREATE TABLE produtos (id INTEGER, nome TEXT)"))
            conn.execute(stext("INSERT INTO produtos VALUES (1, 'Widget A')"))
        engine.dispose()

        tool = SqlTool(
            connection_string_enc=encrypt_secret(f"sqlite:///{db_path}"),
            agent_id="agent-x",
        )
        result = tool.execute("SELECT id, nome FROM produtos")
        assert "Widget A" in result
        assert "id" in result

    def test_execute_raises_value_error_on_invalid_sql(self, tmp_path):
        import os
        os.environ["DATA_PATH"] = str(tmp_path)

        from src.core.tools.sql_tool import SqlTool
        from src.core.security import encrypt_secret
        tool = SqlTool(
            connection_string_enc=encrypt_secret("sqlite:///:memory:"),
            agent_id="agent-x",
        )
        with pytest.raises(ValueError):
            tool.execute("DELETE FROM users")

    def test_audit_log_written_on_execute(self, tmp_path):
        import os
        os.environ["DATA_PATH"] = str(tmp_path)

        from src.core.tools.sql_tool import SqlTool
        from src.core.security import encrypt_secret
        from sqlalchemy import create_engine, text as stext

        db_path = tmp_path / "audit.db"
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(stext("CREATE TABLE t (x INTEGER)"))
        engine.dispose()

        tool = SqlTool(
            connection_string_enc=encrypt_secret(f"sqlite:///{db_path}"),
            agent_id="audit-agent",
        )
        tool.execute("SELECT x FROM t")

        audit_file = tmp_path / "agents" / "audit-agent" / "sql_audit.jsonl"
        assert audit_file.exists()
        import json
        entry = json.loads(audit_file.read_text().strip())
        assert entry["success"] is True
        assert "SELECT" in entry["sql"]


class TestSqlDatasource:
    def test_create_agent_with_sql_datasource(self, client):
        from src.core.security import encrypt_secret
        resp = client.post("/agent", json={
            "name": "SQL Bot",
            "owner": "acme",
            "context": {
                "sql_datasource": {
                    "connection_string": "sqlite:///:memory:",
                    "allowed_tables": [],
                    "max_rows": 20,
                },
                "tags": [],
            },
        })
        assert resp.status_code == 201

    def test_context_stores_sql_datasource_encrypted(self, client):
        resp = client.post("/agent", json={
            "name": "SQL Bot",
            "owner": "acme",
            "context": {
                "sql_datasource": {
                    "connection_string": "sqlite:///:memory:",
                    "allowed_tables": [],
                    "max_rows": 10,
                },
                "tags": [],
            },
        })
        api_key = resp.json()["api_key"]
        headers = {"Authorization": f"Bearer {api_key}"}
        ctx = client.get("/agent/context", headers=headers).json()
        # connection string deve estar criptografada em repouso
        assert ctx["sql_datasource"]["connection_string"].startswith("enc:")

    def test_validate_sql_rejects_unsupported_dialect(self, client):
        resp = client.post("/agent/validate-sql", json={"connection_string": "mssql://u:p@host/db"})
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
        assert "não permitido" in resp.json()["error"]

    def test_validate_sql_accepts_sqlite_memory(self, client):
        resp = client.post("/agent/validate-sql", json={"connection_string": "sqlite:///:memory:"})
        assert resp.status_code == 200
        assert resp.json()["valid"] is True
        assert resp.json()["dialect"] == "sqlite"

    def test_encrypt_secret_roundtrip(self):
        from src.core.security import encrypt_secret, decrypt_secret
        original = "postgresql://user:pass@localhost/db"
        enc = encrypt_secret(original)
        assert enc.startswith("enc:")
        assert decrypt_secret(enc) == original

    def test_encrypt_secret_idempotent(self):
        from src.core.security import encrypt_secret
        original = "sqlite:///:memory:"
        enc1 = encrypt_secret(original)
        enc2 = encrypt_secret(enc1)
        assert enc1 == enc2

    def test_mask_connection_string(self):
        from src.core.security import mask_connection_string
        conn = "postgresql://admin:secret123@db.example.com/mydb"
        masked = mask_connection_string(conn)
        assert "secret123" not in masked
        assert "***" in masked
        assert "admin" in masked
