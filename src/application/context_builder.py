"""
Builds the agent system prompt from AgentContextBase.
Called on POST /agent and PUT /agent/context. The result is cached in Redis
and injected into every model call via chat_service.
escalation_trigger is backend logic — it never appears in the system prompt.
"""
from src.domain.agent import AgentContextBase


def build_system_prompt(context: AgentContextBase) -> str:
    parts: list[str] = []

    parts.append(context.persona if context.persona else "Você é um assistente virtual.")

    meta: list[str] = []
    if context.tone:
        meta.append(f"- Tom: {context.tone}")
    if context.language:
        meta.append(f"- Idioma: {context.language}")
    if context.segment:
        meta.append(f"- Segmento de atendimento: {context.segment}")
    if meta:
        parts.append("## Configurações\n" + "\n".join(meta))

    if context.behavior:
        parts.append(f"## Comportamento\n{context.behavior}")

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

    return "\n\n".join(parts)
