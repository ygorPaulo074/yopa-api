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


class TestB3RateLimiting:
    def test_chat_endpoint_accepts_request_parameter(self):
        """B3: send_message deve declarar request: Request para o LIMITER funcionar."""
        import inspect
        from src.routes.chat.index import send_message
        params = inspect.signature(send_message).parameters
        assert "request" in params

    def test_parse_context_endpoint_accepts_request_parameter(self):
        """B3: parse_context_from_text deve declarar request: Request para o LIMITER funcionar."""
        import inspect
        from src.routes.agent.index import parse_context_from_text
        params = inspect.signature(parse_context_from_text).parameters
        assert "request" in params

    def test_validate_sql_endpoint_accepts_request_parameter(self):
        """B3: validate_sql_connection deve declarar request: Request para o LIMITER funcionar."""
        import inspect
        from src.routes.agent.index import validate_sql_connection
        params = inspect.signature(validate_sql_connection).parameters
        assert "request" in params

    def test_rate_limit_exceeded_returns_429(self, client, agent, mock_ai):
        """B3: após exceder o limite, a rota deve retornar 429 com o formato correto."""
        from unittest.mock import Mock, patch
        from slowapi.errors import RateLimitExceeded
        from src.infrastructure.config import LIMITER

        _, _, headers = agent
        mock_limit = Mock()
        mock_limit.error_message = None
        with patch.object(LIMITER, "_check_request_limit", side_effect=RateLimitExceeded(mock_limit)):
            resp = client.post("/chat", headers=headers, json=CHAT_PAYLOAD)

        assert resp.status_code == 429
        body = resp.json()
        assert body["error"] == "rate_limit_exceeded"

    def test_rate_limit_config_values_are_set(self):
        """B3: os três limites devem estar configurados no settings."""
        from src.infrastructure.config import settings
        assert settings.RATE_LIMIT_CHAT
        assert settings.RATE_LIMIT_PARSE_CONTEXT
        assert settings.RATE_LIMIT_VALIDATE_SQL


class TestB4ToolUseMultiRound:
    """B4: AIClient.complete deve suportar múltiplas rodadas de tool calls."""

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
        """Caso base: uma rodada de tool call seguida de resposta final."""
        from unittest.mock import patch
        from src.clients.ai_client import AIClient
        from src.core.schemas import HistoryMessage

        tc = self._make_tool_call("get_info", '{"q": "test"}')
        first_resp = self._make_tool_response(tool_calls=[tc])
        final_resp = self._make_tool_response(content="Done.")

        calls = [first_resp, final_resp]
        executor_calls = []

        def executor(name, args):
            executor_calls.append((name, args))
            return "tool result"

        with patch("litellm.completion", side_effect=calls):
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
        """Dois rounds consecutivos de tool calls antes da resposta final."""
        from unittest.mock import patch
        from src.clients.ai_client import AIClient
        from src.core.schemas import HistoryMessage

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
        """Loop deve parar em MAX_TOOL_ROUNDS mesmo que a IA continue retornando tool_calls."""
        from unittest.mock import patch
        from src.clients.ai_client import AIClient, AIUsage
        from src.core.schemas import HistoryMessage
        from src.infrastructure.config import settings

        tc = self._make_tool_call("infinite", '{}')
        # looping_resp has no text content — simulates model that keeps calling tools
        looping_resp = self._make_tool_response(content="", tool_calls=[tc])
        # Provide more responses than MAX_TOOL_ROUNDS to verify guard
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

        # After MAX_TOOL_ROUNDS the loop stops — total calls = 1 initial + MAX_TOOL_ROUNDS
        assert mock_complete.call_count == 1 + settings.MAX_TOOL_ROUNDS
        assert result.content == ""

    def test_no_tool_executor_skips_loop(self):
        """Sem tool_executor, tool_calls são ignorados e resposta é retornada diretamente."""
        from unittest.mock import patch
        from src.clients.ai_client import AIClient
        from src.core.schemas import HistoryMessage

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
        """Tokens de todas as rodadas devem ser somados no AIUsage final."""
        from unittest.mock import patch
        from src.clients.ai_client import AIClient
        from src.core.schemas import HistoryMessage

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

        # Each mock response contributes prompt_tokens=10, completion_tokens=5
        assert result.usage.input_tokens == 20
        assert result.usage.output_tokens == 10
        assert result.usage.total_tokens == 30

    def test_max_tool_rounds_config_exists(self):
        """B4: MAX_TOOL_ROUNDS deve estar configurado em settings."""
        from src.infrastructure.config import settings
        assert settings.MAX_TOOL_ROUNDS >= 1


class TestEscalationDestination:
    """#8: escalation_destination — despacho automático e manual."""

    def _create_agent_with_destination(self, client, destination: dict) -> tuple:
        resp = client.post("/agent", json={
            "name": "Escalation Agent",
            "owner": "owner",
            "context": {
                "tone": "formal",
                "language": "pt",
                "persona": "Agente de teste",
                "tags": [],
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
        """Destino de escalação deve ser persistido no contexto do agente."""
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
        """POST /chat/{sid}/escalate deve chamar o webhook configurado."""
        from unittest.mock import patch as mock_patch
        _, headers = self._create_agent_with_destination(client, {
            "type": "webhook",
            "url": "https://hooks.example.com/escalation",
        })
        sid = str(uuid.uuid4())
        client.post("/chat", headers=headers, json={
            "session_id": sid, "user_id": "u1", "message": "hi",
        })

        with mock_patch("src.services.escalation_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            resp = client.post(f"/chat/{sid}/escalate", headers=headers)

        assert resp.status_code == 200
        assert mock_post.called
        call_payload = mock_post.call_args.kwargs["json"]
        assert call_payload["event"] == "escalation"
        assert call_payload["session_id"] == sid
        assert call_payload["reason"] == "manual"

    def test_automatic_escalate_dispatches_webhook(self, client, mock_ai, patch_env):
        """Escalação automática via keyword deve chamar o webhook."""
        from unittest.mock import patch as mock_patch
        _, headers = self._create_agent_with_destination(client, {
            "type": "webhook",
            "url": "https://hooks.example.com/auto",
        })
        sid = str(uuid.uuid4())

        with mock_patch("src.services.escalation_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            client.post("/chat", headers=headers, json={
                "session_id": sid, "user_id": "u1", "message": "escalate_now",
            })

        assert mock_post.called
        call_payload = mock_post.call_args.kwargs["json"]
        assert call_payload["reason"] == "automatic"
        assert call_payload["session_id"] == sid

    def test_webhook_not_called_twice_on_already_escalated(self, client, mock_ai, patch_env):
        """Webhook não deve ser disparado duas vezes se sessão já está escalada."""
        from unittest.mock import patch as mock_patch
        _, headers = self._create_agent_with_destination(client, {
            "type": "webhook",
            "url": "https://hooks.example.com/once",
        })
        sid = str(uuid.uuid4())
        # Primeira mensagem com keyword — dispara escalação
        with mock_patch("src.services.escalation_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            client.post("/chat", headers=headers, json={
                "session_id": sid, "user_id": "u1", "message": "escalate_now",
            })
            first_count = mock_post.call_count
            # Segunda mensagem com keyword — sessão já escalada, não dispara de novo
            client.post("/chat", headers=headers, json={
                "session_id": sid, "user_id": "u1", "message": "escalate_now",
            })
            second_count = mock_post.call_count

        assert first_count == 1
        assert second_count == 1  # não chamou novamente

    def test_none_destination_does_not_call_requests(self, client, mock_ai, patch_env):
        """Destino 'none' não deve fazer chamadas HTTP."""
        from unittest.mock import patch as mock_patch
        _, headers = self._create_agent_with_destination(client, {"type": "none"})
        sid = str(uuid.uuid4())

        with mock_patch("src.services.escalation_service.requests.post") as mock_post:
            client.post(f"/chat", headers=headers, json={
                "session_id": sid, "user_id": "u1", "message": "escalate_now",
            })
            client.post(f"/chat/{sid}/escalate", headers=headers)

        assert not mock_post.called

    def test_webhook_payload_contains_last_messages(self, client, mock_ai, patch_env):
        """Payload do webhook deve incluir as últimas mensagens da sessão."""
        from unittest.mock import patch as mock_patch
        _, headers = self._create_agent_with_destination(client, {
            "type": "webhook",
            "url": "https://hooks.example.com/payload",
        })
        sid = str(uuid.uuid4())
        # Cria a sessão antes de escalar
        client.post("/chat", headers=headers, json={
            "session_id": sid, "user_id": "u1", "message": "hi",
        })

        with mock_patch("src.services.escalation_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            client.post(f"/chat/{sid}/escalate", headers=headers)

        assert mock_post.called
        payload = mock_post.call_args.kwargs["json"]
        assert "last_messages" in payload
        assert "agent_id" in payload
        assert "triggered_at" in payload
