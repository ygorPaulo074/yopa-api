"""
Contrato abstrato dos drivers de persistência (Strategy Pattern).
Define a interface que Local, Database e Webhook devem implementar.
Qualquer chamada de persistência nos services deve operar sobre este contrato,
nunca sobre um driver concreto diretamente — permite trocar o storage via .env
sem alterar a lógica de negócio.
"""
