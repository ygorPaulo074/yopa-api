"""
Conexão e configuração com o modelo de IA via LiteLLM.
Abstrai o provedor (Anthropic, OpenAI, Gemini, DeepSeek, Groq), gerencia
API key, modelo e timeout. Expõe interface única de completion para o ai_service.
Suporta tool use: executa loop de chamadas até o modelo retornar resposta sem
tool_calls ou atingir MAX_TOOL_ROUNDS (configurável em settings).
"""
import json
import litellm
from typing import Callable
from pydantic import BaseModel
from src.infrastructure.config import settings
from src.core.schemas import HistoryMessage


class AIUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class AIResponse(BaseModel):
    content: str
    usage: AIUsage


class AIClient:

    def complete(
        self,
        system: str,
        messages: list[HistoryMessage],
        tools: list[dict] | None = None,
        tool_executor: Callable[[str, str], str] | None = None,
        max_tokens: int = 1024,
    ) -> AIResponse:
        litellm_messages = [
            {"role": "system", "content": system},
            *[{"role": m.role, "content": m.content} for m in messages],
        ]
        total_input = 0
        total_output = 0

        kwargs = dict(
            model=settings.AI_MODEL,
            api_key=settings.AI_API_KEY,
            messages=litellm_messages,
            max_tokens=max_tokens,
            stream=False,
            timeout=settings.AI_TIMEOUT,
        )
        if tools:
            kwargs["tools"] = tools

        response = litellm.completion(**kwargs)
        raw_usage = getattr(response, "usage", None)
        total_input += raw_usage.prompt_tokens if raw_usage else 0
        total_output += raw_usage.completion_tokens if raw_usage else 0

        rounds = 0
        while rounds < settings.MAX_TOOL_ROUNDS:
            tool_calls = getattr(response.choices[0].message, "tool_calls", None)
            if not tool_calls or not tool_executor:
                break
            rounds += 1
            litellm_messages.append(response.choices[0].message.model_dump(exclude_none=True))
            for tc in tool_calls:
                args = json.loads(tc.function.arguments)
                result = tool_executor(tc.function.name, json.dumps(args))
                litellm_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
            kwargs["messages"] = litellm_messages
            response = litellm.completion(**kwargs)
            raw_usage = getattr(response, "usage", None)
            total_input += raw_usage.prompt_tokens if raw_usage else 0
            total_output += raw_usage.completion_tokens if raw_usage else 0

        return AIResponse(
            content=response.choices[0].message.content or "",
            usage=AIUsage(
                input_tokens=total_input,
                output_tokens=total_output,
                total_tokens=total_input + total_output,
            ),
        )
