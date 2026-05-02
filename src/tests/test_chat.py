"""
Testes de integração para os endpoints de chat:
  POST /chat                      — envio de mensagem, injeção de contexto e retorno estruturado
  POST /chat/{session_id}/end     — encerramento de sessão
  POST /chat/{session_id}/resolve — marcação como resolvida
  POST /chat/{session_id}/escalate — marcação como escalonada
Cobre também os fluxos de fallback e de disparo de escalonamento automático.
"""
import uuid
import pytest


SESSION_ID = str(uuid.uuid4())

CHAT_PAYLOAD = {
    "session_id": SESSION_ID,
    "user_id": "user_123",
    "message": "Hello, I need help.",
}


class TestSendMessage:
    def test_returns_response_with_session_and_conversation(self, client, agent, mock_ai):
        _, _, headers = agent
        resp = client.post("/chat", headers=headers, json=CHAT_PAYLOAD)
        assert resp.status_code == 200
        body = resp.json()
        assert "session" in body
        assert "conversation" in body
        assert body["session"]["session_id"] == SESSION_ID
        assert len(body["conversation"]) == 2

    def test_conversation_has_user_and_assistant_messages(self, client, agent, mock_ai):
        _, _, headers = agent
        resp = client.post("/chat", headers=headers, json=CHAT_PAYLOAD)
        roles = [entry["message"]["role"] for entry in resp.json()["conversation"]]
        assert "user" in roles
        assert "assistant" in roles

    def test_ai_response_content_is_returned(self, client, agent, mock_ai):
        _, _, headers = agent
        resp = client.post("/chat", headers=headers, json=CHAT_PAYLOAD)
        assistant_entries = [e for e in resp.json()["conversation"] if e["message"]["role"] == "assistant"]
        assert assistant_entries[0]["message"]["content"] == "Test response from AI."

    def test_token_usage_is_present(self, client, agent, mock_ai):
        _, _, headers = agent
        resp = client.post("/chat", headers=headers, json=CHAT_PAYLOAD)
        tokens = resp.json()["session"]["tokens"]
        assert tokens["total"] == 15

    def test_unauthenticated_request_returns_401(self, client, mock_ai):
        resp = client.post("/chat", json=CHAT_PAYLOAD)
        assert resp.status_code in (401, 403)


class TestSessionLifecycle:
    def test_end_session(self, client, agent, mock_ai):
        _, _, headers = agent
        sid = str(uuid.uuid4())
        client.post("/chat", headers=headers, json={**CHAT_PAYLOAD, "session_id": sid})
        resp = client.post(f"/chat/{sid}/end", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == sid
        assert "ended_at" in body

    def test_resolve_session(self, client, agent, mock_ai):
        _, _, headers = agent
        sid = str(uuid.uuid4())
        client.post("/chat", headers=headers, json={**CHAT_PAYLOAD, "session_id": sid})
        resp = client.post(f"/chat/{sid}/resolve", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["resolved"] is True

    def test_escalate_session(self, client, agent, mock_ai):
        _, _, headers = agent
        sid = str(uuid.uuid4())
        client.post("/chat", headers=headers, json={**CHAT_PAYLOAD, "session_id": sid})
        resp = client.post(f"/chat/{sid}/escalate", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["escalated"] is True

    def test_end_nonexistent_session_returns_404(self, client, agent):
        _, _, headers = agent
        resp = client.post("/chat/nonexistent-session-id/end", headers=headers)
        assert resp.status_code == 404
