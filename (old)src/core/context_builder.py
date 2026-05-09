"""
Constrói o system prompt do agente a partir do AgentContext.
Chamado no POST /agent e no PUT /agent/context. O resultado é cacheado no Redis
e injetado em cada chamada ao modelo via ai_service.

escalation_trigger é lógica de backend — nunca vai para o system prompt.
"""
from src.routes.base_schemas import AgentContext


def build_system_prompt(context: AgentContext) -> str:
    parts: list[str] = []

    # Identidade
    parts.append(context.persona if context.persona else "Você é um assistente virtual.")

    # Configurações de tom, idioma e segmento
    meta: list[str] = []
    if context.tone:
        meta.append(f"- Tom: {context.tone}")
    if context.language:
        meta.append(f"- Idioma: {context.language}")
    if context.segment:
        meta.append(f"- Segmento de atendimento: {context.segment}")
    if meta:
        parts.append("## Configurações\n" + "\n".join(meta))

    # Diretrizes de comportamento
    if context.behavior:
        parts.append(f"## Comportamento\n{context.behavior}")

    # Restrições — tópicos proibidos como proibições explícitas
    if context.restrictions and context.restrictions.topics:
        topics = "\n".join(f"- {t}" for t in context.restrictions.topics)
        block = f"## Restrições\nVocê está PROIBIDO de responder sobre os seguintes tópicos:\n{topics}"
        if context.fallback_message:
            block += (
                f'\n\nQuando o usuário perguntar sobre um tópico proibido, responda EXATAMENTE com:\n'
                f'"{context.fallback_message}"'
            )
        parts.append(block)
    elif context.fallback_message:
        parts.append(
            f'## Mensagem padrão\nQuando não souber responder ou o tema estiver fora do seu escopo, '
            f'use exatamente:\n"{context.fallback_message}"'
        )

    # knowledge_base é tratado via tool use (a implementar) — não vai para o system prompt

    return "\n\n".join(parts)
