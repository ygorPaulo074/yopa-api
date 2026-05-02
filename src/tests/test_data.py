"""
Testes de integração para os endpoints de dados e analytics:
  GET    /data/chat                                  — listagem de conversas
  GET    /data/chat/{session_id}                     — histórico completo de sessão
  DELETE /data/chat/{session_id}                     — remoção de sessão
  GET    /data/chat/{session_id}/insights/sentiment  — sentimento (local)
  GET    /data/chat/{session_id}/insights/topics     — tópicos (local)
  GET    /data/chat/{session_id}/insights/metrics    — métricas (local)
  GET    /data/analytics/summary                     — resumo analítico agregado
"""
import uuid
import pytest


def _send_and_end(client, headers, agent_id, session_id=None):
    """Envia mensagem e encerra sessão (persiste no driver)."""
    sid = session_id or str(uuid.uuid4())
    client.post("/chat", headers=headers, json={
        "session_id": sid,
        "user_id": "user_data_test",
        "message": "I need support with my order.",
    })
    client.post(f"/chat/{sid}/end", headers=headers)
    return sid


class TestDataChat:
    def test_list_chats_empty_initially(self, client, agent):
        _, _, headers = agent
        resp = client.get("/data/chat", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_chats_after_session_end(self, client, agent, mock_ai):
        _, _, headers = agent
        _send_and_end(client, headers, None)
        resp = client.get("/data/chat", headers=headers)
        assert resp.json()["total"] == 1

    def test_get_chat_detail(self, client, agent, mock_ai):
        agent_id, _, headers = agent
        sid = _send_and_end(client, headers, agent_id)
        resp = client.get(f"/data/chat/{sid}", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["session"]["session_id"] == sid
        assert len(body["conversation"]) == 2

    def test_get_chat_not_found(self, client, agent):
        _, _, headers = agent
        resp = client.get("/data/chat/nonexistent-id", headers=headers)
        assert resp.status_code == 404

    def test_delete_chat(self, client, agent, mock_ai):
        agent_id, _, headers = agent
        sid = _send_and_end(client, headers, agent_id)
        resp = client.delete(f"/data/chat/{sid}", headers=headers)
        assert resp.status_code == 204
        assert client.get(f"/data/chat/{sid}", headers=headers).status_code == 404


class TestInsights:
    def test_sentiment_insight(self, client, agent, mock_ai):
        agent_id, _, headers = agent
        sid = _send_and_end(client, headers, agent_id)
        resp = client.get(f"/data/chat/{sid}/insights/sentiment", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == sid
        assert "sentiment" in body
        assert body["sentiment"]["label"] in ("positive", "neutral", "negative")

    def test_topics_insight(self, client, agent, mock_ai):
        agent_id, _, headers = agent
        sid = _send_and_end(client, headers, agent_id)
        resp = client.get(f"/data/chat/{sid}/insights/topics", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "topics" in body
        assert "detected" in body["topics"]

    def test_metrics_insight(self, client, agent, mock_ai):
        agent_id, _, headers = agent
        sid = _send_and_end(client, headers, agent_id)
        resp = client.get(f"/data/chat/{sid}/insights/metrics", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["metrics"]["total_messages"] == 2
        assert body["metrics"]["resolution"] == "open"


class TestAnalytics:
    def test_summary_empty_with_no_sessions(self, client, agent):
        _, _, headers = agent
        resp = client.get("/data/analytics/summary", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["summary"]["total_chats"] == 0

    def test_summary_after_session(self, client, agent, mock_ai):
        agent_id, _, headers = agent
        _send_and_end(client, headers, agent_id)
        resp = client.get("/data/analytics/summary", headers=headers)
        assert resp.json()["summary"]["total_chats"] == 1

    def test_analytics_full_endpoint(self, client, agent, mock_ai):
        agent_id, _, headers = agent
        _send_and_end(client, headers, agent_id)
        resp = client.get("/data/analytics", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "summary" in body
        assert "patterns" in body
        assert "sentiment" in body
        assert "users" in body
        assert "timeline" in body
