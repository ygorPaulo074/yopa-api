# Project Insights

## Snapshot

Current project health: **7.5/10**.

The codebase has a solid product shape: FastAPI routes are grouped by interface concern, core business concepts live in `domain`, orchestration lives in `application/services`, and infrastructure details are isolated behind persistence, cache, AI and ingestion modules. The agent lifecycle, context versioning, BYOK model/key support, Redis-backed live sessions and pluggable persistence are strong foundations.

The main risks are not conceptual. They are mostly consolidation issues: stale documentation, duplicated dev routes, oversized route modules, and some dev-only behavior that needs to stay clearly separated from production analytics.

## Recent Decisions

### `/agent-test` Is The Canonical Test UI

The code now treats `GET /agent-test` as the development UI route. Older README references to `/agent-manager` and `/chat-ui` were stale and should not be reintroduced unless matching routes are added intentionally.

The UI route belongs in `src/interfaces/http/routes/dev.py` because it is development-only and guarded by `RUN_MODE=development`.

### Ephemeral Agents Stay Redis-Only

Ephemeral agents are intentionally not persisted through the configured storage driver. They live in Redis and expire with their TTL. This keeps test data from polluting durable analytics and production-like dashboards.

To still make ephemeral testing useful, development-only endpoints expose temporary sessions and analytics from Redis:

- `GET /dev/agent/ephemeral/sessions`
- `GET /dev/agent/ephemeral/sessions/{session_id}`
- `GET /dev/agent/ephemeral/analytics`

These endpoints require the ephemeral agent Bearer token and are guarded by `RUN_MODE=development`.

### Analytics Belongs In A Service

`src/application/services/analytics_service.py` is now the shared aggregation layer for durable and ephemeral analytics. Route modules should not rebuild analytics DTOs inline. They should authenticate, validate, and delegate.

This keeps `/data/*` and `/dev/*` behavior consistent while preserving the important distinction:

- `/data/*` reads durable sessions through the persistence driver.
- `/dev/agent/ephemeral/*` reads live temporary sessions from Redis.

## Architecture Notes

### Cache Keys

Redis currently stores:

- `agent:{id}:context`: compiled system prompt.
- `agent:{id}:ephemeral`: ephemeral agent metadata and secret hash.
- `agent:{id}:ephemeral:sessions`: Redis set of session ids for ephemeral analytics.
- `session:{id}:history`: live message history.
- `session:{id}:meta`: live session metadata.
- `session:{id}:scores`: local NLP analysis data.

The session index is the key addition that makes ephemeral analytics discoverable without querying durable storage.

### Route Boundaries

Keep these boundaries crisp:

- `src/interfaces/http/routes/*`: HTTP concerns, status codes, authentication dependencies, response models.
- `src/application/services/*`: orchestration and aggregation.
- `src/infrastructure/*`: external systems and implementation details.
- `src/domain/*`: Pydantic domain entities and shared business structures.

When a route starts accumulating loops, counters, DTO building or cross-source fallback logic, that logic probably belongs in a service.

## Operational Notes

### Docker Rebuilds

The container serves files baked into the image. After changing Python files or `src/static/chat.html`, rebuild before verifying through Docker:

```bash
docker compose up --build
```

If `/agent-test` appears stale, compare the HTML markers served by the container against the workspace file before debugging application logic.

### Development Mode

The test UI and `/dev/*` endpoints assume:

```env
RUN_MODE=development
```

Outside development mode, they should return `403`. Do not expose these routes in production; they rotate agent tokens and expose test helpers.

## Recommended Next Work

1. Add tests for ephemeral flows:
   - create ephemeral agent;
   - authenticate with its token;
   - chat creates Redis session index;
   - `/dev/agent/ephemeral/sessions` lists it;
   - `/dev/agent/ephemeral/analytics` aggregates it.

2. Add tests for `AnalyticsService` directly with synthetic `SessionMeta`, `SessionRecord` and `ScoreData`.

3. Consider typed response schemas for ephemeral session detail if the dev endpoint stabilizes. It currently returns a useful combined shape for the UI.

4. Keep README route examples synchronized with actual FastAPI routes. A small route inventory test could catch stale docs over time.

5. If the static UI continues to grow, consider splitting it into a tiny frontend build or at least separate CSS/JS files. For an internal dev tool, the current single-file approach is acceptable but nearing its comfort limit.
