"""
Testes de integração para os endpoints do agente:
  POST   /agent                  — criação, geração de API Key e context.xml
  GET    /agent                  — leitura de dados do agente autenticado
  GET    /agent/context          — contexto atual com versão
  GET    /agent/context/history  — histórico de versões e campos alterados
  GET    /agent/metrics          — métricas agregadas de sessões
  PUT    /agent/context          — atualização de contexto e incremento de versão
  DELETE /agent                  — remoção do agente e dados associados
"""
