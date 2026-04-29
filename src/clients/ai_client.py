"""
Conexão e configuração com o modelo de IA via LiteLLM.
Abstrai o provedor (Anthropic, OpenAI, Gemini, DeepSeek, Groq), gerencia
API key, modelo e timeout. Expõe interface única de completion para o ai_service.
"""
import litellm
from typing import Any, cast
from src.infrastructure.config import settings
from pydantic import BaseModel


class AIResponse(BaseModel):
    content: str
    usage: dict


class AIClient:

    def complete(self, system: str, messages: list[dict], max_tokens: int = 1024) -> AIResponse:
        response = litellm.completion(
            model=settings.AI_MODEL,
            api_key=settings.AI_API_KEY,
            messages=[{"role": "system", "content": system}, *messages],
            max_tokens=max_tokens,
            stream=False,
            timeout=settings.AI_TIMEOUT,
        )
        usage = getattr(response, "usage", None)

        response = cast(litellm.ModelResponse, response)
        return AIResponse(
            content=response.choices[0].message.content or "",
            usage={
            "input": usage.prompt_tokens if usage else 0,
            "output": usage.completion_tokens if usage else 0,
            "total": usage.total_tokens if usage else 0,
            },
        )
