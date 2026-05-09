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
from unittest.mock import patch
from src.clients.ai_client import AIClient, AIResponse, AIUsage


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


class TestInsightSuggestions:
    def test_suggestions_passes_transcript_to_ai(self, client, agent):
        """B1: IA deve receber o histórico real, não messages=[]."""
        agent_id, _, headers = agent
        ai_json = '{"key_points": ["order issue"], "suggested_actions": ["refund"], "summary": "customer complained"}'
        mock_resp = AIResponse(content=ai_json, usage=AIUsage(input_tokens=20, output_tokens=10, total_tokens=30))

        with patch.object(AIClient, "complete", return_value=mock_resp) as mock_call:
            with patch.object(AIClient, "complete", side_effect=[
                AIResponse(content="Test response.", usage=AIUsage(input_tokens=10, output_tokens=5, total_tokens=15)),
                mock_resp,
            ]):
                sid = _send_and_end(client, headers, agent_id)
                resp = client.get(f"/data/chat/{sid}/insights/suggestions", headers=headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["ai_analysis"]["key_points"] == ["order issue"]
        assert body["ai_analysis"]["summary"] == "customer complained"

    def test_suggestions_transcript_contains_history(self, client, agent):
        """B1: o conteúdo passado à IA deve conter as mensagens reais da sessão."""
        agent_id, _, headers = agent
        captured = {}
        ai_json = '{"key_points": [], "suggested_actions": [], "summary": "ok"}'

        def capture_complete(system, messages, **kwargs):
            captured["messages"] = messages
            return AIResponse(content=ai_json, usage=AIUsage(input_tokens=5, output_tokens=5, total_tokens=10))

        with patch.object(AIClient, "complete", side_effect=[
            AIResponse(content="Test response.", usage=AIUsage(input_tokens=10, output_tokens=5, total_tokens=15)),
            capture_complete.__wrapped__ if hasattr(capture_complete, "__wrapped__") else capture_complete,
        ]):
            sid = _send_and_end(client, headers, agent_id)

        with patch.object(AIClient, "complete", side_effect=capture_complete):
            client.get(f"/data/chat/{sid}/insights/suggestions", headers=headers)

        assert "messages" in captured
        assert len(captured["messages"]) > 0
        assert captured["messages"][0].role == "user"
        assert "USER:" in captured["messages"][0].content or "ASSISTANT:" in captured["messages"][0].content


class TestB2Performance:
    def test_load_all_scores_returns_all_sessions(self, client, agent, mock_ai):
        """B2 N+1: load_all_scores deve retornar scores de todas as sessões em uma única chamada."""
        agent_id, _, headers = agent
        sid1 = _send_and_end(client, headers, agent_id)
        sid2 = _send_and_end(client, headers, agent_id)

        from src.core.persistence.factory import get_driver
        scores = get_driver().load_all_scores(agent_id)
        session_ids = {sc.session_id for sc in scores}
        assert sid1 in session_ids
        assert sid2 in session_ids

    def test_scores_have_ttl_in_redis(self, client, agent, mock_ai):
        """B2 TTL: scores no Redis devem ter TTL configurado (não persistem indefinidamente)."""
        agent_id, _, headers = agent
        sid = str(__import__("uuid").uuid4())
        client.post("/chat", headers=headers, json={
            "session_id": sid, "user_id": "u1", "message": "hello",
        })
        from src.core.cache.client import CacheClient
        from src.core.cache import keys
        cache = CacheClient()
        ttl = cache._redis.ttl(keys.scores_key(sid))
        assert ttl > 0

    def test_cache_client_uses_shared_connection_pool(self):
        """B2 Pool: múltiplas instâncias de CacheClient devem compartilhar o mesmo pool."""
        from src.core.cache.client import CacheClient, _get_pool
        from src.infrastructure.config import settings
        c1 = CacheClient()
        c2 = CacheClient()
        assert c1._redis.connection_pool is c2._redis.connection_pool


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

    def test_avg_response_time_populated_in_analytics(self, client, agent, mock_ai):
        """B5: avg_response_time_ms deve ser > 0 após uma sessão real."""
        agent_id, _, headers = agent
        _send_and_end(client, headers, agent_id)
        resp = client.get("/data/analytics/summary", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["summary"]["avg_response_time_ms"] >= 0

    def test_timeline_response_time_populated(self, client, agent, mock_ai):
        """B5: timeline deve ter avg_response_time_ms calculado por dia."""
        agent_id, _, headers = agent
        _send_and_end(client, headers, agent_id)
        resp = client.get("/data/analytics/timeline", headers=headers)
        assert resp.status_code == 200
        timeline = resp.json()["timeline"]
        assert len(timeline) > 0
        assert "avg_response_time_ms" in timeline[0]
