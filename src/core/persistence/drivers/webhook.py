"""
Driver de persistência via despacho HTTP para sistema externo.
Em vez de gravar dados localmente, envia cada evento (criação de agente,
mensagem, fim de sessão, etc.) como POST para WEBHOOK_URL configurado no .env.
O sistema externo é responsável por persistir e indexar os dados recebidos.
Indicado quando o consumidor já possui infraestrutura própria de storage.
"""
