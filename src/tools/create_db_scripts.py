import os

def create_sql_scripts():
    sql_script = """-- =============================================================
-- Chatbot API — Schema SQL
-- PostgreSQL 14+
-- =============================================================
-- NOTE: This schema is designed to match the canonical JSON
-- returned by the API. Your database must adapt to this
-- structure — not the other way around.
-- =============================================================


-- -------------------------------------------------------------
-- agents
-- -------------------------------------------------------------
CREATE TABLE agents (
    agent_id          VARCHAR(64)   PRIMARY KEY,
    name              VARCHAR(255)  NOT NULL,
    owner             VARCHAR(64)   NOT NULL,
    api_key           VARCHAR(255)  NOT NULL UNIQUE,
    tags              JSONB         NOT NULL DEFAULT '[]',
    created_at        TIMESTAMP     NOT NULL,
    updated_at        TIMESTAMP     NOT NULL,
    active_since      TIMESTAMP,
    last_activity_at  TIMESTAMP
);


-- -------------------------------------------------------------
-- agent_contexts
-- One row per version. Current version = MAX(version).
-- -------------------------------------------------------------
CREATE TABLE agent_contexts (
    id                  SERIAL        PRIMARY KEY,
    agent_id            VARCHAR(64)   NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    version             INTEGER       NOT NULL DEFAULT 1,
    tone                VARCHAR(64)   CHECK (tone IN ('formal', 'informal', 'neutro')),
    language            VARCHAR(16),
    segment             VARCHAR(128),
    persona             VARCHAR(128),
    behavior            TEXT,
    fallback_message    TEXT,
    restrictions        JSONB,        -- { topics: [], files: [] }
    knowledge_base      JSONB,        -- { urls: [], files: [] }
    escalation_trigger  JSONB,        -- { operator, conditions: [] }
    changes             JSONB,        -- array of field names changed vs previous version
    updated_at          TIMESTAMP     NOT NULL,

    UNIQUE (agent_id, version)
);


-- -------------------------------------------------------------
-- user_contexts
-- User profiles tracked per agent. One row per (user, agent).
-- Created on first interaction.
-- -------------------------------------------------------------
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


-- -------------------------------------------------------------
-- sessions
-- -------------------------------------------------------------
CREATE TABLE sessions (
    session_id      VARCHAR(64)   PRIMARY KEY,
    agent_id        VARCHAR(64)   NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
    user_id         VARCHAR(64),
    user_context_id INTEGER       REFERENCES user_contexts(id) ON DELETE SET NULL,
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


-- -------------------------------------------------------------
-- messages
-- -------------------------------------------------------------
CREATE TABLE messages (
    id                SERIAL        PRIMARY KEY,
    message_id        VARCHAR(64)   NOT NULL UNIQUE,
    session_id        VARCHAR(64)   NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role              VARCHAR(16)   NOT NULL CHECK (role IN ('user', 'assistant')),
    content           TEXT          NOT NULL,
    timestamp         TIMESTAMP     NOT NULL,
    status            VARCHAR(16)   NOT NULL CHECK (status IN ('delivered', 'pending', 'failed', 'escalated')),
    tokens            INTEGER,
    response_time_ms  INTEGER       -- only for role = 'assistant'
);


-- -------------------------------------------------------------
-- scores
-- Local NLP scores generated during POST /chat — no token cost.
-- One row per message (UNIQUE on message_id).
-- -------------------------------------------------------------
CREATE TABLE scores (
    id               SERIAL        PRIMARY KEY,
    session_id       VARCHAR(64)   NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    message_id       VARCHAR(64)   NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
    sentiment_score  FLOAT,
    sentiment_label  VARCHAR(16)   CHECK (sentiment_label IN ('positive', 'neutral', 'negative')),
    topics           JSONB,        -- array of detected topic strings
    main_topic       VARCHAR(255),
    intent           VARCHAR(128),
    created_at       TIMESTAMP     NOT NULL,

    UNIQUE (message_id)
);


-- -------------------------------------------------------------
-- insights
-- AI-generated analysis, created on demand via GET /insights.
-- -------------------------------------------------------------
CREATE TABLE insights (
    id                SERIAL        PRIMARY KEY,
    session_id        VARCHAR(64)   NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    generated_at      TIMESTAMP     NOT NULL,
    key_points        JSONB,        -- array of strings
    suggested_actions JSONB,        -- array of strings
    summary           TEXT
);


-- -------------------------------------------------------------
-- Indexes
-- -------------------------------------------------------------
CREATE INDEX idx_agent_contexts_agent_id   ON agent_contexts(agent_id);
CREATE INDEX idx_user_contexts_agent_id    ON user_contexts(agent_id);
CREATE INDEX idx_user_contexts_user_id     ON user_contexts(user_id);
CREATE INDEX idx_sessions_agent_id         ON sessions(agent_id);
CREATE INDEX idx_sessions_user_id          ON sessions(user_id);
CREATE INDEX idx_sessions_user_context_id  ON sessions(user_context_id);
CREATE INDEX idx_messages_session_id       ON messages(session_id);
CREATE INDEX idx_scores_session_id         ON scores(session_id);
CREATE INDEX idx_scores_message_id         ON scores(message_id);
CREATE INDEX idx_insights_session_id       ON insights(session_id);
"""
    with open("scripts/schema.sql", "w") as f:
        f.write(sql_script)


def create_prisma_migrate():
    prisma_migrate = """// =============================================================
// Chatbot API — Prisma Schema
// PostgreSQL 14+ (change datasource provider for other DBs)
// =============================================================
// NOTE: This schema is designed to match the canonical JSON
// returned by the API. Your database must adapt to this
// structure — not the other way around.
//
// To use:
//   1. Set DATABASE_URL in your .env
//   2. Run: npx prisma migrate dev
// =============================================================

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}


// -------------------------------------------------------------
// Agent
// -------------------------------------------------------------
model Agent {
  agentId        String    @id @map("agent_id")
  name           String
  owner          String
  apiKey         String    @unique @map("api_key")
  tags           Json      @default("[]")
  createdAt      DateTime  @map("created_at")
  updatedAt      DateTime  @map("updated_at")
  activeSince    DateTime? @map("active_since")
  lastActivityAt DateTime? @map("last_activity_at")

  contexts     AgentContext[]
  sessions     Session[]
  userContexts UserContext[]

  @@map("agents")
}


// -------------------------------------------------------------
// AgentContext
// One row per version. Current = MAX(version).
// -------------------------------------------------------------
model AgentContext {
  id                Int      @id @default(autoincrement())
  agentId           String   @map("agent_id")
  version           Int      @default(1)
  tone              Tone?
  language          String?
  segment           String?
  persona           String?
  behavior          String?
  fallbackMessage   String?  @map("fallback_message")
  restrictions      Json?    // { topics: [], files: [] }
  knowledgeBase     Json?    @map("knowledge_base")     // { urls: [], files: [] }
  escalationTrigger Json?    @map("escalation_trigger") // { operator, conditions: [] }
  changes           Json?    // array of field names changed vs previous version
  updatedAt         DateTime @map("updated_at")

  agent Agent @relation(fields: [agentId], references: [agentId], onDelete: Cascade)

  @@unique([agentId, version])
  @@map("agent_contexts")
}


// -------------------------------------------------------------
// UserContext
// User profiles tracked per agent. One row per (user, agent).
// Created on first interaction.
// -------------------------------------------------------------
model UserContext {
  id          Int      @id @default(autoincrement())
  userId      String   @map("user_id")
  agentId     String   @map("agent_id")
  createdAt   DateTime @map("created_at")
  updatedAt   DateTime @map("updated_at")
  segment     String?
  language    String?
  formAnswers Json?    @map("form_answers")

  agent    Agent     @relation(fields: [agentId], references: [agentId], onDelete: Cascade)
  sessions Session[]

  @@unique([userId, agentId])
  @@map("user_contexts")
}


// -------------------------------------------------------------
// Session
// -------------------------------------------------------------
model Session {
  sessionId       String    @id @map("session_id")
  agentId         String    @map("agent_id")
  userId          String?   @map("user_id")
  userContextId   Int?      @map("user_context_id")
  model           String
  startedAt       DateTime  @map("started_at")
  endedAt         DateTime? @map("ended_at")
  totalMessages   Int       @default(0) @map("total_messages")
  inputTokens     Int       @default(0) @map("input_tokens")
  outputTokens    Int       @default(0) @map("output_tokens")
  totalTokens     Int       @default(0) @map("total_tokens")
  resolved        Boolean   @default(false)
  escalated       Boolean   @default(false)

  agent       Agent        @relation(fields: [agentId], references: [agentId], onDelete: Cascade)
  userContext UserContext?  @relation(fields: [userContextId], references: [id], onDelete: SetNull)
  messages    Message[]
  scores      Score[]
  insights    Insight[]

  @@map("sessions")
}


// -------------------------------------------------------------
// Message
// -------------------------------------------------------------
model Message {
  id             Int      @id @default(autoincrement())
  messageId      String   @unique @map("message_id")
  sessionId      String   @map("session_id")
  role           Role
  content        String
  timestamp      DateTime
  status         Status
  tokens         Int?
  responseTimeMs Int?     @map("response_time_ms") // only for role = ASSISTANT

  session Session @relation(fields: [sessionId], references: [sessionId], onDelete: Cascade)
  score   Score?

  @@map("messages")
}

enum Role {
  user
  assistant
}

enum Status {
  delivered
  pending
  failed
  escalated
}

enum Tone {
  formal
  informal
  neutro
}

enum SentimentLabel {
  positive
  neutral
  negative
}


// -------------------------------------------------------------
// Score
// Local NLP scores generated during POST /chat — no token cost.
// One row per message.
// -------------------------------------------------------------
model Score {
  id             Int             @id @default(autoincrement())
  sessionId      String          @map("session_id")
  messageId      String          @unique @map("message_id")
  sentimentScore Float?          @map("sentiment_score")
  sentimentLabel SentimentLabel? @map("sentiment_label")
  topics         Json?           // array of detected topic strings
  mainTopic      String?         @map("main_topic")
  intent         String?
  createdAt      DateTime        @map("created_at")

  session Session @relation(fields: [sessionId], references: [sessionId], onDelete: Cascade)
  message Message @relation(fields: [messageId], references: [messageId], onDelete: Cascade)

  @@map("scores")
}


// -------------------------------------------------------------
// Insight
// AI-generated analysis, created on demand via GET /insights.
// -------------------------------------------------------------
model Insight {
  id               Int      @id @default(autoincrement())
  sessionId        String   @map("session_id")
  generatedAt      DateTime @map("generated_at")
  keyPoints        Json?    @map("key_points")        // array of strings
  suggestedActions Json?    @map("suggested_actions") // array of strings
  summary          String?

  session Session @relation(fields: [sessionId], references: [sessionId], onDelete: Cascade)

  @@map("insights")
}
"""
    with open("scripts/schema.prisma", "w") as f:
        f.write(prisma_migrate)


def generate_docker_compose():
    """docker-compose.yml — API only, no database service."""
    content = """services:
  api:
    container_name: chatbot-api
    build: .
    ports:
      - "${PORT:-8000}:${PORT:-8000}"
    env_file:
      - .env
    restart: unless-stopped
"""
    with open("docker-compose.yml", "w") as f:
        f.write(content)


def create_docker_compose_with_db():
    """docker-compose.yml — API + database, schema applied on first run."""
    content = """services:
  api:
    container_name: chatbot-api
    build: .
    ports:
      - "${PORT:-8000}:${PORT:-8000}"
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  db:
    container_name: chatbot-api-db
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/schema.sql:/docker-entrypoint-initdb.d/schema.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  postgres_data:
"""
    with open("docker-compose.yml", "w") as f:
        f.write(content)
