"""
Testes de integração para os endpoints de chat:
  POST /chat                      — envio de mensagem, injeção de contexto e retorno estruturado
  POST /chat/{session_id}/end     — encerramento de sessão
  POST /chat/{session_id}/resolve — marcação como resolvida
  POST /chat/{session_id}/escalate — marcação como escalonada
Cobre também os fluxos de fallback e de disparo de escalonamento automático.
"""
