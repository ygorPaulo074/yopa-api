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
