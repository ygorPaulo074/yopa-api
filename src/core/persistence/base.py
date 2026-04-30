"""
Contrato abstrato dos drivers de persistência (Strategy Pattern).
Define a interface que Local, Database e Webhook devem implementar.
Qualquer chamada de persistência nos services deve operar sobre este contrato,
nunca sobre um driver concreto diretamente — permite trocar o storage via .env
sem alterar a lógica de negócio.

Segurança é responsabilidade desta camada:
  - Sanitização de PII ocorre nos métodos de escrita (save_*) antes de persistir
  - Geração e hash de API Key ocorrem em save_agent
  - Validação da API Key ocorre em load_agent / load_context
Os services e routes nunca chamam security.py diretamente.
"""

