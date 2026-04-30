"""
Conexão e configuração com o modelo de IA via LiteLLM.
Abstrai o provedor (Anthropic, OpenAI, Gemini, DeepSeek, Groq), gerencia
API key, modelo e timeout. Expõe interface única de completion para o ai_service.
"""
import litellm
from typing import cast
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

    def complete(self, system: str, messages: list[HistoryMessage], max_tokens: int = 1024) -> AIResponse:
        response = cast(
            litellm.ModelResponse,
            litellm.completion(
                model=settings.AI_MODEL,
                api_key=settings.AI_API_KEY,
                messages=[
                    {"role": "system", "content": system},
                    *[{"role": m.role, "content": m.content} for m in messages],
                ],
                max_tokens=max_tokens,
                stream=False,
                timeout=settings.AI_TIMEOUT,
            ),
        )
        raw_usage = getattr(response, "usage", None)

        return AIResponse(
            content=response.choices[0].message.content or "",
            usage=AIUsage(
                input_tokens=raw_usage.prompt_tokens if raw_usage else 0,
                output_tokens=raw_usage.completion_tokens if raw_usage else 0,
                total_tokens=raw_usage.total_tokens if raw_usage else 0,
            ),
        )
