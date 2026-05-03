# Chatbot API — IA Conversacional

## Índice

- [Conceito](#conceito)
- [Inicialização](#inicialização)
- [Funcionalidades](#funcionalidades)
- [Fluxo de Uso](#fluxo-de-uso)
- [Autenticação](#autenticação)
- [Agente](#agente)
  - [POST /agent](#post-agent)
  - [GET /agent](#get-agent)
  - [GET /agent/context](#get-agentcontext)
  - [GET /agent/context/history](#get-agentcontexthistory)
  - [GET /agent/metrics](#get-agentmetrics)
  - [PUT /agent/context](#put-agentcontext)
  - [DELETE /agent](#delete-agent)
- [Chat](#chat)
  - [POST /chat](#post-chat)
  - [Ciclo de vida da sessão](#ciclo-de-vida-da-sessao)
    - [POST /chat/{session\_id}/end](#post-chatsession_idend)
    - [POST /chat/{session\_id}/resolve](#post-chatsession_idresolve)
    - [POST /chat/{session\_id}/escalate](#post-chatsession_idescalate)
- [Data](#data)
  - [GET /data/chat](#get-datachat)
  - [GET /data/chat/{session\_id}](#get-datachatsession_id)
  - [DELETE /data/chat/{session\_id}](#delete-datachatsession_id)
  - [Insights](#insights)
    - [GET /data/chat/{session\_id}/insights](#get-datachatsession_idinsights)
    - [GET /data/chat/{session\_id}/insights/sentiment](#get-datachatsession_idinsightssentiment)
    - [GET /data/chat/{session\_id}/insights/topics](#get-datachatsession_idinsightstopics)
    - [GET /data/chat/{session\_id}/insights/metrics](#get-datachatsession_idinsightsmetrics)
    - [GET /data/chat/{session\_id}/insights/suggestions](#get-datachatsession_idinsightssuggestions)
  - [GET /data/context](#get-datacontext)
  - [GET /data/context/{user\_id}](#get-datacontextuser_id)
  - [DELETE /data/context/{user\_id}](#delete-datacontextuser_id)
  - [Analytics](#analytics)
    - [GET /data/analytics](#get-dataanalytics)
    - [GET /data/analytics/summary](#get-dataanalyticssummary)
    - [GET /data/analytics/patterns](#get-dataanalyticspatterns)
    - [GET /data/analytics/sentiment](#get-dataanalyticssentiment)
    - [GET /data/analytics/users](#get-dataanalyticsusers)
    - [GET /data/analytics/timeline](#get-dataanalyticstimeline)
- [Estrutura de Arquivos](#estrutura-de-arquivos)
- [Pasta data/](#pasta-data)
- [Contexto dos Agentes](#contexto-dos-agentes)
- [Análise Local de Conversas](#análise-local-de-conversas)
- [Cache Redis](#cache-redis)
- [Requisitos](#requisitos)
- [Instalação](#instalação)

---

<a id="conceito"></a>
## Conceito

API de IA conversacional projetada para ser consumida por projetos externos. Abstrai toda a complexidade de comunicação com o modelo de IA, geração de contexto e rastreamento de conversas, expondo uma interface simples e padronizada via HTTP.

O projeto é agnóstico ao domínio de negócio — pode servir como base para atendimento ao cliente, assistentes virtuais, sistemas de suporte com escalonamento humano, ou qualquer aplicação que exija interação conversacional com IA.

A persistência dos dados é responsabilidade do consumidor. A API retorna JSONs completos a cada interação, contendo dados da sessão e histórico da conversa, para que o consumidor armazene da forma que preferir.

---

<a id="inicialização"></a>
## Inicialização

## `tools/setup.py`

O `setup.py` é o ponto de entrada obrigatório antes de qualquer outra coisa. Ele é responsável por configurar o ambiente da API de forma guiada, validar as credenciais com o provedor de IA antes de gravar qualquer arquivo, e gerar o `.env` automaticamente. A API não sobe sem que o setup tenha sido concluído — o `config.py` verifica a existência do arquivo `.initialized` ao iniciar e chama o setup caso ele não exista.

**Execute uma única vez, antes de subir a aplicação:**

```bash
python tools/setup.py
```

Se precisar reconfigurar, delete o `.initialized` na raiz do projeto e execute novamente. O `.env` será sobrescrito.

### O que o setup pergunta

**Provedor de IA**

Selecione o provedor pelo número correspondente. O modelo padrão daquele provedor já é sugerido automaticamente.

```
1. Anthropic  →  claude-sonnet-4
2. OpenAI     →  gpt-4o
3. Gemini     →  gemini/gemini-2.0-flash
4. Deepseek   →  deepseek/deepseek-chat
5. Groq       →  groq/llama-3.3-70b-versatile
```

**API Key**

Após selecionar o provedor, o setup solicita a API Key e faz uma chamada de validação real ao provedor antes de continuar — com `max_tokens=1` para minimizar custo. A API só avança quando a chave for confirmada como válida. Chaves inválidas ou erros de conexão são tratados com mensagem específica.

**Run Mode**

Define o modo de execução: `development` ou `production`. Em `development`, a API verifica o `.initialized` e aciona o setup automaticamente se necessário. Em `production`, exige que o `.env` esteja completamente configurado — caso contrário, lança uma exceção e não sobe.

**Porta**

Porta em que o servidor vai rodar. Padrão: `8000`. Somente valores numéricos são aceitos.

**Redis**

URL de conexão com o Redis. Obrigatório — o Redis é a espinha dorsal do cache de contexto, histórico de sessões e scores NLP. O setup valida a conexão via `PING` antes de gravar o `.env`. Padrão: `redis://localhost:6379`.

Formatos aceitos:
- `redis://localhost:6379` — conexão local sem autenticação
- `redis://:senha@localhost:6379` — com senha
- `rediss://user:senha@host:6380` — com TLS (serviços gerenciados: Upstash, Redis Cloud, ElastiCache)
- `unix:///caminho/para/socket` — socket Unix

O TTL das sessões define por quantos segundos o histórico de conversa e os scores ficam em cache após a última mensagem. Padrão: `86400` (24 horas).

**Origens permitidas (CORS)**

Lista de domínios que podem consumir a API, separados por vírgula. Cada entrada é validada como URL pelo Pydantic antes de ser aceita. Padrão: `http://localhost`.

### O que o setup gera

Ao final, dois arquivos são criados na raiz do projeto:

- `.env` — com todas as variáveis configuradas
- `.initialized` — flag que indica que o setup foi concluído. **Não delete este arquivo manualmente** a menos que queira redefinir toda a configuração.

Quando o tipo de storage selecionado for **Database**, o setup oferece a geração do schema em dois formatos, salvos em `scripts/`:

| Formato | Arquivo gerado | Observação |
|---|---|---|
| SQL Script | `scripts/schema.sql` | **PostgreSQL 14+ apenas.** Usa `SERIAL` e `JSONB` — não compatível com MySQL ou SQLite |
| Prisma Migrate | `scripts/schema.prisma` | Adapta os tipos automaticamente ao provider configurado no `datasource` |

Após a geração, o setup pergunta se deseja criar o `docker-compose.yml`. Há duas variantes: apenas a API (banco gerenciado externamente) ou API + serviço PostgreSQL com o schema aplicado automaticamente na primeira execução.

---

<a id="funcionalidades"></a>
## Funcionalidades

- **Criação de agentes** configurados a partir dos dados fornecidos pelo usuário, definindo precisamente como a IA deve se comportar
- **Geração de contexto personalizado** processado pelo `context_builder.py` no momento da criação do agente, armazenado em XML para máxima precisão na interpretação pelo modelo
- **Processamento de mensagens** com envio para o modelo de IA e retorno estruturado da resposta
- **Rastreamento de sessões** com dados por conversa (session_id, timestamps, tokens utilizados)
- **Análise local de conversas** via `textblob` e `spaCy` — geração de scores de sentimento, detecção de tópicos e métricas sem consumo de tokens de IA
- **Insights por sessão** gerados pela IA sob demanda, alimentados pelos scores locais para minimizar consumo de tokens
- **Dados analíticos agregados** de todas as conversas, prontos para consumo por dashboards, sistemas de RAG ou qualquer ferramenta de análise
- **Logs de sistema** para rastreabilidade de erros e acesso
- **Documentação automática** via Swagger gerada automaticamente pelo FastAPI a partir dos schemas Pydantic

---

<a id="fluxo-de-uso"></a>
## Fluxo de Uso

```
1. Usuário cria o agente        →  POST /agent
2. Usuário recebe a API Key     →  usa em todas as requisições subsequentes
3. Usuário inicia conversas     →  POST /chat
4. Usuário consulta os dados    →  GET  /data/...
5. Usuário solicita insights    →  GET  /data/chat/{session_id}/insights
```

---

<a id="autenticação"></a>
## Autenticação

Todas as rotas exigem autenticação via API Key obtida na criação do agente:

```
Authorization: Bearer sk-...
```

---

<a id="agente"></a>
## Agente

<a id="post-agent"></a>
### `POST /agent`

Cria um agente, processa seu contexto via `context_builder.py` e armazena em `context.xml`. Retorna a API Key que autentica todas as requisições subsequentes.

**Request:**
```json
{
  "name": "Assistente de Suporte",
  "context": {
    "tone": "formal",
    "language": "pt-BR",
    "segment": "ecommerce",
    "persona": "Ana",
    "behavior": "Responda apenas sobre pedidos e entregas.",
    "restrictions": {
      "topics": ["política interna", "dados de outros clientes"],
      "files": [
        {
          "name": "termos_de_uso.pdf",
          "url": "https://meusite.com/docs/termos.pdf"
        }
      ]
    },
    "fallback_message": "Não consegui entender, pode reformular?",
    "knowledge_base": {
      "urls": ["https://meusite.com/faq"],
      "files": [
        {
          "name": "catalogo_produtos.pdf",
          "url": "https://meusite.com/docs/catalogo.pdf"
        }
      ]
    },
    "tags": ["suporte", "ecommerce"],
    "escalation_trigger": {
      "operator": "OR",
      "conditions": [
        { "type": "keyword", "values": ["atendente", "gerente"] },
        { "type": "sentiment", "value": "negative", "threshold": 0.8 },
        { "type": "message_count", "value": 10 },
        { "type": "topic", "values": ["reembolso"] },
        { "type": "time_elapsed", "value": 300 },
        { "type": "intent", "values": ["cancelamento", "processo judicial"] }
      ]
    }
  }
}
```

**Validação de arquivos:**

Arquivos enviados em `restrictions.files` e `knowledge_base.files` passam por validação antes de serem processados:
- Extensões permitidas: `.pdf`, `.txt`, `.docx`
- Tamanho mínimo de conteúdo extraído
- Detecção de PDF escaneado sem OCR
- Verificação de encoding e legibilidade do texto

Em caso de falha:
```json
{
  "error": "file_quality_error",
  "file": "manual_interno.pdf",
  "reason": "Conteúdo insuficiente extraído — o arquivo pode estar escaneado sem OCR ou corrompido.",
  "suggestion": "Converta o arquivo para texto pesquisável antes de enviar."
}
```

**Response:**
```json
{
  "agent_id": "agent_789",
  "api_key": "sk-...",
  "created_at": "2026-04-25T18:00:00Z"
}
```

<a id="get-agent"></a>
### `GET /agent`

Retorna os dados base do agente autenticado: identificação, owner e timestamps.

**Response:**
```json
{
  "agent_id": "agent_789",
  "name": "Assistente de Suporte",
  "owner": "user_123",
  "tags": ["suporte", "ecommerce"],
  "created_at": "2026-04-25T18:00:00Z",
  "updated_at": "2026-04-25T18:00:00Z",
  "active_since": "2026-04-25T18:00:00Z",
  "last_activity_at": "2026-04-27T14:00:00Z"
}
```

<a id="get-agentcontext"></a>
### `GET /agent/context`

Retorna a configuração completa do contexto atual do agente.

**Response:**
```json
{
  "agent_id": "agent_789",
  "version": 1,
  "tone": "formal",
  "language": "pt-BR",
  "segment": "ecommerce",
  "persona": "Ana",
  "behavior": "Responda apenas sobre pedidos e entregas.",
  "restrictions": {
    "topics": ["política interna", "dados de outros clientes"],
    "files": [{ "name": "termos_de_uso.pdf", "url": "...", "quality": "ok" }]
  },
  "fallback_message": "Não consegui entender, pode reformular?",
  "knowledge_base": {
    "urls": ["https://meusite.com/faq"],
    "files": [{ "name": "catalogo_produtos.pdf", "url": "...", "quality": "ok" }]
  },
  "escalation_trigger": {
    "operator": "OR",
    "conditions": [
      { "type": "keyword", "values": ["atendente", "gerente"] },
      { "type": "sentiment", "value": "negative", "threshold": 0.8 },
      { "type": "message_count", "value": 10 },
      { "type": "topic", "values": ["reembolso"] },
      { "type": "time_elapsed", "value": 300 },
      { "type": "intent", "values": ["cancelamento", "processo judicial"] }
    ]
  }
}
```

<a id="get-agentcontexthistory"></a>
### `GET /agent/context/history`

Retorna o histórico de versões do contexto do agente. Útil para auditar mudanças de comportamento da IA ao longo do tempo.

**Response:**
```json
{
  "agent_id": "agent_789",
  "versions": [
    {
      "version": 2,
      "updated_at": "2026-04-27T10:00:00Z",
      "changes": ["tone", "behavior"]
    },
    {
      "version": 1,
      "updated_at": "2026-04-25T18:00:00Z",
      "changes": []
    }
  ]
}
```

<a id="get-agentmetrics"></a>
### `GET /agent/metrics`

Retorna as métricas do agente autenticado.

**Response:**
```json
{
  "agent_id": "agent_789",
  "total_sessions": 1200,
  "total_messages": 9600,
  "avg_response_time_ms": 340,
  "resolution_rate": 0.87,
  "escalation_rate": 0.13,
  "active_since": "2026-04-25T18:00:00Z",
  "last_activity_at": "2026-04-27T14:00:00Z"
}
```

<a id="put-agentcontext"></a>
### `PUT /agent/context`

Atualiza as configurações do agente, regenera o `context.xml` e incrementa a versão do contexto automaticamente.

**Request:**
```json
{
  "tone": "informal",
  "behavior": "Responda perguntas sobre pedidos, entregas e trocas."
}
```

<a id="delete-agent"></a>
### `DELETE /agent`

Remove o agente, seu `context.xml` e todos os dados associados em `data/agents/{agent_id}/`.

<a id="chat"></a>
## Chat

<a id="post-chat"></a>
### `POST /chat`

Envia uma mensagem para a IA e retorna a resposta processada. O contexto do agente é injetado automaticamente a partir do `context.xml`. Após cada resposta, o script de análise local processa a mensagem e atualiza os scores de sentimento e tópicos da sessão sem consumo de tokens.

**Request:**
```json
{
  "session_id": "abc123",
  "user_id": "user_456",
  "message": "Qual o prazo de entrega?"
}
```

**Response:**
```json
{
  "session": {
    "session_id": "abc123",
    "agent_id": "agent_789",
    "model": "claude-sonnet-4",
    "started_at": "2026-04-25T18:00:00Z",
    "response_time_ms": 340,
    "tokens": {
      "input": 120,
      "output": 85,
      "total": 205
    }
  },
  "conversation": [
    {
      "message": {
        "id": "msg_001",
        "role": "user",
        "content": "Qual o prazo de entrega?",
        "timestamp": "2026-04-25T18:00:00Z",
        "status": "delivered",
        "tokens": 12
      }
    },
    {
      "message": {
        "id": "msg_002",
        "role": "assistant",
        "content": "O prazo é de 5 dias úteis.",
        "timestamp": "2026-04-25T18:00:01Z",
        "status": "delivered",
        "tokens": 18,
        "response_time_ms": 340
      }
    }
  ]
}
```

**Status possíveis de `message.status`:**
- `delivered` — entregue normalmente
- `pending` — aguardando resposta da IA
- `failed` — erro no processamento
- `escalated` — mensagem que trigou escalonamento humano

<a id="ciclo-de-vida-da-sessao"></a>
### Ciclo de vida da sessão

Endpoints para transição de estado de uma sessão. Devem ser chamados pelo consumidor no momento certo do fluxo — a API não encerra nem resolve sessões automaticamente.

<a id="post-chatsession_idend"></a>
#### `POST /chat/{session_id}/end`

Encerra a sessão, gravando o `ended_at`. Após este ponto, a sessão não aceita novas mensagens.

**Response:**
```json
{
  "session_id": "abc123",
  "ended_at": "2026-04-25T18:12:00Z"
}
```

<a id="post-chatsession_idresolve"></a>
#### `POST /chat/{session_id}/resolve`

Marca a sessão como resolvida pela IA, sem escalonamento humano.

**Response:**
```json
{
  "session_id": "abc123",
  "resolved": true,
  "updated_at": "2026-04-25T18:10:00Z"
}
```

<a id="post-chatsession_idescalate"></a>
#### `POST /chat/{session_id}/escalate`

Marca a sessão como escalonada para atendimento humano. A última mensagem do assistente recebe `status: "escalated"`.

**Response:**
```json
{
  "session_id": "abc123",
  "escalated": true,
  "updated_at": "2026-04-25T18:11:30Z"
}
```

<a id="data"></a>
## Data

<a id="get-datachat"></a>
### `GET /data/chat`

Retorna a listagem de todas as conversas do agente autenticado.

**Response:**
```json
{
  "total": 1200,
  "chats": [
    {
      "session_id": "abc123",
      "agent_id": "agent_789",
      "started_at": "2026-04-25T18:00:00Z",
      "ended_at": "2026-04-25T18:12:00Z",
      "total_messages": 8,
      "total_tokens": 1640,
      "resolved": true,
      "escalated": false
    }
  ]
}
```

<a id="get-datachatsession_id"></a>
### `GET /data/chat/{session_id}`

Retorna o histórico completo de uma conversa específica.

**Response:**
```json
{
  "session": {
    "session_id": "abc123",
    "agent_id": "agent_789",
    "started_at": "2026-04-25T18:00:00Z",
    "ended_at": "2026-04-25T18:12:00Z",
    "total_messages": 8,
    "total_tokens": 1640,
    "resolved": true,
    "escalated": false
  },
  "conversation": [
    {
      "message": {
        "id": "msg_001",
        "role": "user",
        "content": "Qual o prazo de entrega?",
        "timestamp": "2026-04-25T18:00:00Z",
        "status": "delivered",
        "tokens": 12
      }
    },
    {
      "message": {
        "id": "msg_002",
        "role": "assistant",
        "content": "O prazo é de 5 dias úteis.",
        "timestamp": "2026-04-25T18:00:01Z",
        "status": "delivered",
        "tokens": 18,
        "response_time_ms": 340
      }
    }
  ]
}
```

<a id="delete-datachatsession_id"></a>
### `DELETE /data/chat/{session_id}`

Remove uma sessão de conversa específica e seus dados em `data/agents/{agent_id}/chats/{session_id}/`.

<a id="insights"></a>
### Insights

Análise por sessão. As rotas locais não consomem tokens — são alimentadas pelos scores gerados durante o `POST /chat`.

<a id="get-datachatsession_idinsights"></a>
#### `GET /data/chat/{session_id}/insights`

Retorna o dataframe completo de insights de uma sessão. Consolida três fontes de dados:

1. **Scores locais** — gerados por `textblob` e `spaCy` durante o `POST /chat`, sem consumo de tokens
2. **Dados analíticos** — métricas da sessão e do agente já disponíveis
3. **Análise da IA** — gerada sob demanda apenas nesta rota, alimentada pelos scores locais para minimizar tokens consumidos

Por ser um payload denso, recomenda-se usar as rotas abstraídas abaixo quando apenas um subconjunto dos dados for necessário.

**Response:**
```json
{
  "session_id": "abc123",
  "agent_id": "agent_789",
  "generated_at": "2026-04-25T18:15:00Z",
  "sentiment": {
    "score": -0.3,
    "label": "negative",
    "progression": [
      { "message_id": "msg_001", "score": 0.1 },
      { "message_id": "msg_003", "score": -0.4 },
      { "message_id": "msg_007", "score": -0.8 }
    ]
  },
  "topics": {
    "detected": ["entrega", "prazo", "atraso"],
    "main_topic": "atraso na entrega",
    "intent": "reembolso"
  },
  "resolution": "escalated",
  "metrics": {
    "total_messages": 8,
    "total_tokens": 1640,
    "avg_user_message_length": 42,
    "avg_response_time_ms": 340,
    "time_to_escalation_seconds": 187
  },
  "agent_context": {
    "version": 1,
    "tone": "formal",
    "segment": "ecommerce"
  },
  "ai_analysis": {
    "key_points": [
      "Cliente insatisfeito com prazo",
      "Pedido atrasado 3 dias"
    ],
    "suggested_actions": [
      "Oferecer reembolso parcial",
      "Acionar equipe de logística"
    ],
    "summary": "Cliente contatou suporte sobre atraso em pedido. Sentimento deteriorou progressivamente até escalonamento."
  }
}
```

<a id="get-datachatsession_idinsightssentiment"></a>
#### `GET /data/chat/{session_id}/insights/sentiment`

Retorna apenas os dados de sentimento da sessão — gerados localmente, sem consumo de tokens.

**Response:**
```json
{
  "session_id": "abc123",
  "sentiment": {
    "score": -0.3,
    "label": "negative",
    "progression": [
      { "message_id": "msg_001", "score": 0.1 },
      { "message_id": "msg_003", "score": -0.4 },
      { "message_id": "msg_007", "score": -0.8 }
    ]
  }
}
```

<a id="get-datachatsession_idinsightstopics"></a>
#### `GET /data/chat/{session_id}/insights/topics`

Retorna os tópicos detectados na sessão — gerados localmente via `spaCy`, sem consumo de tokens.

**Response:**
```json
{
  "session_id": "abc123",
  "topics": {
    "detected": ["entrega", "prazo", "atraso"],
    "main_topic": "atraso na entrega",
    "intent": "reembolso"
  }
}
```

<a id="get-datachatsession_idinsightsmetrics"></a>
#### `GET /data/chat/{session_id}/insights/metrics`

Retorna as métricas quantitativas da sessão — calculadas localmente, sem consumo de tokens.

**Response:**
```json
{
  "session_id": "abc123",
  "metrics": {
    "total_messages": 8,
    "total_tokens": 1640,
    "avg_user_message_length": 42,
    "avg_response_time_ms": 340,
    "time_to_escalation_seconds": 187,
    "resolution": "escalated"
  }
}
```

<a id="get-datachatsession_idinsightssuggestions"></a>
#### `GET /data/chat/{session_id}/insights/suggestions`

Retorna as ações sugeridas e análise geradas pela IA. **Esta é a única sub-rota de insights que consome tokens.**

**Response:**
```json
{
  "session_id": "abc123",
  "generated_at": "2026-04-25T18:15:00Z",
  "ai_analysis": {
    "key_points": [
      "Cliente insatisfeito com prazo",
      "Pedido atrasado 3 dias"
    ],
    "suggested_actions": [
      "Oferecer reembolso parcial",
      "Acionar equipe de logística"
    ],
    "summary": "Cliente contatou suporte sobre atraso em pedido. Sentimento deteriorou progressivamente até escalonamento."
  }
}
```

<a id="get-datacontext"></a>
### `GET /data/context`

Retorna todos os contextos de usuários atendidos pelo agente autenticado.

**Response:**
```json
{
  "total": 300,
  "contexts": [
    {
      "user_id": "user_456",
      "created_at": "2026-04-25T17:55:00Z",
      "updated_at": "2026-04-25T18:00:00Z",
      "profile": {
        "segment": "ecommerce",
        "language": "pt-BR"
      }
    }
  ]
}
```

<a id="get-datacontextuser_id"></a>
### `GET /data/context/{user_id}`

Retorna o contexto de um usuário específico.

**Response:**
```json
{
  "user_id": "user_456",
  "created_at": "2026-04-25T17:55:00Z",
  "updated_at": "2026-04-25T18:00:00Z",
  "profile": {
    "segment": "ecommerce",
    "language": "pt-BR",
    "form_answers": {
      "main_need": "suporte",
      "preferred_tone": "formal"
    }
  }
}
```

<a id="delete-datacontextuser_id"></a>
### `DELETE /data/context/{user_id}`

Remove o contexto de um usuário específico.

<a id="analytics"></a>
### Analytics

Visão agregada de todas as conversas do agente autenticado. Alimentada pelos scores locais gerados durante o `POST /chat`. Projetada para consumo por dashboards, sistemas de RAG e ferramentas de análise de negócio. Use as sub-rotas quando apenas um subconjunto dos dados for necessário.

<a id="get-dataanalytics"></a>
#### `GET /data/analytics`

Retorna o payload analítico completo.

**Response:**
```json
{
  "generated_at": "2026-04-25T18:00:00Z",
  "period": {
    "from": "2026-01-01T00:00:00Z",
    "to": "2026-04-25T23:59:59Z"
  },
  "summary": {
    "total_chats": 1200,
    "total_messages": 9600,
    "total_users": 870,
    "avg_messages_per_chat": 8,
    "avg_chat_duration_seconds": 187,
    "avg_response_time_ms": 340,
    "resolution_rate": 0.87,
    "escalation_rate": 0.13,
    "total_tokens_used": 980000,
    "avg_tokens_per_chat": 816
  },
  "patterns": {
    "most_common_topics": [
      { "topic": "prazo de entrega", "count": 430, "resolution_rate": 0.91 },
      { "topic": "forma de pagamento", "count": 318, "resolution_rate": 0.89 },
      { "topic": "cancelamento", "count": 210, "resolution_rate": 0.74 }
    ],
    "most_common_unresolved_topics": [
      { "topic": "cancelamento", "count": 55 },
      { "topic": "troca de produto", "count": 48 }
    ],
    "peak_hours": [
      { "hour": "14:00", "avg_chats": 92 },
      { "hour": "18:00", "avg_chats": 87 }
    ],
    "peak_days": ["friday", "monday"],
    "avg_messages_to_resolution": 6,
    "avg_messages_to_escalation": 12
  },
  "sentiment": {
    "avg_score": -0.12,
    "distribution": {
      "positive": 0.45,
      "neutral": 0.32,
      "negative": 0.23
    }
  },
  "users": {
    "new_users": 430,
    "returning_users": 440,
    "avg_chats_per_user": 1.38,
    "segments": [
      { "segment": "ecommerce", "total_users": 520, "resolution_rate": 0.90 },
      { "segment": "saas", "total_users": 350, "resolution_rate": 0.83 }
    ]
  },
  "timeline": [
    {
      "date": "2026-04-25",
      "total_chats": 42,
      "resolved": 38,
      "escalated": 4,
      "new_users": 18,
      "total_tokens": 34272,
      "avg_response_time_ms": 320,
      "avg_sentiment_score": -0.15
    }
  ]
}
```

<a id="get-dataanalyticssummary"></a>
#### `GET /data/analytics/summary`

Retorna apenas o bloco `summary` com os totais numéricos agregados.

**Response:**
```json
{
  "generated_at": "2026-04-25T18:00:00Z",
  "period": { "from": "2026-01-01T00:00:00Z", "to": "2026-04-25T23:59:59Z" },
  "summary": {
    "total_chats": 1200,
    "total_messages": 9600,
    "total_users": 870,
    "avg_messages_per_chat": 8,
    "avg_chat_duration_seconds": 187,
    "avg_response_time_ms": 340,
    "resolution_rate": 0.87,
    "escalation_rate": 0.13,
    "total_tokens_used": 980000,
    "avg_tokens_per_chat": 816
  }
}
```

<a id="get-dataanalyticspatterns"></a>
#### `GET /data/analytics/patterns`

Retorna padrões de tópicos, horários de pico e médias de resolução/escalonamento.

**Response:**
```json
{
  "generated_at": "2026-04-25T18:00:00Z",
  "period": { "from": "2026-01-01T00:00:00Z", "to": "2026-04-25T23:59:59Z" },
  "patterns": {
    "most_common_topics": [
      { "topic": "prazo de entrega", "count": 430, "resolution_rate": 0.91 }
    ],
    "most_common_unresolved_topics": [
      { "topic": "cancelamento", "count": 55 }
    ],
    "peak_hours": [
      { "hour": "14:00", "avg_chats": 92 }
    ],
    "peak_days": ["friday", "monday"],
    "avg_messages_to_resolution": 6,
    "avg_messages_to_escalation": 12
  }
}
```

<a id="get-dataanalyticssentiment"></a>
#### `GET /data/analytics/sentiment`

Retorna o score médio de sentimento e a distribuição positivo/neutro/negativo.

**Response:**
```json
{
  "generated_at": "2026-04-25T18:00:00Z",
  "period": { "from": "2026-01-01T00:00:00Z", "to": "2026-04-25T23:59:59Z" },
  "sentiment": {
    "avg_score": -0.12,
    "distribution": {
      "positive": 0.45,
      "neutral": 0.32,
      "negative": 0.23
    }
  }
}
```

<a id="get-dataanalyticsusers"></a>
#### `GET /data/analytics/users`

Retorna segmentação de usuários, taxa de novos vs. recorrentes e resolução por segmento.

**Response:**
```json
{
  "generated_at": "2026-04-25T18:00:00Z",
  "period": { "from": "2026-01-01T00:00:00Z", "to": "2026-04-25T23:59:59Z" },
  "users": {
    "new_users": 430,
    "returning_users": 440,
    "avg_chats_per_user": 1.38,
    "segments": [
      { "segment": "ecommerce", "total_users": 520, "resolution_rate": 0.90 },
      { "segment": "saas", "total_users": 350, "resolution_rate": 0.83 }
    ]
  }
}
```

<a id="get-dataanalyticstimeline"></a>
#### `GET /data/analytics/timeline`

Retorna a evolução diária das métricas no período. Ideal para geração de gráficos.

**Response:**
```json
{
  "generated_at": "2026-04-25T18:00:00Z",
  "period": { "from": "2026-01-01T00:00:00Z", "to": "2026-04-25T23:59:59Z" },
  "timeline": [
    {
      "date": "2026-04-25",
      "total_chats": 42,
      "resolved": 38,
      "escalated": 4,
      "new_users": 18,
      "total_tokens": 34272,
      "avg_response_time_ms": 320,
      "avg_sentiment_score": -0.15
    }
  ]
}
```

---

<a id="estrutura-de-arquivos"></a>
## Estrutura de Arquivos

```
AI-ChatBot/
├── main.py                        # inicializa FastAPI, registra middlewares e rotas
├── requirements.txt
├── .env
├── .env.example
├── .gitignore
├── .initialized                   # flag de primeira execução — gerado pelo setup.py
├── README.md
├── data/                          # gerado em runtime — não versionado
│   └── README.md                  # instrução: não versionar este diretório
└── src/
    ├── infrastructure/            # configurações globais e infraestrutura transversal
    │   └── config.py              # variáveis de ambiente, settings, CORS, rate limiter
    ├── core/                      # lógica central e utilitários transversais
    │   ├── context_builder.py     # AgentContext (Pydantic) → system prompt XML (cacheado no Redis)
    │   ├── security.py            # sanitização de PII, hash de API Key (placeholder)
    │   ├── cache/                 # camada de cache Redis
    │   │   ├── __init__.py
    │   │   ├── client.py          # CacheClient — contexto, histórico, scores e meta de sessão
    │   │   └── keys.py            # helpers de nomeação de chaves Redis
    │   └── persistence/           # Strategy Pattern — abstração de storage
    │       ├── __init__.py
    │       ├── base.py            # interface abstrata — contrato dos drivers
    │       ├── factory.py         # resolve driver pelo STORAGE_TYPE do .env
    │       └── drivers/
    │           ├── local.py       # persistência em arquivos JSON
    │           ├── database.py    # persistência via Prisma/SQL
    │           └── webhook.py     # despacho HTTP para sistema externo
    ├── services/                  # lógica de negócio — orquestra core e clients
    │   ├── agent_service.py       # ciclo de vida do agente: create, get, update, delete
    │   ├── context_service.py     # versionamento de contexto e histórico de changes ✅
    │   ├── ai_service.py          # orquestra chamadas à IA, fallback e escalonamento
    │   └── quality_analyzer.py    # análise local NLP: sentiment, tópicos, intent
    ├── clients/                   # conexões com serviços externos
    │   ├── ai_client.py           # LiteLLM: modelo, API key, timeout, AIResponse ✅
    │   └── skills/
    │       ├── CONTEXT.md         # gerado pelo context_builder.py por agente
    │       └── PROMPT.md          # template base do system prompt
    ├── routes/                    # camada HTTP — schemas Pydantic e handlers FastAPI
    │   ├── base_schemas.py        # schemas compartilhados: AgentContext e sub-modelos
    │   ├── agent/
    │   │   ├── __init__.py
    │   │   ├── index.py           # handlers: POST/GET/PUT/DELETE /agent
    │   │   └── schemas.py         # AgentCreateRequest/Response, AgentGetResponse, etc.
    │   ├── chat/
    │   │   ├── __init__.py
    │   │   ├── index.py           # handler: POST /chat e ciclo de vida da sessão
    │   │   └── schemas.py         # ChatRequest/Response, SessionResponse
    │   └── data/
    │       ├── __init__.py
    │       ├── index.py           # handlers: GET /data/chat, /data/context, /data/analytics
    │       └── schemas.py         # InsightsResponse, AnalyticsResponse, ContextResponse
    ├── tests/                     # testes por domínio
    │   ├── test_agent.py
    │   ├── test_chat.py
    │   └── test_data.py
    └── tools/                     # scripts CLI — executados fora do ciclo de request
        ├── setup.py               # configuração inicial guiada — roda uma vez ✅
        ├── create_db_scripts.py   # gera schema.sql, schema.prisma e docker-compose ✅
        ├── clear_data.py          # limpa dados gerados em desenvolvimento
        └── run_tests.py           # executa testes e aciona clear_data ao final
```

---

<a id="pasta-data"></a>
## Pasta `data/`

A pasta `data/` é gerada automaticamente em runtime e **não faz parte do repositório** (somente `data/agents/` está no `.gitignore` — o `data/README.md` é versionado). Sua localização padrão é a raiz do projeto (`AI-ChatBot/data/`), configurável via variável de ambiente `DATA_PATH` no `.env`.

```
data/
└── agents/
    └── {agent_id}/
        ├── agent.json                         # criado no POST /agent
        ├── context/
        │   ├── current.json                   # criado no POST /agent, atualizado no PUT /agent/context
        │   └── history/
        │       └── v{n}.json                  # snapshot imutável de cada versão do contexto
        ├── users/
        │   └── {user_id}.json                 # contexto acumulado por usuário
        └── chats/
            └── {session_id}/
                ├── session.json               # criado no POST /chat/{id}/end, resolve ou escalate
                ├── scores.json                # criado apenas no POST /chat/{id}/end
                └── insights.json              # criado sob demanda via GET /data/chat/{id}/insights
```

> **O system prompt XML não é gravado em disco** — é construído pelo `context_builder.py` e mantido exclusivamente no Redis.
>
> **`chats/` não é criado durante o `POST /chat`** — mensagens ficam no Redis durante a sessão ativa. Os arquivos só são gravados ao encerrar via `POST /chat/{session_id}/end`.
>
> **`users/` e `chats/`** são criados conforme o uso — um agente recém-criado terá apenas `agent.json` e `context/`.

### `agent.json`

Registro persistido no `POST /agent`. Contém identificação, owner, hash da API Key e timestamps.

```json
{
  "agent_id": "d9f53d15-...",
  "name": "Assistente de Suporte",
  "owner": "empresa",
  "api_key_hash": "9ab44a...",
  "tags": ["suporte", "ecommerce"],
  "created_at": "2026-04-25T18:00:00+00:00",
  "updated_at": "2026-04-25T18:00:00+00:00",
  "active_since": null,
  "last_activity_at": null
}
```

### `context/current.json`

Versão atual do contexto do agente. Persistida no `POST /agent` e atualizada no `PUT /agent/context`. O campo `version` é incrementado a cada atualização.

```json
{
  "agent_id": "d9f53d15-...",
  "version": 2,
  "context": {
    "tone": "formal",
    "language": "pt-BR",
    "segment": "ecommerce",
    "persona": "Ana",
    "behavior": "Responda apenas sobre pedidos e entregas.",
    "fallback_message": "Não consegui entender, pode reformular?",
    "restrictions": { "topics": ["política interna"], "files": [] },
    "knowledge_base": { "urls": ["https://meusite.com/faq"], "files": [] },
    "escalation_trigger": { "operator": "OR", "conditions": [] }
  },
  "changes": ["tone", "behavior"],
  "updated_at": "2026-04-27T10:00:00+00:00"
}
```

### `context/history/v{n}.json`

Snapshot imutável de cada versão do contexto. Mesmo schema de `current.json`. Permite auditar mudanças de comportamento do agente ao longo do tempo via `GET /agent/context/history`.

### `chats/{session_id}/session.json`

Metadados da sessão. Criado quando `POST /chat/{session_id}/end` é chamado.

```json
{
  "session_id": "abc123",
  "agent_id": "d9f53d15-...",
  "user_id": "user_456",
  "model": "groq/llama-3.3-70b-versatile",
  "started_at": "2026-04-25T18:00:00+00:00",
  "ended_at": "2026-04-25T18:12:00+00:00",
  "total_messages": 8,
  "input_tokens": 980,
  "output_tokens": 660,
  "total_tokens": 1640,
  "resolved": true,
  "escalated": false
}
```

### `chats/{session_id}/scores.json`

Scores NLP acumulados durante a sessão pelo `quality_analyzer`. Criado junto com `session.json` ao encerrar a sessão.

```json
{
  "session_id": "abc123",
  "messages": [
    {
      "message_id": "msg_001",
      "role": "user",
      "text_length": 32,
      "sentiment_score": 0.1,
      "sentiment_label": "positive",
      "topics": ["entrega"],
      "intent": "track order"
    }
  ],
  "avg_sentiment_score": -0.3,
  "sentiment_label": "negative",
  "all_topics": ["entrega", "prazo", "atraso"],
  "main_topic": "atraso",
  "intent": "reembolso",
  "avg_user_message_length": 42.0,
  "updated_at": "2026-04-25T18:12:00+00:00"
}
```

### `chats/{session_id}/insights.json`

Gerado pela IA sob demanda via `GET /data/chat/{session_id}/insights` ou `GET /data/chat/{session_id}/insights/suggestions`. Persistido após a primeira geração para evitar reprocessamento.

```json
{
  "session_id": "abc123",
  "generated_at": "2026-04-25T18:15:00+00:00",
  "key_points": [
    "Cliente insatisfeito com prazo",
    "Pedido atrasado 3 dias"
  ],
  "suggested_actions": [
    "Oferecer reembolso parcial",
    "Acionar equipe de logística"
  ],
  "summary": "Cliente contatou suporte sobre atraso em pedido. Sentimento deteriorou progressivamente até escalonamento."
}
```

---

<a id="contexto-dos-agentes"></a>
## Contexto dos Agentes

### Campos do contexto

| Campo | Tipo | Descrição |
|---|---|---|
| `tone` | string | Tom da conversa: `formal`, `informal`, `neutro` |
| `language` | string | Idioma das respostas (ex: `pt-BR`, `en-US`) |
| `segment` | string | Segmento de negócio (ex: `ecommerce`, `saas`) |
| `persona` | string | Nome que a IA usará nas respostas |
| `behavior` | string | Instrução livre de comportamento da IA |
| `restrictions.topics` | array | Tópicos que a IA não deve abordar |
| `restrictions.files` | array | Arquivos cujo conteúdo define restrições |
| `fallback_message` | string | Mensagem padrão quando a IA não souber responder |
| `knowledge_base.urls` | array | URLs de referência para a IA |
| `knowledge_base.files` | array | Arquivos de referência para a IA |
| `tags` | array | Categorias do agente para organização |
| `version` | int | Versão do contexto, incrementada a cada `PUT /agent` |

### Escalation Trigger

| Tipo | Descrição |
|---|---|
| `keyword` | Palavras ou frases que disparam escalonamento |
| `sentiment` | Sentimento negativo acima de um threshold (0 a 1) |
| `message_count` | Número máximo de mensagens sem resolução |
| `topic` | Assuntos que sempre vão para atendimento humano |
| `time_elapsed` | Tempo em segundos sem resolução |
| `intent` | Intenções detectadas pela IA |

---

<a id="cache-redis"></a>
## Cache Redis

O Redis é obrigatório e atua como camada de acesso rápido entre o `POST /chat` e o storage durável. Mantém em memória tudo que é necessário para o ciclo de vida de uma sessão, evitando I/O de disco ou queries ao banco a cada requisição.

### O que é armazenado

| Chave | Estrutura | TTL | Descrição |
|---|---|---|---|
| `agent:{agent_id}:context` | String | sem TTL fixo | `context.xml` do agente — invalidado no `PUT /agent/context` |
| `session:{session_id}:history` | List | `SESSION_TTL` | histórico de mensagens da sessão (RPUSH por mensagem) |
| `session:{session_id}:scores` | String (JSON) | `SESSION_TTL` | scores NLP acumulados pelo `quality_analyzer` |
| `session:{session_id}:meta` | Hash | `SESSION_TTL` | metadados da sessão: `agent_id`, `user_id`, timestamps, estado |

### Fluxo no `POST /chat`

```
1. Carrega context.xml do Redis          (ou storage → Redis se miss)
2. Carrega histórico da sessão do Redis
3. Envia contexto + histórico para o modelo via ai_client
4. Adiciona mensagens ao histórico via RPUSH  (renova TTL)
5. quality_analyzer atualiza scores no Redis
```

### Encerramento de sessão

Quando `POST /chat/{session_id}/end` é chamado, os dados são persistidos no storage durável e as chaves da sessão são removidas do Redis via `delete_session()`, liberando memória imediatamente.

### Formatos de URL suportados

```
redis://localhost:6379                  # local sem auth
redis://:senha@localhost:6379           # com senha
rediss://user:senha@host:6380           # TLS (Upstash, Redis Cloud, ElastiCache)
unix:///caminho/para/socket             # socket Unix
```

---

<a id="análise-local-de-conversas"></a>
## Análise Local de Conversas

As rotas de insights são divididas em dois grupos quanto ao consumo de tokens:

| Rota | Consome tokens |
|---|---|
| `GET .../insights/sentiment` | ❌ — gerado por `textblob` |
| `GET .../insights/topics` | ❌ — gerado por `spaCy` |
| `GET .../insights/metrics` | ❌ — calculado localmente |
| `GET .../insights/suggestions` | ✅ — gerado pela IA |
| `GET .../insights` | ✅ — inclui análise da IA |

Os scores locais são gerados automaticamente durante o `POST /chat` e armazenados em `scores.json`. Quando a IA for acionada, ela recebe esses scores como entrada em vez da conversa completa, minimizando o contexto necessário.

---

<a id="requisitos"></a>
## Requisitos

```
# Core
fastapi
uvicorn

# IA
litellm

# Validação e configuração
pydantic
python-dotenv

# Rate limiting
slowapi

# Cache
redis

# Análise local de conversas
textblob
spacy

# Extração de texto de arquivos
pdfplumber

# Logs
loguru

# Testes
pytest
httpx
```

---

<a id="instalação"></a>
## Instalação

### Com Docker (recomendado)

```bash
docker compose up
```

### Manual

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

### Variáveis de ambiente

Copie o arquivo de exemplo e preencha com seus valores:

```bash
cp .env.example .env
```

```env
# AI Configuration
AI_API_KEY=
AI_MODEL=

# Application Settings
APP_NAME=AI-ChatBot
APP_VERSION=1.0.0
RUN_MODE=development
DEBUG=false

# Server Configuration
HOST=0.0.0.0
PORT=8000

# CORS Configuration
ALLOWED_ORIGINS=https://localhost:3000,https://seu-dominio.com

# Logging
LOG_LEVEL=INFO

# Dados
DATA_PATH=./data

# Cache Redis
REDIS_URL=redis://localhost:6379
SESSION_TTL=86400
```

### Modelos suportados nativamente

O setup interativo oferece os seguintes modelos pré-configurados:

| Opção | Modelo | Provedor |
|---|---|---|
| 1 | `claude-sonnet-4` | Anthropic |
| 2 | `gpt-4o` | OpenAI |
| 3 | `gemini/gemini-2.0-flash` | Google |
| 4 | `deepseek/deepseek-chat` | DeepSeek |
| 5 | `groq/llama-3.3-70b-versatile` | Groq |

A variável `MODEL` no `.env` pode ser alterada manualmente para qualquer modelo suportado pelo [LiteLLM](https://docs.litellm.ai/docs/providers). O funcionamento perfeito é garantido apenas para os modelos listados acima — modelos externos à lista são compatíveis via LiteLLM mas não são testados oficialmente pelo projeto.

### Setup interativo

Alternativa ao preenchimento manual do `.env`. Guia o desenvolvedor passo a passo, valida a API Key diretamente no provedor antes de gravar e gera o `.env` automaticamente:

```bash
python tools/setup.py
```

---

## Licença

MIT — livre para usar, modificar e distribuir.