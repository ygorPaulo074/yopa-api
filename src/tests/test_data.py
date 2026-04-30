"""
Testes de integração para os endpoints de dados e analytics:
  GET    /data/chat                                  — listagem de conversas
  GET    /data/chat/{session_id}                     — histórico completo de sessão
  DELETE /data/chat/{session_id}                     — remoção de sessão
  GET    /data/chat/{session_id}/insights            — insight completo (IA)
  GET    /data/chat/{session_id}/insights/sentiment  — sentimento (local)
  GET    /data/chat/{session_id}/insights/topics     — tópicos (local)
  GET    /data/chat/{session_id}/insights/metrics    — métricas (local)
  GET    /data/chat/{session_id}/insights/suggestions — sugestões (IA)
  GET    /data/context                               — contextos de usuários
  GET    /data/context/{user_id}                     — contexto de usuário específico
  DELETE /data/context/{user_id}                     — remoção de contexto
  GET    /data/analytics                             — analytics completo
  GET    /data/analytics/summary|patterns|sentiment|users|timeline — sub-rotas
"""
