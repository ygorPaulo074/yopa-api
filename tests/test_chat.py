"""
Integration tests for chat endpoints:
  POST /chat                      — send message, context injection, structured response
  POST /chat/{session_id}/end     — session end
  POST /chat/{session_id}/resolve — resolve session
  POST /chat/{session_id}/escalate — escalate session
Covers: X-Allowed-Models enforcement (R1-14), HMAC signing (R1-12),
        escalation auto/manual dispatch, multi-round tool use.
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

    def test_session_id_generated_when_omitted(self, client, agent, mock_ai):
        """Server generates session_id if not supplied."""
        _, _, headers = agent
        resp = client.post("/chat", headers=headers, json={"user_id": "u1", "message": "hi"})
        assert resp.status_code == 200
        assert resp.json()["session"]["session_id"]


class TestAllowedModels:
    """R1-14: X-Allowed-Models header enforcement by proxy."""

    def test_allowed_model_passes(self, client, agent, mock_ai, monkeypatch):
        _, _, headers = agent
        from src.infrastructure.config import settings
        monkeypatch.setattr(settings, "AI_MODEL", "gpt-4o")
        auth_headers = {**headers, "X-Allowed-Models": "gpt-4o,gpt-3.5-turbo"}
        resp = client.post("/chat", headers=auth_headers, json=CHAT_PAYLOAD)
        assert resp.status_code == 200

    def test_disallowed_model_returns_403(self, client, agent, mock_ai, monkeypatch):
        _, _, headers = agent
        from src.infrastructure.config import settings
        monkeypatch.setattr(settings, "AI_MODEL", "gpt-4o")
        auth_headers = {**headers, "X-Allowed-Models": "claude-3-opus"}
        resp = client.post("/chat", headers=auth_headers, json={**CHAT_PAYLOAD, "session_id": str(uuid.uuid4())})
        assert resp.status_code == 403

    def test_empty_allowed_models_header_does_not_block(self, client, agent, mock_ai):
        """Empty header value is treated as no restriction."""
        _, _, headers = agent
        auth_headers = {**headers, "X-Allowed-Models": ""}
        resp = client.post("/chat", headers=auth_headers, json={**CHAT_PAYLOAD, "session_id": str(uuid.uuid4())})
        assert resp.status_code == 200


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


class TestToolUseMultiRound:
    def _make_tool_response(self, content="Final answer.", tool_calls=None):
        from unittest.mock import Mock
        msg = Mock()
        msg.content = content
        msg.tool_calls = tool_calls
        choice = Mock()
        choice.message = msg
        response = Mock()
        response.choices = [choice]
        usage = Mock()
        usage.prompt_tokens = 10
        usage.completion_tokens = 5
        response.usage = usage
        if tool_calls:
            msg.model_dump = lambda exclude_none=False: {
                "role": "assistant",
                "tool_calls": [
                    {"id": tc.id, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            }
        return response

    def _make_tool_call(self, name, arguments, call_id="tc_1"):
        from unittest.mock import Mock
        tc = Mock()
        tc.id = call_id
        tc.function.name = name
        tc.function.arguments = arguments
        return tc

    def test_single_tool_round_resolves(self):
        from unittest.mock import patch
        from src.infrastructure.ai.client import AIClient
        from src.domain.conversation import HistoryMessage

        tc = self._make_tool_call("get_info", '{"q": "test"}')
        first_resp = self._make_tool_response(tool_calls=[tc])
        final_resp = self._make_tool_response(content="Done.")

        executor_calls = []

        def executor(name, args):
            executor_calls.append((name, args))
            return "tool result"

        with patch("litellm.completion", side_effect=[first_resp, final_resp]):
            result = AIClient().complete(
                system="sys",
                messages=[HistoryMessage(
                    message_id="1", session_id="s", role="user",
                    content="hi", timestamp="", status="delivered",
                )],
                tools=[{"type": "function", "function": {"name": "get_info"}}],
                tool_executor=executor,
            )

        assert result.content == "Done."
        assert len(executor_calls) == 1
        assert executor_calls[0][0] == "get_info"

    def test_two_consecutive_tool_rounds(self):
        from unittest.mock import patch
        from src.infrastructure.ai.client import AIClient
        from src.domain.conversation import HistoryMessage

        tc1 = self._make_tool_call("step_one", '{}', call_id="tc_1")
        tc2 = self._make_tool_call("step_two", '{}', call_id="tc_2")
        first_resp = self._make_tool_response(tool_calls=[tc1])
        second_resp = self._make_tool_response(tool_calls=[tc2])
        final_resp = self._make_tool_response(content="All done.")

        executor_calls = []

        def executor(name, args):
            executor_calls.append(name)
            return "ok"

        with patch("litellm.completion", side_effect=[first_resp, second_resp, final_resp]):
            result = AIClient().complete(
                system="sys",
                messages=[HistoryMessage(
                    message_id="1", session_id="s", role="user",
                    content="hi", timestamp="", status="delivered",
                )],
                tools=[],
                tool_executor=executor,
            )

        assert result.content == "All done."
        assert executor_calls == ["step_one", "step_two"]

    def test_max_tool_rounds_guard_stops_loop(self):
        from unittest.mock import patch
        from src.infrastructure.ai.client import AIClient
        from src.domain.conversation import HistoryMessage
        from src.infrastructure.config import settings

        tc = self._make_tool_call("infinite", '{}')
        looping_resp = self._make_tool_response(content="", tool_calls=[tc])
        responses = [looping_resp] * (settings.MAX_TOOL_ROUNDS + 2)

        with patch("litellm.completion", side_effect=responses) as mock_complete:
            result = AIClient().complete(
                system="sys",
                messages=[HistoryMessage(
                    message_id="1", session_id="s", role="user",
                    content="hi", timestamp="", status="delivered",
                )],
                tools=[{"type": "function", "function": {"name": "infinite"}}],
                tool_executor=lambda name, args: "result",
            )

        assert mock_complete.call_count == 1 + settings.MAX_TOOL_ROUNDS
        assert result.content == ""

    def test_no_tool_executor_skips_loop(self):
        from unittest.mock import patch
        from src.infrastructure.ai.client import AIClient
        from src.domain.conversation import HistoryMessage

        tc = self._make_tool_call("should_not_run", '{}')
        resp = self._make_tool_response(content="Direct.", tool_calls=[tc])

        with patch("litellm.completion", return_value=resp) as mock_complete:
            result = AIClient().complete(
                system="sys",
                messages=[HistoryMessage(
                    message_id="1", session_id="s", role="user",
                    content="hi", timestamp="", status="delivered",
                )],
                tools=[],
                tool_executor=None,
            )

        assert result.content == "Direct."
        assert mock_complete.call_count == 1

    def test_token_usage_accumulates_across_rounds(self):
        from unittest.mock import patch
        from src.infrastructure.ai.client import AIClient
        from src.domain.conversation import HistoryMessage

        tc = self._make_tool_call("calc", '{}')
        first_resp = self._make_tool_response(tool_calls=[tc])
        final_resp = self._make_tool_response(content="Result.")

        with patch("litellm.completion", side_effect=[first_resp, final_resp]):
            result = AIClient().complete(
                system="sys",
                messages=[HistoryMessage(
                    message_id="1", session_id="s", role="user",
                    content="hi", timestamp="", status="delivered",
                )],
                tools=[],
                tool_executor=lambda n, a: "42",
            )

        assert result.usage.input_tokens == 20
        assert result.usage.output_tokens == 10
        assert result.usage.total_tokens == 30

    def test_max_tool_rounds_config_exists(self):
        from src.infrastructure.config import settings
        assert settings.MAX_TOOL_ROUNDS >= 1


class TestEscalationDestination:
    def _create_agent_with_destination(self, client, destination: dict) -> tuple:
        resp = client.post("/agent", json={
            "name": "Escalation Agent",
            "owner": "owner",
            "context": {
                "tone": "formal",
                "language": "pt",
                "persona": "Agente de teste",
                "escalation_trigger": {
                    "operator": "OR",
                    "conditions": [{"type": "keyword", "values": ["escalate_now"]}],
                },
                "escalation_destination": destination,
            },
        })
        assert resp.status_code == 201
        data = resp.json()
        headers = {"Authorization": f"Bearer {data['api_key']}"}
        return data["agent_id"], headers

    def test_destination_persisted_on_create(self, client, patch_env):
        _, headers = self._create_agent_with_destination(client, {
            "type": "webhook",
            "url": "https://example.com/hook",
            "token": "secret",
        })
        resp = client.get("/agent/context", headers=headers)
        assert resp.status_code == 200
        dest = resp.json().get("escalation_destination")
        assert dest is not None
        assert dest["type"] == "webhook"
        assert dest["url"] == "https://example.com/hook"

    def test_manual_escalate_dispatches_webhook(self, client, mock_ai, patch_env):
        from unittest.mock import patch as mock_patch
        _, headers = self._create_agent_with_destination(client, {
            "type": "webhook",
            "url": "https://hooks.example.com/escalation",
        })
        sid = str(uuid.uuid4())
        client.post("/chat", headers=headers, json={
            "session_id": sid, "user_id": "u1", "message": "hi",
        })

        with mock_patch("src.application.services.escalation_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            resp = client.post(f"/chat/{sid}/escalate", headers=headers)

        assert resp.status_code == 200
        assert mock_post.called
        call_kwargs = mock_post.call_args
        import json
        payload = json.loads(call_kwargs.kwargs.get("data", b"{}"))
        assert payload["event"] == "escalation"
        assert payload["session_id"] == sid
        assert payload["reason"] == "manual"

    def test_automatic_escalate_dispatches_webhook(self, client, mock_ai, patch_env):
        from unittest.mock import patch as mock_patch
        _, headers = self._create_agent_with_destination(client, {
            "type": "webhook",
            "url": "https://hooks.example.com/auto",
        })
        sid = str(uuid.uuid4())

        with mock_patch("src.application.services.escalation_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            client.post("/chat", headers=headers, json={
                "session_id": sid, "user_id": "u1", "message": "escalate_now",
            })

        assert mock_post.called
        import json
        payload = json.loads(mock_post.call_args.kwargs.get("data", b"{}"))
        assert payload["reason"] == "automatic"
        assert payload["session_id"] == sid

    def test_webhook_not_called_twice_on_already_escalated(self, client, mock_ai, patch_env):
        from unittest.mock import patch as mock_patch
        _, headers = self._create_agent_with_destination(client, {
            "type": "webhook",
            "url": "https://hooks.example.com/once",
        })
        sid = str(uuid.uuid4())
        with mock_patch("src.application.services.escalation_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            client.post("/chat", headers=headers, json={
                "session_id": sid, "user_id": "u1", "message": "escalate_now",
            })
            first_count = mock_post.call_count
            client.post("/chat", headers=headers, json={
                "session_id": sid, "user_id": "u1", "message": "escalate_now",
            })
            second_count = mock_post.call_count

        assert first_count == 1
        assert second_count == 1

    def test_none_destination_does_not_call_requests(self, client, mock_ai, patch_env):
        from unittest.mock import patch as mock_patch
        _, headers = self._create_agent_with_destination(client, {"type": "none"})
        sid = str(uuid.uuid4())

        with mock_patch("src.application.services.escalation_service.requests.post") as mock_post:
            client.post("/chat", headers=headers, json={
                "session_id": sid, "user_id": "u1", "message": "escalate_now",
            })
            client.post(f"/chat/{sid}/escalate", headers=headers)

        assert not mock_post.called

    def test_webhook_payload_contains_last_messages(self, client, mock_ai, patch_env):
        from unittest.mock import patch as mock_patch
        _, headers = self._create_agent_with_destination(client, {
            "type": "webhook",
            "url": "https://hooks.example.com/payload",
        })
        sid = str(uuid.uuid4())
        client.post("/chat", headers=headers, json={
            "session_id": sid, "user_id": "u1", "message": "hi",
        })

        with mock_patch("src.application.services.escalation_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            client.post(f"/chat/{sid}/escalate", headers=headers)

        assert mock_post.called
        import json
        payload = json.loads(mock_post.call_args.kwargs.get("data", b"{}"))
        assert "last_messages" in payload
        assert "agent_id" in payload
        assert "triggered_at" in payload


class TestHmacSigning:
    """R1-12: HMAC-SHA256 signature on escalation webhook payloads."""

    def test_webhook_includes_signature_when_token_set(self, client, mock_ai, monkeypatch):
        from unittest.mock import patch as mock_patch
        from src.infrastructure.config import settings

        monkeypatch.setattr(settings, "INTERNAL_TOKEN", "test-secret-token")

        resp = client.post("/agent", json={
            "name": "HMAC Agent",
            "owner": "owner",
            "context": {
                "escalation_destination": {
                    "type": "webhook",
                    "url": "https://hooks.example.com/hmac",
                },
            },
        })
        assert resp.status_code == 201
        data = resp.json()
        headers = {"Authorization": f"Bearer {data['api_key']}"}
        sid = str(uuid.uuid4())
        client.post("/chat", headers=headers, json={"session_id": sid, "user_id": "u1", "message": "hi"})

        with mock_patch("src.application.services.escalation_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            client.post(f"/chat/{sid}/escalate", headers=headers)

        assert mock_post.called
        call_headers = mock_post.call_args.kwargs["headers"]
        assert "X-Yopa-Signature" in call_headers
        assert call_headers["X-Yopa-Signature"].startswith("sha256=")

    def test_signature_is_valid_hmac(self, client, mock_ai, monkeypatch):
        import hmac
        import hashlib
        import json
        from unittest.mock import patch as mock_patch
        from src.infrastructure.config import settings

        secret = "verify-me-token"
        monkeypatch.setattr(settings, "INTERNAL_TOKEN", secret)

        resp = client.post("/agent", json={
            "name": "HMAC Verify",
            "owner": "owner",
            "context": {
                "escalation_destination": {
                    "type": "webhook",
                    "url": "https://hooks.example.com/verify",
                },
            },
        })
        headers = {"Authorization": f"Bearer {resp.json()['api_key']}"}
        sid = str(uuid.uuid4())
        client.post("/chat", headers=headers, json={"session_id": sid, "user_id": "u1", "message": "hi"})

        with mock_patch("src.application.services.escalation_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            client.post(f"/chat/{sid}/escalate", headers=headers)

        raw_body = mock_post.call_args.kwargs["data"]
        received_sig = mock_post.call_args.kwargs["headers"]["X-Yopa-Signature"]
        expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        assert received_sig == expected

    def test_no_signature_when_token_empty(self, client, mock_ai, monkeypatch):
        from unittest.mock import patch as mock_patch
        from src.infrastructure.config import settings

        monkeypatch.setattr(settings, "INTERNAL_TOKEN", "")

        resp = client.post("/agent", json={
            "name": "No HMAC",
            "owner": "owner",
            "context": {
                "escalation_destination": {
                    "type": "webhook",
                    "url": "https://hooks.example.com/no-hmac",
                },
            },
        })
        headers = {"Authorization": f"Bearer {resp.json()['api_key']}"}
        sid = str(uuid.uuid4())
        client.post("/chat", headers=headers, json={"session_id": sid, "user_id": "u1", "message": "hi"})

        with mock_patch("src.application.services.escalation_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            client.post(f"/chat/{sid}/escalate", headers=headers)

        call_headers = mock_post.call_args.kwargs["headers"]
        assert "X-Yopa-Signature" not in call_headers
