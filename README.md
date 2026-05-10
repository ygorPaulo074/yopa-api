# AI-ChatBot — Conversational AI API

Open source conversational API built with FastAPI and LiteLLM. Abstracts the complexity of AI provider communication, context management and session tracking behind a simple HTTP interface. Provider-agnostic — supports Anthropic, OpenAI, Gemini, DeepSeek, Groq and any model supported by LiteLLM.

Designed to run standalone (self-hosted, direct auth) or behind the Yopa Proxy (managed SaaS, proxy-injected auth).

---

## Index

- [Quick Start](#quick-start)
- [Authentication](#authentication)
- [Agent](#agent)
- [Chat](#chat)
- [Knowledge Base](#knowledge-base)
- [Data & Analytics](#data--analytics)
- [Admin](#admin)
- [Chat UI](#chat-ui)
- [Configuration](#configuration)
- [Self-hosted Deploy](#self-hosted-deploy)
- [Storage](#storage)
- [Redis Cache](#redis-cache)
- [NLP Analysis](#nlp-analysis)

---

## Quick Start

```bash
cp .env.example .env
# Edit .env: set at minimum AI_MODEL and AI_API_KEY (or configure per agent via POST /agent)
# Generate SQL_ENCRYPTION_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn main:app --reload
```

Or with Docker:
```bash
docker compose up
```

For a production self-hosted deploy with Caddy and automatic TLS, see [Self-hosted Deploy](#self-hosted-deploy).

---

## Authentication

Two modes, controlled by `AUTH_MODE` in `.env`:

### `AUTH_MODE=standalone` (default)

Used for direct deploys without the Yopa Proxy. All agent routes require:

```
Authorization: Bearer {agent_id}.{secret}
```

The API key is returned once at agent creation and never again.

### `AUTH_MODE=internal`

Used when the API runs behind the Yopa Proxy. The proxy validates the client's `api_key`, then injects:

```
X-Internal-Token: <shared secret>
X-Agent-Id: <agent_id>
```

The API validates `X-Internal-Token` and reads `X-Agent-Id` directly — no credential lookup per request. Requires `INTERNAL_TOKEN` to be set in `.env`; startup fails with a clear error if it isn't.

---

## Agent

### `POST /agent`

Creates an agent with its initial context. Returns the API key — this is the only time it is returned.

**Request:**
```json
{
  "name": "Support Assistant",
  "owner": "company_id",
  "context": {
    "tone": "formal",
    "language": "pt-BR",
    "segment": "ecommerce",
    "persona": "Ana",
    "behavior": "Answer only about orders and deliveries.",
    "fallback_message": "I couldn't understand. Could you rephrase?",
    "restrictions": {
      "topics": ["internal policy", "other customers' data"]
    },
    "knowledge_base": {
      "urls": ["https://mysite.com/faq"],
      "files": []
    },
    "escalation_trigger": {
      "operator": "OR",
      "conditions": [
        { "type": "keyword", "values": ["manager", "human"] },
        { "type": "sentiment", "threshold": 0.8 },
        { "type": "message_count", "value": 10 },
        { "type": "time_elapsed", "value": 300 }
      ]
    },
    "escalation_destination": {
      "type": "webhook",
      "url": "https://mysite.com/escalation",
      "token": "secret"
    }
  },
  "ai_model": "groq/llama-3.3-70b-versatile",
  "ai_api_key": "gsk_..."
}
```

`ai_model` and `ai_api_key` are optional (BYOK — Bring Your Own Key). If omitted, the agent uses the global `AI_MODEL` / `AI_API_KEY` from `.env`. The key is encrypted with Fernet before storage.

**Response:**
```json
{
  "agent_id": "d9f53d15-...",
  "api_key": "d9f53d15-....secret",
  "created_at": "2026-05-01T18:00:00Z"
}
```

---

### `GET /agent`

Returns the authenticated agent's data.

**Response:**
```json
{
  "agent_id": "d9f53d15-...",
  "name": "Support Assistant",
  "owner": "company_id",
  "created_at": "2026-05-01T18:00:00Z",
  "updated_at": "2026-05-01T18:00:00Z",
  "active_since": "2026-05-01T18:00:00Z",
  "last_activity_at": "2026-05-03T14:00:00Z",
  "ai_model": "groq/llama-3.3-70b-versatile",
  "ai_validated": true
}
```

---

### `PATCH /agent`

Updates the agent's name.

**Request:**
```json
{ "name": "New Name" }
```

---

### `GET /agent/context`

Returns the current context with version number.

---

### `GET /agent/context/history`

Returns the list of context versions and which fields changed in each.

---

### `PUT /agent/context`

Replaces the agent's context, increments version, and regenerates the system prompt in Redis.

---

### `GET /agent/metrics`

Returns aggregated session and message metrics.

---

### `DELETE /agent`

Soft-deletes the agent and all associated data.

---

### `POST /agent/validate-ai`

Tests the connection to the AI provider using the agent's configured credentials. On success, marks `ai_validated=true` on the agent record.

**Response:**
```json
{ "valid": true, "model": "groq/llama-3.3-70b-versatile" }
```

---

### `POST /agent/validate-sql`

Validates a SQL connection string — dialect allowlist, connectivity check, and table listing.

**Request:** `{ "connection_string": "postgresql://user:pass@host/db" }`

---

### `POST /agent/parse-context`

Parses a free-text description into a structured `AgentContext` using the AI model.

**Request:** `{ "text": "A formal support bot for e-commerce that escalates after 10 messages." }`

---

## Chat

### `POST /chat`

Sends a message to the agent's AI. If `session_id` is omitted, the server creates a new session and returns it — the client uses the returned `session_id` for all subsequent messages in the same conversation.

**Request:**
```json
{
  "session_id": "abc123",
  "user_id": "user_456",
  "message": "What is the delivery deadline?"
}
```

`session_id` is optional. Omitting it starts a new session.

**Response:**
```json
{
  "session": {
    "session_id": "abc123",
    "agent_id": "d9f53d15-...",
    "model": "groq/llama-3.3-70b-versatile",
    "started_at": "2026-05-01T18:00:00Z",
    "response_time_ms": 340,
    "tokens": { "input": 120, "output": 85, "total": 205 }
  },
  "conversation": [
    {
      "message": {
        "id": "msg_001",
        "role": "user",
        "content": "What is the delivery deadline?",
        "timestamp": "2026-05-01T18:00:00Z",
        "status": "delivered"
      }
    },
    {
      "message": {
        "id": "msg_002",
        "role": "assistant",
        "content": "The deadline is 5 business days.",
        "timestamp": "2026-05-01T18:00:01Z",
        "status": "delivered",
        "tokens": 18,
        "response_time_ms": 340
      }
    }
  ]
}
```

### Session lifecycle

| Endpoint | Description |
|---|---|
| `POST /chat/{session_id}/end` | Persists session to durable storage and frees Redis memory |
| `POST /chat/{session_id}/resolve` | Marks session as resolved by AI (no human escalation) |
| `POST /chat/{session_id}/escalate` | Triggers manual escalation to the configured destination |

---

## Knowledge Base

Files and URLs indexed per agent, used as tool-call context during chat.

| Endpoint | Description |
|---|---|
| `POST /agent/knowledge/upload` | Uploads a file (PDF, DOCX, TXT, CSV, JSON, Excel) |
| `POST /agent/knowledge/fetch-url` | Indexes a URL's content |
| `GET /agent/knowledge` | Lists all indexed documents |
| `DELETE /agent/knowledge/{file_id}` | Removes an indexed document |

---

## Data & Analytics

All routes require agent authentication. Analytics are powered by the NLP scores generated locally during each `POST /chat` — no tokens consumed except for `insights/suggestions`.

### Sessions

| Endpoint | Description |
|---|---|
| `GET /data/chat` | Lists all sessions |
| `GET /data/chat/{session_id}` | Full conversation history |
| `DELETE /data/chat/{session_id}` | Soft-deletes a session |

### Insights (per session)

| Endpoint | Tokens |
|---|---|
| `GET /data/chat/{session_id}/insights` | ✅ includes AI analysis |
| `GET /data/chat/{session_id}/insights/sentiment` | ❌ local NLP |
| `GET /data/chat/{session_id}/insights/topics` | ❌ local NLP |
| `GET /data/chat/{session_id}/insights/metrics` | ❌ local NLP |
| `GET /data/chat/{session_id}/insights/suggestions` | ✅ AI only |

### Analytics (aggregated)

All accept optional `?from=` and `?to=` (ISO date strings).

| Endpoint | Description |
|---|---|
| `GET /data/analytics` | Full analytics payload |
| `GET /data/analytics/summary` | Totals and rates |
| `GET /data/analytics/patterns` | Topic patterns, peak hours |
| `GET /data/analytics/sentiment` | Sentiment distribution |
| `GET /data/analytics/users` | User segmentation |
| `GET /data/analytics/timeline` | Daily metrics |

### User context

| Endpoint | Description |
|---|---|
| `GET /data/context` | All user profiles for the agent |
| `GET /data/context/{user_id}` | Single user profile |
| `DELETE /data/context/{user_id}` | Removes user profile |

---

## Admin

These routes are not exposed to end users.

### `GET /health`

Serves an HTML dashboard showing live server status (version, uptime, storage driver) and a table of the last 20 health checks. Auto-refreshes every 15 seconds. No authentication required.

```
http://localhost:8000/health
```

### `GET /health/status`

JSON endpoint polled by the dashboard above. Also usable for external monitoring.

```json
{
  "status": "ok",
  "version": "0.1.0",
  "started_at": "2026-05-10T12:00:00+00:00",
  "uptime_seconds": 3600.0,
  "storage": "database",
  "recent_checks": [
    { "timestamp": "...", "status": "ok", "uptime_seconds": 3600.0 }
  ]
}
```

### `POST /admin/purge`

Hard-deletes agents and sessions with `deleted_at` before the given date. Requires `X-Internal-Token` header.

**Request:** `{ "before": "2026-04-01T00:00:00Z" }`

**Response:** `{ "agents_purged": 3, "sessions_purged": 47 }`

In a managed Yopa deployment, the Proxy runs this on a 7-day cron. In standalone mode, call it manually when needed.

---

## Development routes

> **Only active when `RUN_MODE=development`.** All `/dev/*` routes and `/agent-manager` return `403 Forbidden` in production.

### `GET /agent-manager`

Full agent management UI — lists all agents, lets you chat with any one, inspect sessions, and view aggregate analytics. Opens in the browser:

```
http://localhost:8000/agent-manager
```

Selecting an agent rotates its API key and stores the new bearer token in memory for the session. Existing tokens for that agent are invalidated.

### `GET /dev/agents`

Lists all active (non-deleted) agents.

```json
[
  {
    "agent_id": "...",
    "name": "Support Bot",
    "owner": "acme",
    "ai_model": "groq/llama-3.3-70b-versatile",
    "ai_validated": true,
    "created_at": "...",
    "active_since": "...",
    "last_activity_at": "..."
  }
]
```

### `POST /dev/token/{agent_id}`

Rotates the agent's API key and returns a new bearer token. No authentication required (dev mode only).

```json
{ "bearer_token": "{agent_id}.{new_secret}" }
```

---

## Chat UI

> **Development only.** Not listed in the OpenAPI schema (`/docs`).

`GET /chat-ui` serves a browser-based chat interface for testing agents without any external client. Open it directly after starting the API:

```
http://localhost:8000/chat-ui
```

Features:
- Send messages and see AI responses in real time
- Sidebar listing past sessions for the authenticated agent
- Requires the same Bearer token used by the REST API (`Authorization: Bearer {agent_id}.{secret}`)

Do not expose this route in production — it has no rate limiting or CSRF protection.

---

## Configuration

Copy `.env.example` to `.env`:

```env
# AI provider fallback — can be left empty if all agents use BYOK
AI_API_KEY=
AI_MODEL=

AI_TIMEOUT=30

# App
APP_NAME=AI-ChatBot
RUN_MODE=development
HOST=0.0.0.0
PORT=8000

# Redis (required)
REDIS_URL=redis://localhost:6379
SESSION_TTL=86400

# Storage: local | database | webhook
STORAGE_TYPE=local
DATA_PATH=./data

# Database (required if STORAGE_TYPE=database)
DATABASE_URL=
DB_USER=
DB_PASSWORD=
DB_NAME=

# Encryption key for SQL credentials and ai_api_key (Fernet)
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SQL_ENCRYPTION_KEY=

# Auth
AUTH_MODE=standalone
INTERNAL_TOKEN=

# NLP
ANALYZER_LANGUAGES=["en"]

# SQL tool safety
SQL_ALLOWED_DIALECTS=["postgresql","mysql","sqlite"]
SQL_QUERY_TIMEOUT=10
SQL_MAX_ROWS=50

MAX_TOOL_ROUNDS=5
LOG_LEVEL=INFO
```

### Versioning

The canonical version lives in `VERSION`. It propagates automatically to:

- Docker image tag: `ai-chatbot-api:<VERSION>` (set in `docker-compose.yml` via `APP_VERSION`)
- `GET /health/status` JSON response
- `.env` `APP_VERSION` field (written by `inv setup`)

**Bumping the version**

```bash
echo "0.2.0" > VERSION
# rebuild — inv setup will detect the new tag and build automatically
inv docker-build          # or: inv setup → Docker → build
```

**Old image cleanup**

The API image is large (PyTorch, spaCy models). `inv setup` will prompt you after each new build whether to remove old tagged images or keep them for rollback. To clean up manually:

```bash
docker images ai-chatbot-api          # list all tagged versions
docker rmi ai-chatbot-api:0.1.0       # remove a specific version
docker image prune                    # remove untagged dangling layers
```

---

### Supported models

Any model supported by [LiteLLM](https://docs.litellm.ai/docs/providers). Common examples:

| Provider | Model string |
|---|---|
| Anthropic | `claude-sonnet-4-5` |
| OpenAI | `gpt-4o` |
| Google | `gemini/gemini-2.0-flash` |
| DeepSeek | `deepseek/deepseek-chat` |
| Groq | `groq/llama-3.3-70b-versatile` |

---

## Self-hosted Deploy

Uses `docker-compose.selfhosted.yml` — Caddy handles HTTPS automatically via Let's Encrypt.

```bash
# 1. Configure domain
nano Caddyfile.selfhosted   # replace your-domain.com

# 2. Set env
cp .env.example .env
nano .env

# 3. Start
docker compose -f docker-compose.selfhosted.yml up -d
```

PostgreSQL is optional — uncomment the `db` service block in `docker-compose.selfhosted.yml` and set `STORAGE_TYPE=database` in `.env`.

---

## Storage

Three drivers, selected by `STORAGE_TYPE` in `.env`:

| Driver | Config | Use case |
|---|---|---|
| `local` | `DATA_PATH` | Default — JSON files, zero infrastructure |
| `database` | `DATABASE_URL` | PostgreSQL — recommended for production |
| `webhook` | `WEBHOOK_URL` | Forward all persistence operations to an external HTTP endpoint |

### Data layout (local driver)

```
data/agents/{agent_id}/
├── agent.json
├── context/
│   ├── current.json
│   └── history/v{n}.json
├── users/{user_id}.json
├── skills/skill.json
└── chats/{session_id}/
    ├── session.json
    ├── scores.json
    └── insights.json
```

Sessions are written incrementally to disk on every `POST /chat` (snapshot pattern). `POST /chat/{session_id}/end` also flushes history from Redis to disk.

---

## Redis Cache

Required. Holds all live session state — no disk I/O per message.

| Key | TTL | Contents |
|---|---|---|
| `agent:{id}:context` | none | Compiled system prompt (invalidated on context update) |
| `session:{id}:history` | `SESSION_TTL` | Message list |
| `session:{id}:scores` | `SESSION_TTL` | NLP scores |
| `session:{id}:meta` | `SESSION_TTL` | Session metadata |

Supported URL formats:
```
redis://localhost:6379
redis://:password@localhost:6379
rediss://user:password@host:6380   # TLS
unix:///path/to/socket
```

---

## NLP Analysis

Scores are generated locally during every `POST /chat` — no tokens consumed.

| Capability | Library |
|---|---|
| Sentiment scoring | TextBlob |
| Topic extraction | spaCy + TF-IDF |
| Intent detection | spaCy |
| Language detection | langdetect |

spaCy models must be installed manually:
```bash
python -m spacy download en_core_web_sm
python -m spacy download pt_core_news_sm
```

---

## License

MIT
