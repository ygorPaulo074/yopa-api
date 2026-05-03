# AI-ChatBot — Wiki

API conversacional multi-tenant construída com FastAPI. Uma instância serve múltiplos agentes e clientes.

---

## Índice

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Configuração Inicial](#configuração-inicial)
4. [Variáveis de Ambiente](#variáveis-de-ambiente)
5. [Referência de API](#referência-de-api)
   - [Agentes](#agentes)
   - [Chat](#chat)
   - [Dados](#dados)
6. [Configuração do Agente](#configuração-do-agente)
7. [Escalação Automática](#escalação-automática)
8. [Knowledge Base](#knowledge-base)
9. [Persistência](#persistência)
10. [Deploy](#deploy)
11. [Planos](#planos)

---

## Visão Geral

O AI-ChatBot fornece uma API REST para criar e operar agentes conversacionais configuráveis. Cada agente possui:

- Personalidade, tom e comportamento definidos em formulário
- Restrições de tópico com mensagem de fallback
- Gatilhos de escalação por condições de backend
- Análise NLP local de cada mensagem (sentimento, intenção, tópicos)
- Histórico de sessão com persistência incremental

A API é projetada para ser consumida por aplicações externas. O cliente integra via `agent_id` e uma `API-Key` gerada no cadastro do agente.

---

## Arquitetura

```
Requisição do usuário
        │
        ▼
  FastAPI (main.py)
        │
        ├── /agent   → AgentService → PersistenceDriver
        ├── /chat    → AIService → AIClient (LiteLLM) → Modelo de IA
        │                       → CacheClient (Redis)
        │                       → QualityAnalyzer (NLP local)
        │                       → PersistenceDriver (snapshot a cada mensagem)
        └── /data    → PersistenceDriver (leitura)
```

**Camada de cache (Redis):** histórico ativo da sessão, scores NLP, metadados de sessão. TTL configurável (padrão 24h).

**Camada de persistência (PersistenceDriver):** salvo a cada mensagem trocada. Sessões abandonadas não perdem dados. Três drivers disponíveis: Local, Database, Webhook.

**NLP local:** análise de sentimento, detecção de intenção e tópicos via textblob e spaCy, sem consumo de tokens do modelo de IA.

---

## Configuração Inicial

### Pré-requisitos

- Python 3.11+
- Redis (local ou remoto)
- PostgreSQL (opcional, se `STORAGE_TYPE=Database`)

### Instalação

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Setup interativo

```bash
invoke setup
```

O assistente de configuração guia pelas seguintes etapas:

| Etapa | Descrição |
|-------|-----------|
| 0 | Modo de deploy: local ou Docker |
| 1 | Provedor de IA (Anthropic, OpenAI, Gemini, DeepSeek, Groq) |
| 1.5 | Timeout da IA em segundos |
| 2 | API Key do provedor (validada em runtime) |
| 3 | Modo de execução: development ou production |
| 4 | Porta do servidor |
| 5 | Tipo de storage: Local, Database ou Webhook |
| 6 | URL do Redis + TTL de sessão |
| 7 | Idiomas do analisador NLP |
| 8 | CORS: origens permitidas |

Para modo Docker, os arquivos `Dockerfile` e `docker-compose.yml` são gerados automaticamente ao final.

---

## Variáveis de Ambiente

Arquivo `.env` na raiz do projeto. Gerado pelo `invoke setup` ou criado manualmente a partir do `.env.example`.

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `AI_API_KEY` | — | API Key do provedor de IA |
| `AI_MODEL` | — | Identificador do modelo (ex: `groq/llama-3.3-70b-versatile`) |
| `AI_TIMEOUT` | `30` | Timeout da chamada à IA em segundos |
| `RUN_MODE` | `development` | `development` ou `production` |
| `HOST` | `0.0.0.0` | Host do servidor |
| `PORT` | `8000` | Porta do servidor |
| `STORAGE_TYPE` | `local` | `local`, `Database` ou `Webhook` |
| `DATA_PATH` | `./data` | Diretório para storage local |
| `DATABASE_URL` | — | Connection string PostgreSQL |
| `DB_USER` | — | Usuário do banco |
| `DB_PASSWORD` | — | Senha do banco |
| `DB_NAME` | — | Nome do banco |
| `WEBHOOK_URL` | — | URL de destino para driver Webhook |
| `REDIS_URL` | `redis://localhost:6379` | URL do Redis |
| `SESSION_TTL` | `86400` | TTL da sessão em segundos (padrão 24h) |
| `ALLOWED_ORIGINS` | `["http://localhost"]` | Lista JSON de origens CORS permitidas |
| `ANALYZER_LANGUAGES` | `["en"]` | Idiomas do analisador NLP |
| `LOG_LEVEL` | `INFO` | Nível de log |

---

## Referência de API

A autenticação é feita via header `X-API-Key` com a chave gerada no cadastro do agente.

### Agentes

#### `POST /agent`
Cria um novo agente.

**Body:**
```json
{
  "name": "Atendente Loja X",
  "owner": "cliente@empresa.com",
  "tags": ["ecommerce", "suporte"]
}
```

**Resposta:**
```json
{
  "agent_id": "uuid",
  "api_key": "chave-gerada-uma-vez",
  "created_at": "2026-01-01T00:00:00Z"
}
```

> A `api_key` é retornada apenas na criação. Armazene com segurança.

---

#### `GET /agent`
Retorna metadados do agente autenticado.

---

#### `PUT /agent/context`
Atualiza o contexto do agente (persona, comportamento, restrições, escalação).

**Body:** ver seção [Configuração do Agente](#configuração-do-agente).

---

#### `GET /agent/context`
Retorna a versão atual do contexto do agente.

---

#### `GET /agent/context/history`
Lista todas as versões do contexto com histórico de alterações.

---

#### `GET /agent/metrics`
Retorna métricas agregadas: total de sessões, tokens consumidos, média de sentimento.

---

#### `DELETE /agent`
Remove o agente e todos os dados associados (sessões, contextos, usuários).

---

### Chat

#### `POST /chat`
Envia uma mensagem e recebe a resposta da IA.

**Header:** `X-API-Key: <chave-do-agente>`

**Body:**
```json
{
  "session_id": "uuid-da-sessao",
  "user_id": "identificador-opcional-do-usuario",
  "message": "Qual o prazo de entrega?"
}
```

**Resposta:**
```json
{
  "message_id": "uuid",
  "content": "O prazo de entrega é de 3 a 5 dias úteis.",
  "usage": {
    "input_tokens": 120,
    "output_tokens": 30,
    "total_tokens": 150
  },
  "response_time_ms": 842
}
```

A cada mensagem, o sistema:
1. Carrega o system prompt do cache (ou reconstrói a partir do contexto)
2. Executa análise NLP na mensagem do usuário e na resposta
3. Salva snapshot incremental no driver de persistência

---

#### `POST /chat/{session_id}/end`
Encerra a sessão. Gera insights, persiste histórico completo e atualiza contexto do usuário.

---

#### `POST /chat/{session_id}/resolve`
Marca a sessão como resolvida sem encerrar.

---

#### `POST /chat/{session_id}/escalate`
Marca a sessão como escalada manualmente.

---

### Dados

#### `GET /data/chat`
Lista todas as sessões do agente autenticado.

---

#### `GET /data/chat/{session_id}`
Retorna histórico completo de mensagens da sessão. Busca primeiro no Redis; se expirado, recupera do driver de persistência.

---

#### `DELETE /data/chat/{session_id}`
Remove sessão e todos os dados associados.

---

#### `GET /data/chat/{session_id}/insights`
Retorna insights gerados ao encerrar a sessão (pontos-chave, ações sugeridas, resumo).

---

#### `GET /data/context`
Retorna o contexto de um usuário específico (`?user_id=`): idioma detectado, segmento, respostas de formulário.

---

#### `GET /data/analytics`
Retorna analytics agregadas do agente: sessões por período, sentimento médio, tópicos mais frequentes, taxa de escalação.

---

## Configuração do Agente

O contexto do agente é atualizado via `PUT /agent/context`. Cada atualização gera uma nova versão com histórico de alterações.

```json
{
  "persona": "Você é a Clara, atendente virtual da Loja X. Seja sempre cordial e objetivo.",
  "tone": "formal",
  "language": "pt-BR",
  "segment": "ecommerce",
  "behavior": "Responda apenas perguntas relacionadas a pedidos, entregas e trocas.",
  "fallback_message": "Não tenho informações sobre esse assunto. Posso te ajudar com pedidos e entregas.",
  "restrictions": {
    "topics": ["política", "religião", "concorrentes"],
    "files": []
  },
  "knowledge_base": {
    "urls": ["https://loja.com/faq"],
    "files": []
  },
  "escalation_trigger": {
    "operator": "OR",
    "conditions": [
      { "type": "sentiment", "threshold": 0.4 },
      { "type": "keyword", "values": ["cancelar", "reembolso", "fraude"] },
      { "type": "message_count", "value": 10 }
    ]
  }
}
```

### Campos do contexto

| Campo | Descrição |
|-------|-----------|
| `persona` | Identidade e papel do agente. Instrução direta para a IA. |
| `tone` | Tom de voz: `formal`, `informal`, `técnico`, etc. |
| `language` | Idioma preferencial para respostas. |
| `segment` | Segmento de atendimento para categorização. |
| `behavior` | Instruções detalhadas de comportamento. |
| `fallback_message` | Resposta exata quando tópico restrito é abordado. |
| `restrictions.topics` | Lista de tópicos proibidos. |
| `knowledge_base` | Fontes de dados para tool use (plano premium). |
| `escalation_trigger` | Condições de escalação automática (lógica de backend). |

> `escalation_trigger` nunca é enviado para o modelo de IA. É avaliado pelo backend após cada mensagem.

---

## Escalação Automática

O sistema avalia as condições configuradas em `escalation_trigger` após cada mensagem recebida.

### Tipos de condição

| Tipo | Parâmetro | Descrição |
|------|-----------|-----------|
| `sentiment` | `threshold: float` | Escalona se sentimento médio < `-threshold` |
| `keyword` | `values: list[str]` | Escalona se a última mensagem contém qualquer palavra |
| `message_count` | `value: int` | Escalona se número de mensagens do usuário >= valor |
| `topic` | `values: list[str]` | Escalona se tópico detectado está na lista |
| `time_elapsed` | `value: float` | Escalona se tempo desde início da sessão >= segundos |
| `intent` | `value: str` | Escalona se intenção detectada == valor |

### Operadores

- `OR`: escalona se **qualquer** condição for verdadeira
- `AND`: escalona somente se **todas** as condições forem verdadeiras

---

## Knowledge Base

> Funcionalidade de plano premium. Em implementação.

Permite conectar o agente a fontes de dados externas. O modelo de IA decide, com base na pergunta, qual fonte consultar.

### Opções disponíveis

| Opção | Descrição | Status |
|-------|-----------|--------|
| C — File Upload | CSV, JSON, PDF, Excel indexados localmente | Em desenvolvimento |
| A — REST API | Endpoint HTTP do cliente chamado como ferramenta | Em desenvolvimento |
| B — SQL Connection | Query SQL gerada pela IA contra banco read-only com 5 camadas de segurança | Em desenvolvimento |
| D — Webhook | Cliente recebe pergunta e retorna dados estruturados | Em desenvolvimento |

### Segurança da Opção B (SQL)

1. **Nível de banco:** usuário read-only com permissões mínimas (script de orientação fornecido)
2. **Schema registry:** IA só vê o schema das tabelas autorizadas em `allowed_tables`
3. **QueryValidator:** apenas SELECT; blocklist de comandos destrutivos; bloqueia `information_schema`; força `LIMIT`
4. **Constraints de execução:** timeout de 5s por query; limite de linhas e bytes no resultado
5. **Sanitização do resultado:** colunas com nomes sensíveis (password, cpf, token, etc.) são mascaradas antes de chegar à IA

---

## Persistência

### Drivers disponíveis

| Driver | `STORAGE_TYPE` | Descrição |
|--------|---------------|-----------|
| Local | `local` | Arquivos JSON em `DATA_PATH`. Ideal para desenvolvimento. |
| Database | `Database` | PostgreSQL via SQLAlchemy. Requer schema gerado pelo setup. |
| Webhook | `Webhook` | POST para `WEBHOOK_URL` a cada operação de escrita. |

### Estratégia de persistência

O sistema salva snapshots incrementais a cada mensagem processada (não apenas ao encerrar a sessão). Sessões abandonadas sem chamada a `POST /chat/{id}/end` não perdem dados.

O Redis atua como cache de curta duração. Ao expirar, os dados são recuperados do driver de persistência.

### Schema do banco (PostgreSQL)

Tabelas criadas pelo script gerado em `invoke setup`:

- `agents` — registro de agentes
- `agent_contexts` — versões de contexto com histórico
- `user_contexts` — contexto por usuário por agente
- `sessions` — metadados de sessão (tokens, timestamps, flags)
- `session_history` — histórico de mensagens serializado
- `scores` — scores NLP por sessão
- `insights` — insights gerados ao encerrar sessão

---

## Deploy

### Local

```bash
invoke setup   # configuração interativa
invoke run     # inicia o servidor
```

### Docker

O setup detecta automaticamente o modo Docker e gera os arquivos:

```bash
invoke setup   # escolher opção 2 (Docker) no Step 0
docker compose up --build
```

A API fica disponível em `http://localhost:{PORT}`.

### Comandos disponíveis

| Comando | Descrição |
|---------|-----------|
| `invoke setup` | Assistente de configuração interativo |
| `invoke run` | Inicia o servidor FastAPI |
| `invoke test` | Executa os testes com pytest |
| `invoke clear` | Remove dados de sessão em `data/` |
| `invoke lint` | Executa verificação de estilo |
| `invoke docker-build` | Build da imagem Docker |
| `invoke prompt --agent-id <id>` | Exibe o system prompt atual de um agente |
| `invoke prompt-preview --file <path>` | Pré-visualiza system prompt a partir de um JSON |

---

## Planos

| Funcionalidade | Base | Premium |
|----------------|------|---------|
| Criação de agentes | Sim | Sim |
| Chat com histórico | Sim | Sim |
| Análise NLP local | Sim | Sim |
| Escalação automática | Sim | Sim |
| Persistência incremental | Sim | Sim |
| Analytics e insights | Sim | Sim |
| Knowledge base (tool use) | Não | Sim |
| Múltiplas fontes de dados | Não | Sim |

A separação de planos é implementada via Strategy Pattern em `src/services/capabilities/` (Task #13 — em desenvolvimento).
