"""
Redis cache layer.
Centralizes access to agent context, session history, NLP scores and session
metadata. Agent context has no fixed TTL — it is invalidated explicitly on
PUT /agent/context. Sessions use a configurable TTL renewed on each message.
"""
from redis import Redis
from redis.exceptions import RedisError
from src.infrastructure.config import settings
from src.core.schemas import HistoryMessage, SessionMeta, ScoreData
from . import keys


class CacheClient:

    def __init__(self):
        self._redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)

    def ping(self) -> bool:
        try:
            return bool(self._redis.ping())
        except RedisError:
            return False

    # ── Agent context ─────────────────────────────────────────

    def get_context(self, agent_id: str) -> str | None:
        return self._redis.get(keys.context_key(agent_id))

    def set_context(self, agent_id: str, context_xml: str) -> None:
        self._redis.set(keys.context_key(agent_id), context_xml)

    def invalidate_context(self, agent_id: str) -> None:
        self._redis.delete(keys.context_key(agent_id))

    # ── Session history ───────────────────────────────────────

    def get_history(self, session_id: str) -> list[HistoryMessage]:
        raw = self._redis.lrange(keys.history_key(session_id), 0, -1)
        return [HistoryMessage.model_validate_json(item) for item in raw]

    def append_message(self, session_id: str, message: HistoryMessage, ttl: int = 0) -> None:
        resolved_ttl = ttl or settings.SESSION_TTL
        key = keys.history_key(session_id)
        with self._redis.pipeline() as pipe:
            pipe.rpush(key, message.model_dump_json())
            pipe.expire(key, resolved_ttl)
            pipe.execute()

    # ── NLP scores ────────────────────────────────────────────

    def get_scores(self, session_id: str) -> ScoreData | None:
        raw = self._redis.get(keys.scores_key(session_id))
        return ScoreData.model_validate_json(raw) if raw else None

    def set_scores(self, session_id: str, scores: ScoreData) -> None:
        self._redis.set(keys.scores_key(session_id), scores.model_dump_json())

    # ── Session metadata ──────────────────────────────────────

    def get_session_meta(self, session_id: str) -> SessionMeta | None:
        raw = self._redis.get(keys.meta_key(session_id))
        return SessionMeta.model_validate_json(raw) if raw else None

    def set_session_meta(self, session_id: str, meta: SessionMeta, ttl: int = 0) -> None:
        resolved_ttl = ttl or settings.SESSION_TTL
        self._redis.set(keys.meta_key(session_id), meta.model_dump_json(), ex=resolved_ttl)

    # ── Cleanup ───────────────────────────────────────────────

    def delete_session(self, session_id: str) -> None:
        self._redis.delete(
            keys.history_key(session_id),
            keys.scores_key(session_id),
            keys.meta_key(session_id),
        )
