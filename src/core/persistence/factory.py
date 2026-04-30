"""
Resolve e instancia o driver de persistência correto com base no STORAGE_TYPE do .env.
Valores válidos: 'Local', 'Database', 'Webhook'.
Usado pelos services para obter o driver sem depender de um concreto —
toda a troca de storage ocorre aqui, sem tocar na lógica de negócio.
"""
