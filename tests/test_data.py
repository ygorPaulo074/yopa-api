"""
Integration tests for data and analytics endpoints:
  GET    /data/chat                                  — conversation listing
  GET    /data/chat/{session_id}                     — full session history
  DELETE /data/chat/{session_id}                     — session removal
  GET    /data/chat/{session_id}/insights/sentiment  — local NLP sentiment
  GET    /data/chat/{session_id}/insights/topics     — local NLP topics
  GET    /data/chat/{session_id}/insights/metrics    — session metrics
  GET    /data/analytics/summary                     — aggregated analytics summary
Covers: insights Redis→driver fallback (R1-8), analytics segments (R1-9).
"""
import uuid
import pytest
from unittest.mock import patch
from src.infrastructure.ai.client import AIClient, AIResponse, AIUsage


def _send_and_end(client, headers, agent_id, session_id=None):
    """Sends a message and ends the session (persists to driver)."""
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

    def test_insights_fallback_to_driver_when_redis_empty(self, client, agent, mock_ai):
        """R1-8: insights endpoint falls back to driver when Redis has no scores."""
        agent_id, _, headers = agent
        sid = _send_and_end(client, headers, agent_id)

        # Evict scores from Redis to force driver fallback
        from src.infrastructure.cache.redis_client import CacheClient
        cache = CacheClient()
        cache._redis.delete(f"session:{sid}:scores")

        resp = client.get(f"/data/chat/{sid}/insights/sentiment", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["session_id"] == sid


class TestInsightSuggestions:
    def test_suggestions_passes_transcript_to_ai(self, client, agent):
        """AI must receive the real history, not messages=[]."""
        import json
        agent_id, _, headers = agent
        ai_json = json.dumps({
            "key_points": ["order issue"],
            "suggested_actions": ["refund"],
            "summary": "customer complained",
        })
        mock_resp = AIResponse(content=ai_json, usage=AIUsage(input_tokens=20, output_tokens=10, total_tokens=30))

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
        """The content passed to AI must contain the real session messages."""
        import json
        agent_id, _, headers = agent
        captured = {}
        ai_json = json.dumps({"key_points": [], "suggested_actions": [], "summary": "ok"})

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


class TestPerformance:
    def test_load_all_scores_returns_all_sessions(self, client, agent, mock_ai):
        """load_all_scores must return scores for all sessions in a single call."""
        agent_id, _, headers = agent
        sid1 = _send_and_end(client, headers, agent_id)
        sid2 = _send_and_end(client, headers, agent_id)

        from src.infrastructure.persistence.factory import get_driver
        scores = get_driver().load_all_scores(agent_id)
        session_ids = {sc.session_id for sc in scores}
        assert sid1 in session_ids
        assert sid2 in session_ids

    def test_scores_have_ttl_in_redis(self, client, agent, mock_ai):
        """Scores stored in Redis must have a TTL (not persistent indefinitely)."""
        _, _, headers = agent
        sid = str(uuid.uuid4())
        client.post("/chat", headers=headers, json={
            "session_id": sid, "user_id": "u1", "message": "hello",
        })
        from src.infrastructure.cache.redis_client import CacheClient
        cache = CacheClient()
        ttl = cache._redis.ttl(f"session:{sid}:scores")
        assert ttl > 0


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
        agent_id, _, headers = agent
        _send_and_end(client, headers, agent_id)
        resp = client.get("/data/analytics/summary", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["summary"]["avg_response_time_ms"] >= 0

    def test_timeline_response_time_populated(self, client, agent, mock_ai):
        agent_id, _, headers = agent
        _send_and_end(client, headers, agent_id)
        resp = client.get("/data/analytics/timeline", headers=headers)
        assert resp.status_code == 200
        timeline = resp.json()["timeline"]
        assert len(timeline) > 0
        assert "avg_response_time_ms" in timeline[0]

    def test_segments_populated_from_user_context(self, client, mock_ai):
        """R1-9: analytics segments must be extracted from UserContext, not always []."""
        # Create an agent with a segment in its context
        resp = client.post("/agent", json={
            "name": "Segment Agent",
            "owner": "owner",
            "context": {"segment": "premium"},
        })
        assert resp.status_code == 201
        data = resp.json()
        agent_id = data["agent_id"]
        headers = {"Authorization": f"Bearer {data['api_key']}"}

        # Send and end a session with a user_id — _update_user_context will pick up the
        # segment from the agent context and store it in UserContextRecord
        sid = str(uuid.uuid4())
        client.post("/chat", headers=headers, json={
            "session_id": sid, "user_id": "premium_user_1", "message": "hello",
        })
        client.post(f"/chat/{sid}/end", headers=headers)

        resp = client.get("/data/analytics/users", headers=headers)
        assert resp.status_code == 200
        segments = resp.json().get("users", {}).get("segments", [])
        segment_names = [s["segment"] for s in segments]
        assert "premium" in segment_names
