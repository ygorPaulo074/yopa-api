"""
Geração de artefatos de deployment: SQL, Prisma, Dockerfile, docker-compose.yml.
Chamado pelo setup.py ao finalizar a configuração inicial.
"""
import os


# ── SQL Schema ─────────────────────────────────────────────────────────────────

def create_sql_scripts():
    sql_script = """-- =============================================================
-- Chatbot API — Schema SQL
-- PostgreSQL 14+
-- =============================================================

-- agents
CREATE TABLE agents (
    agent_id          VARCHAR(64)   PRIMARY KEY,
    name              VARCHAR(255)  NOT NULL,
    owner             VARCHAR(64)   NOT NULL,
    api_key_hash      VARCHAR(64)   NOT NULL UNIQUE,
    tags              JSONB         NOT NULL DEFAULT '[]',
    created_at        TIMESTAMP     NOT NULL,
    updated_at        TIMESTAMP     NOT NULL,
    active_since      TIMESTAMP,
    last_activity_at  TIMESTAMP
);

-- agent_contexts (one row per version; current = MAX(version))
CREATE TABLE agent_contexts (
    id          SERIAL        PRIMARY KEY,
    agent_id    VARCHAR(64)   NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    version     INTEGER       NOT NULL DEFAULT 1,
    context     JSONB         NOT NULL DEFAULT '{}',
    changes     JSONB         NOT NULL DEFAULT '[]',
    updated_at  TIMESTAMP     NOT NULL,
    UNIQUE (agent_id, version)
);

-- user_contexts (one row per user+agent)
CREATE TABLE user_contexts (
    id           SERIAL        PRIMARY KEY,
    user_id      VARCHAR(64)   NOT NULL,
    agent_id     VARCHAR(64)   NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    created_at   TIMESTAMP     NOT NULL,
    updated_at   TIMESTAMP     NOT NULL,
    segment      VARCHAR(128),
    language     VARCHAR(16),
    form_answers JSONB,
    UNIQUE (user_id, agent_id)
);

-- sessions
CREATE TABLE sessions (
    session_id      VARCHAR(64)   PRIMARY KEY,
    agent_id        VARCHAR(64)   NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    user_id         VARCHAR(64),
    model           VARCHAR(64)   NOT NULL,
    started_at      TIMESTAMP     NOT NULL,
    ended_at        TIMESTAMP,
    total_messages  INTEGER       NOT NULL DEFAULT 0,
    input_tokens    INTEGER       NOT NULL DEFAULT 0,
    output_tokens   INTEGER       NOT NULL DEFAULT 0,
    total_tokens    INTEGER       NOT NULL DEFAULT 0,
    resolved        BOOLEAN       NOT NULL DEFAULT FALSE,
    escalated       BOOLEAN       NOT NULL DEFAULT FALSE
);

-- session_history (full message history, persisted on session end)
CREATE TABLE session_history (
    session_id  VARCHAR(64)  PRIMARY KEY REFERENCES sessions(session_id) ON DELETE CASCADE,
    agent_id    VARCHAR(64)  NOT NULL,
    messages    JSONB        NOT NULL DEFAULT '[]'
);

-- scores (NLP scores aggregated per session)
CREATE TABLE scores (
    session_id              VARCHAR(64)   PRIMARY KEY REFERENCES sessions(session_id) ON DELETE CASCADE,
    agent_id                VARCHAR(64)   NOT NULL,
    messages                JSONB         NOT NULL DEFAULT '[]',
    avg_sentiment_score     FLOAT,
    sentiment_label         VARCHAR(16)   CHECK (sentiment_label IN ('positive', 'neutral', 'negative')),
    all_topics              JSONB,
    main_topic              VARCHAR(255),
    intent                  VARCHAR(128),
    avg_user_message_length FLOAT,
    updated_at              TIMESTAMP     NOT NULL
);

-- insights (AI-generated, on demand)
CREATE TABLE insights (
    session_id        VARCHAR(64)   PRIMARY KEY REFERENCES sessions(session_id) ON DELETE CASCADE,
    agent_id          VARCHAR(64)   NOT NULL,
    generated_at      TIMESTAMP     NOT NULL,
    key_points        JSONB,
    suggested_actions JSONB,
    summary           TEXT
);

-- knowledge_files (uploaded knowledge base files per agent)
CREATE TABLE knowledge_files (
    file_id     VARCHAR(64)   PRIMARY KEY,
    agent_id    VARCHAR(64)   NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    filename    VARCHAR(255)  NOT NULL,
    file_type   VARCHAR(16)   NOT NULL CHECK (file_type IN ('csv', 'json', 'pdf', 'excel')),
    records     JSONB         NOT NULL DEFAULT '[]',
    uploaded_at TIMESTAMP     NOT NULL,
    updated_at  TIMESTAMP     NOT NULL
);

-- Indexes
CREATE INDEX idx_agent_contexts_agent_id   ON agent_contexts(agent_id);
CREATE INDEX idx_user_contexts_agent_id    ON user_contexts(agent_id);
CREATE INDEX idx_user_contexts_user_id     ON user_contexts(user_id);
CREATE INDEX idx_sessions_agent_id         ON sessions(agent_id);
CREATE INDEX idx_sessions_user_id          ON sessions(user_id);
CREATE INDEX idx_session_history_agent_id  ON session_history(agent_id);
CREATE INDEX idx_scores_agent_id           ON scores(agent_id);
CREATE INDEX idx_insights_agent_id         ON insights(agent_id);
CREATE INDEX idx_knowledge_files_agent_id  ON knowledge_files(agent_id);
"""
    os.makedirs("scripts", exist_ok=True)
    with open("scripts/schema.sql", "w") as f:
        f.write(sql_script)
    print("  ✓ scripts/schema.sql generated.")


# ── Prisma Schema ──────────────────────────────────────────────────────────────

def create_prisma_migrate():
    content = """// Chatbot API — Prisma Schema (PostgreSQL 14+)

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

enum Role           { user assistant }
enum Status         { delivered pending failed escalated }
enum SentimentLabel { positive neutral negative }

model Agent {
  agentId        String    @id @map("agent_id")
  name           String
  owner          String
  apiKeyHash     String    @unique @map("api_key_hash")
  tags           Json      @default("[]")
  createdAt      DateTime  @map("created_at")
  updatedAt      DateTime  @map("updated_at")
  activeSince    DateTime? @map("active_since")
  lastActivityAt DateTime? @map("last_activity_at")

  contexts       AgentContext[]
  sessions       Session[]
  userContexts   UserContext[]
  knowledgeFiles KnowledgeFile[]

  @@map("agents")
}

model AgentContext {
  id        Int      @id @default(autoincrement())
  agentId   String   @map("agent_id")
  version   Int      @default(1)
  context   Json     @default("{}")
  changes   Json     @default("[]")
  updatedAt DateTime @map("updated_at")
  agent Agent @relation(fields: [agentId], references: [agentId], onDelete: Cascade)
  @@unique([agentId, version])
  @@map("agent_contexts")
}

model UserContext {
  id          Int      @id @default(autoincrement())
  userId      String   @map("user_id")
  agentId     String   @map("agent_id")
  createdAt   DateTime @map("created_at")
  updatedAt   DateTime @map("updated_at")
  segment     String?
  language    String?
  formAnswers Json?    @map("form_answers")
  agent Agent @relation(fields: [agentId], references: [agentId], onDelete: Cascade)
  @@unique([userId, agentId])
  @@map("user_contexts")
}

model Session {
  sessionId     String    @id @map("session_id")
  agentId       String    @map("agent_id")
  userId        String?   @map("user_id")
  model         String
  startedAt     DateTime  @map("started_at")
  endedAt       DateTime? @map("ended_at")
  totalMessages Int       @default(0) @map("total_messages")
  inputTokens   Int       @default(0) @map("input_tokens")
  outputTokens  Int       @default(0) @map("output_tokens")
  totalTokens   Int       @default(0) @map("total_tokens")
  resolved      Boolean   @default(false)
  escalated     Boolean   @default(false)
  agent   Agent          @relation(fields: [agentId], references: [agentId], onDelete: Cascade)
  history SessionHistory?
  scores  Score?
  insight Insight?
  @@map("sessions")
}

model SessionHistory {
  sessionId String @id @map("session_id")
  agentId   String @map("agent_id")
  messages  Json   @default("[]")
  session Session @relation(fields: [sessionId], references: [sessionId], onDelete: Cascade)
  @@map("session_history")
}

model Score {
  sessionId            String          @id @map("session_id")
  agentId              String          @map("agent_id")
  messages             Json            @default("[]")
  avgSentimentScore    Float?          @map("avg_sentiment_score")
  sentimentLabel       SentimentLabel? @map("sentiment_label")
  allTopics            Json?           @map("all_topics")
  mainTopic            String?         @map("main_topic")
  intent               String?
  avgUserMessageLength Float?          @map("avg_user_message_length")
  updatedAt            DateTime        @map("updated_at")
  session Session @relation(fields: [sessionId], references: [sessionId], onDelete: Cascade)
  @@map("scores")
}

model Insight {
  sessionId        String   @id @map("session_id")
  agentId          String   @map("agent_id")
  generatedAt      DateTime @map("generated_at")
  keyPoints        Json?    @map("key_points")
  suggestedActions Json?    @map("suggested_actions")
  summary          String?
  session Session @relation(fields: [sessionId], references: [sessionId], onDelete: Cascade)
  @@map("insights")
}

model KnowledgeFile {
  fileId     String   @id @map("file_id")
  agentId    String   @map("agent_id")
  filename   String
  fileType   String   @map("file_type")
  records    Json     @default("[]")
  uploadedAt DateTime @map("uploaded_at")
  updatedAt  DateTime @map("updated_at")
  agent Agent @relation(fields: [agentId], references: [agentId], onDelete: Cascade)
  @@map("knowledge_files")
}
"""
    os.makedirs("scripts", exist_ok=True)
    with open("scripts/schema.prisma", "w") as f:
        f.write(content)
    print("  ✓ scripts/schema.prisma generated.")


# ── Dockerfile ─────────────────────────────────────────────────────────────────

def generate_dockerfile(port: str = "8000") -> None:
    content = f"""FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm

COPY . .

ENV RUN_MODE=production

EXPOSE {port}
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port}"]
"""
    with open("Dockerfile", "w") as f:
        f.write(content)
    print("  ✓ Dockerfile generated.")


# ── Docker Compose ─────────────────────────────────────────────────────────────

def generate_docker_compose(port: str = "8000", storage_type: str = "Local") -> None:
    """API + Redis. Optionally adds PostgreSQL when storage_type is Database."""
    db_block = ""
    db_depends = ""
    db_volume = ""

    if storage_type == "Database":
        db_block = """
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    volumes:
      - db_data:/var/lib/postgresql/data
      - ./scripts/schema.sql:/docker-entrypoint-initdb.d/schema.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${DB_USER} -d $${DB_NAME}"]
      interval: 10s
      timeout: 5s
      retries: 5
"""
        db_depends = "\n      - db"
        db_volume = "  db_data:\n"

    content = f"""services:
  api:
    build: .
    ports:
      - "{port}:{port}"
    env_file:
      - .env
    depends_on:
      - redis{db_depends}
    restart: unless-stopped
    volumes:
      - ./data:/app/data

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data
{db_block}
volumes:
  redis_data:
{db_volume}"""
    with open("docker-compose.yml", "w") as f:
        f.write(content)
    print("  ✓ docker-compose.yml generated.")


# ── Backward compat aliases ────────────────────────────────────────────────────

def create_docker_compose_with_db():
    generate_docker_compose(storage_type="Database")
