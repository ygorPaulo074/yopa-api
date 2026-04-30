"""
Utilitários de segurança transversais ao projeto.
Responsável por:
  - Sanitização de PII nas mensagens antes de persistir (nomes, CPF, e-mails, etc.)
  - Geração e hash da API Key dos agentes (bcrypt ou similar)
  - Validação da API Key recebida no header Authorization contra o hash armazenado
"""
