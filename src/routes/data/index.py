"""
Endpoints de dados e analytics.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.auth import authenticate_agent
from src.core.cache.client import CacheClient
from src.core.persistence.factory import get_driver
from src.core.schemas import InsightRecord, HistoryMessage
from src.infrastructure.config import settings
from src.clients.ai_client import AIClient
from src.routes.chat.schemas import Message, ConversationEntry
from .schemas import (
    ChatListResponse, ChatSummary,
    ChatDetailResponse, SessionDetail,
    SentimentInsightResponse, SentimentData, SentimentPoint,
    TopicsInsightResponse, TopicsData,
    MetricsInsightResponse, MetricsData,
    SuggestionsInsightResponse, AIAnalysis,
    FullInsightResponse, AgentContextSnapshot,
    UserContextListResponse, UserContextSummary, UserProfile, UserContextResponse,
    AnalyticsResponse, AnalyticsSummaryResponse, AnalyticsPatternsResponse,
    AnalyticsSentimentResponse, AnalyticsUsersResponse, AnalyticsTimelineResponse,
    AnalyticsSummary, AnalyticsPatterns, AnalyticsSentiment, AnalyticsUsers,
    AnalyticsPeriod, TimelineEntry, TopicPattern, PeakHour,
    SentimentDistribution, UserSegment,
)

router = APIRouter(prefix="/data", tags=["data"])


# ── /data/chat ─────────────────────────────────────────────────────────────────

@router.get("/chat", response_model=ChatListResponse)
def list_chats(agent_id: str = Depends(authenticate_agent)):
    sessions = get_driver().list_sessions(agent_id)
    chats = [
        ChatSummary(
            session_id=s.session_id,
            agent_id=s.agent_id,
            started_at=s.started_at,
            ended_at=s.ended_at,
            total_messages=s.total_messages,
            total_tokens=s.total_tokens,
            resolved=s.resolved,
            escalated=s.escalated,
        )
        for s in sessions
    ]
    return ChatListResponse(total=len(chats), chats=chats)


@router.get("/chat/{session_id}", response_model=ChatDetailResponse)
def get_chat(session_id: str, agent_id: str = Depends(authenticate_agent)):
    driver = get_driver()
    session = driver.load_session(agent_id, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    history = CacheClient().get_history(session_id)
    if not history:
        history = driver.load_history(agent_id, session_id)
    conversation = [
        ConversationEntry(message=Message(
            id=m.message_id,
            role=m.role,
            content=m.content,
            timestamp=m.timestamp,
            status=m.status,
            tokens=m.tokens,
            response_time_ms=m.response_time_ms,
        ))
        for m in history
    ]
    return ChatDetailResponse(
        session=SessionDetail(
            session_id=session.session_id,
            agent_id=session.agent_id,
            started_at=session.started_at,
            ended_at=session.ended_at,
            total_messages=session.total_messages,
            total_tokens=session.total_tokens,
            resolved=session.resolved,
            escalated=session.escalated,
        ),
        conversation=conversation,
    )


@router.delete("/chat/{session_id}", status_code=204)
def delete_chat(session_id: str, agent_id: str = Depends(authenticate_agent)):
    driver = get_driver()
    session = driver.load_session(agent_id, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    now = datetime.now(timezone.utc).isoformat()
    driver.soft_delete_session(agent_id, session_id, now)
    CacheClient().delete_session(session_id)


# ── Insights ───────────────────────────────────────────────────────────────────

def _require_scores(session_id: str):
    scores = CacheClient().get_scores(session_id)
    if not scores:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No analysis data for this session")
    return scores


def _require_session(agent_id: str, session_id: str):
    session = get_driver().load_session(agent_id, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.get("/chat/{session_id}/insights/sentiment", response_model=SentimentInsightResponse)
def insight_sentiment(session_id: str, agent_id: str = Depends(authenticate_agent)):
    _require_session(agent_id, session_id)
    scores = _require_scores(session_id)
    progression = [
        SentimentPoint(message_id=m.message_id, score=m.sentiment_score or 0.0)
        for m in scores.messages
        if m.role == "user" and m.sentiment_score is not None
    ]
    return SentimentInsightResponse(
        session_id=session_id,
        sentiment=SentimentData(
            score=scores.avg_sentiment_score or 0.0,
            label=scores.sentiment_label or "neutral",
            progression=progression,
        ),
    )


@router.get("/chat/{session_id}/insights/topics", response_model=TopicsInsightResponse)
def insight_topics(session_id: str, agent_id: str = Depends(authenticate_agent)):
    _require_session(agent_id, session_id)
    scores = _require_scores(session_id)
    return TopicsInsightResponse(
        session_id=session_id,
        topics=TopicsData(
            detected=scores.all_topics,
            main_topic=scores.main_topic or "",
            intent=scores.intent,
        ),
    )


@router.get("/chat/{session_id}/insights/metrics", response_model=MetricsInsightResponse)
def insight_metrics(session_id: str, agent_id: str = Depends(authenticate_agent)):
    session = _require_session(agent_id, session_id)
    scores = CacheClient().get_scores(session_id)

    if session.resolved:
        resolution = "resolved"
    elif session.escalated:
        resolution = "escalated"
    else:
        resolution = "open"

    history = CacheClient().get_history(session_id)
    response_times = [m.response_time_ms for m in history if m.role == "assistant" and m.response_time_ms]
    avg_rt = round(sum(response_times) / len(response_times), 1) if response_times else 0.0

    time_to_escalation = None
    if session.escalated and session.ended_at:
        try:
            start = datetime.fromisoformat(session.started_at)
            end = datetime.fromisoformat(session.ended_at)
            time_to_escalation = int((end - start).total_seconds())
        except Exception:
            pass

    return MetricsInsightResponse(
        session_id=session_id,
        metrics=MetricsData(
            total_messages=session.total_messages,
            total_tokens=session.total_tokens,
            avg_user_message_length=scores.avg_user_message_length or 0.0 if scores else 0.0,
            avg_response_time_ms=avg_rt,
            time_to_escalation_seconds=time_to_escalation,
            resolution=resolution,
        ),
    )


def _call_ai_for_insight(history_text: str) -> dict:
    msg = HistoryMessage(
        message_id="0",
        session_id="0",
        role="user",
        content=(
            f"Analyze the following chat transcript and respond in JSON only.\n\n"
            f"Transcript:\n{history_text}\n\n"
            'Return exactly: {"key_points": ["..."], "suggested_actions": ["..."], "summary": "..."}'
        ),
        timestamp="",
        status="delivered",
    )
    response = AIClient().complete(
        system="You are an AI assistant that analyzes chat conversations and returns structured JSON insights.",
        messages=[msg],
        max_tokens=512,
    )
    try:
        start = response.content.find("{")
        end = response.content.rfind("}") + 1
        return json.loads(response.content[start:end])
    except Exception:
        return {"key_points": [], "suggested_actions": [], "summary": response.content}


@router.get("/chat/{session_id}/insights/suggestions", response_model=SuggestionsInsightResponse)
def insight_suggestions(session_id: str, agent_id: str = Depends(authenticate_agent)):
    _require_session(agent_id, session_id)
    history = CacheClient().get_history(session_id)
    history_text = "\n".join(f"{m.role.upper()}: {m.content}" for m in history)
    ai_data = _call_ai_for_insight(history_text)
    now = datetime.now(timezone.utc).isoformat()
    return SuggestionsInsightResponse(
        session_id=session_id,
        generated_at=now,
        ai_analysis=AIAnalysis(**ai_data),
    )


@router.get("/chat/{session_id}/insights", response_model=FullInsightResponse)
def insight_full(session_id: str, agent_id: str = Depends(authenticate_agent)):
    session = _require_session(agent_id, session_id)
    scores = _require_scores(session_id)
    history = CacheClient().get_history(session_id)
    history_text = "\n".join(f"{m.role.upper()}: {m.content}" for m in history)
    ai_data = _call_ai_for_insight(history_text)
    now = datetime.now(timezone.utc).isoformat()

    response_times = [m.response_time_ms for m in history if m.role == "assistant" and m.response_time_ms]
    avg_rt = round(sum(response_times) / len(response_times), 1) if response_times else 0.0

    if session.resolved:
        resolution = "resolved"
    elif session.escalated:
        resolution = "escalated"
    else:
        resolution = "open"

    context_record = None
    try:
        from src.services.context_service import ContextService
        rec = ContextService().load_context(agent_id)
        if rec:
            context_record = AgentContextSnapshot(
                version=rec.version,
                tone=rec.context.tone,
                segment=rec.context.segment,
            )
    except Exception:
        pass

    insight = InsightRecord(
        session_id=session_id,
        generated_at=now,
        key_points=ai_data.get("key_points", []),
        suggested_actions=ai_data.get("suggested_actions", []),
        summary=ai_data.get("summary", ""),
    )
    get_driver().save_insight(agent_id, insight)

    progression = [
        SentimentPoint(message_id=m.message_id, score=m.sentiment_score or 0.0)
        for m in scores.messages
        if m.role == "user" and m.sentiment_score is not None
    ]

    return FullInsightResponse(
        session_id=session_id,
        agent_id=agent_id,
        generated_at=now,
        sentiment=SentimentData(
            score=scores.avg_sentiment_score or 0.0,
            label=scores.sentiment_label or "neutral",
            progression=progression,
        ),
        topics=TopicsData(
            detected=scores.all_topics,
            main_topic=scores.main_topic or "",
            intent=scores.intent,
        ),
        resolution=resolution,
        metrics=MetricsData(
            total_messages=session.total_messages,
            total_tokens=session.total_tokens,
            avg_user_message_length=scores.avg_user_message_length or 0.0,
            avg_response_time_ms=avg_rt,
            resolution=resolution,
        ),
        agent_context=context_record,
        ai_analysis=AIAnalysis(**ai_data),
    )


# ── /data/context ──────────────────────────────────────────────────────────────

@router.get("/context", response_model=UserContextListResponse)
def list_contexts(agent_id: str = Depends(authenticate_agent)):
    records = get_driver().list_user_contexts(agent_id)
    contexts = [
        UserContextSummary(
            user_id=r.user_id,
            created_at=r.created_at,
            updated_at=r.updated_at,
            profile=UserProfile(segment=r.segment, language=r.language, form_answers=r.form_answers),
        )
        for r in records
    ]
    return UserContextListResponse(total=len(contexts), contexts=contexts)


@router.get("/context/{user_id}", response_model=UserContextResponse)
def get_context(user_id: str, agent_id: str = Depends(authenticate_agent)):
    record = get_driver().load_user_context(agent_id, user_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User context not found")
    return UserContextResponse(
        user_id=record.user_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        profile=UserProfile(segment=record.segment, language=record.language, form_answers=record.form_answers),
    )


@router.delete("/context/{user_id}", status_code=204)
def delete_context(user_id: str, agent_id: str = Depends(authenticate_agent)):
    record = get_driver().load_user_context(agent_id, user_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User context not found")
    get_driver().delete_user_context(agent_id, user_id)


# ── /data/analytics ────────────────────────────────────────────────────────────

def _build_analytics(agent_id: str, from_: str | None, to: str | None):
    driver = get_driver()
    sessions = driver.list_sessions(agent_id)

    if from_:
        sessions = [s for s in sessions if s.started_at >= from_]
    if to:
        sessions = [s for s in sessions if s.started_at <= to]

    total = len(sessions)
    now = datetime.now(timezone.utc).isoformat()

    if total == 0:
        empty_summary = AnalyticsSummary(
            total_chats=0, total_messages=0, total_users=0,
            avg_messages_per_chat=0.0, avg_chat_duration_seconds=0.0,
            avg_response_time_ms=0.0, resolution_rate=0.0, escalation_rate=0.0,
            total_tokens_used=0, avg_tokens_per_chat=0.0,
        )
        empty_patterns = AnalyticsPatterns(
            most_common_topics=[], most_common_unresolved_topics=[],
            peak_hours=[], peak_days=[], avg_messages_to_resolution=0.0,
            avg_messages_to_escalation=0.0,
        )
        return {
            "generated_at": now,
            "period": AnalyticsPeriod(from_=from_, to=to),
            "summary": empty_summary,
            "patterns": empty_patterns,
            "sentiment": AnalyticsSentiment(avg_score=0.0, distribution=SentimentDistribution(positive=0.0, neutral=1.0, negative=0.0)),
            "users": AnalyticsUsers(new_users=0, returning_users=0, avg_chats_per_user=0.0, segments=[]),
            "timeline": [],
        }

    total_msgs = sum(s.total_messages for s in sessions)
    total_tokens = sum(s.total_tokens for s in sessions)
    resolved = sum(1 for s in sessions if s.resolved)
    escalated = sum(1 for s in sessions if s.escalated)
    unique_users = {s.user_id for s in sessions if s.user_id}
    returning = {uid for uid in unique_users if sum(1 for s in sessions if s.user_id == uid) > 1}

    durations = []
    for s in sessions:
        if s.started_at and s.ended_at:
            try:
                start = datetime.fromisoformat(s.started_at)
                end = datetime.fromisoformat(s.ended_at)
                durations.append((end - start).total_seconds())
            except Exception:
                pass

    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0

    # aggregate NLP scores — load_all_scores evita N+1 (1 query ao invés de 1 por sessão)
    session_ids = {s.session_id for s in sessions}
    resolved_map = {s.session_id: s.resolved for s in sessions}
    all_scores = [sc for sc in driver.load_all_scores(agent_id) if sc.session_id in session_ids]

    topic_counts: Counter = Counter()
    unresolved_topic_counts: Counter = Counter()
    for sc in all_scores:
        for t in sc.all_topics:
            topic_counts[t] += 1
            if not resolved_map.get(sc.session_id, True):
                unresolved_topic_counts[t] += 1

    sentiment_values = [sc.avg_sentiment_score for sc in all_scores if sc.avg_sentiment_score is not None]
    avg_sentiment = round(sum(sentiment_values) / len(sentiment_values), 4) if sentiment_values else 0.0

    rt_values = [sc.avg_response_time_ms for sc in all_scores if sc.avg_response_time_ms > 0]
    avg_rt_global = round(sum(rt_values) / len(rt_values), 1) if rt_values else 0.0

    sentiment_labels = [sc.sentiment_label for sc in all_scores if sc.sentiment_label]
    label_counter = Counter(sentiment_labels)
    label_total = len(sentiment_labels) or 1
    distribution = SentimentDistribution(
        positive=round(label_counter.get("positive", 0) / label_total, 4),
        neutral=round(label_counter.get("neutral", 0) / label_total, 4),
        negative=round(label_counter.get("negative", 0) / label_total, 4),
    )

    # peak hours
    hour_counts: Counter = Counter()
    day_counts: Counter = Counter()
    for s in sessions:
        try:
            dt = datetime.fromisoformat(s.started_at)
            hour_counts[f"{dt.hour:02d}:00"] += 1
            day_counts[dt.strftime("%A")] += 1
        except Exception:
            pass

    peak_hours = [PeakHour(hour=h, avg_chats=c) for h, c in hour_counts.most_common(3)]
    peak_days = [d for d, _ in day_counts.most_common(3)]

    # resolution/escalation message averages
    resolved_msgs = [s.total_messages for s in sessions if s.resolved]
    escalated_msgs = [s.total_messages for s in sessions if s.escalated]

    # timeline by date
    daily: dict = defaultdict(lambda: {"total_chats": 0, "resolved": 0, "escalated": 0, "users": set(), "tokens": 0, "rt": [], "sentiments": [], "response_times": []})
    for s in sessions:
        try:
            date = datetime.fromisoformat(s.started_at).strftime("%Y-%m-%d")
            daily[date]["total_chats"] += 1
            daily[date]["resolved"] += int(s.resolved)
            daily[date]["escalated"] += int(s.escalated)
            if s.user_id:
                daily[date]["users"].add(s.user_id)
            daily[date]["tokens"] += s.total_tokens
        except Exception:
            pass

    for sc in all_scores:
        if sc.updated_at:
            try:
                date = datetime.fromisoformat(sc.updated_at).strftime("%Y-%m-%d")
                if sc.avg_sentiment_score is not None:
                    daily[date]["sentiments"].append(sc.avg_sentiment_score)
                if sc.avg_response_time_ms > 0:
                    daily[date]["response_times"].append(sc.avg_response_time_ms)
            except Exception:
                pass

    timeline = []
    for date in sorted(daily.keys()):
        d = daily[date]
        sents = d["sentiments"]
        rts = d["response_times"]
        timeline.append(TimelineEntry(
            date=date,
            total_chats=d["total_chats"],
            resolved=d["resolved"],
            escalated=d["escalated"],
            new_users=len(d["users"]),
            total_tokens=d["tokens"],
            avg_response_time_ms=round(sum(rts) / len(rts), 1) if rts else 0.0,
            avg_sentiment_score=round(sum(sents) / len(sents), 4) if sents else 0.0,
        ))

    # user segments
    segment_data: Counter = Counter()
    for sc in all_scores:
        pass  # no segment in ScoreData — skip segments for now

    return {
        "generated_at": now,
        "period": AnalyticsPeriod(from_=from_, to=to),
        "summary": AnalyticsSummary(
            total_chats=total,
            total_messages=total_msgs,
            total_users=len(unique_users),
            avg_messages_per_chat=round(total_msgs / total, 1),
            avg_chat_duration_seconds=avg_duration,
            avg_response_time_ms=avg_rt_global,
            resolution_rate=round(resolved / total, 4),
            escalation_rate=round(escalated / total, 4),
            total_tokens_used=total_tokens,
            avg_tokens_per_chat=round(total_tokens / total, 1),
        ),
        "patterns": AnalyticsPatterns(
            most_common_topics=[TopicPattern(topic=t, count=c) for t, c in topic_counts.most_common(10)],
            most_common_unresolved_topics=[TopicPattern(topic=t, count=c) for t, c in unresolved_topic_counts.most_common(5)],
            peak_hours=peak_hours,
            peak_days=peak_days,
            avg_messages_to_resolution=round(sum(resolved_msgs) / len(resolved_msgs), 1) if resolved_msgs else 0.0,
            avg_messages_to_escalation=round(sum(escalated_msgs) / len(escalated_msgs), 1) if escalated_msgs else 0.0,
        ),
        "sentiment": AnalyticsSentiment(avg_score=avg_sentiment, distribution=distribution),
        "users": AnalyticsUsers(
            new_users=len(unique_users) - len(returning),
            returning_users=len(returning),
            avg_chats_per_user=round(total / len(unique_users), 1) if unique_users else 0.0,
            segments=[],
        ),
        "timeline": timeline,
    }


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics_full(
    agent_id: str = Depends(authenticate_agent),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
):
    data = _build_analytics(agent_id, from_, to)
    return AnalyticsResponse(**data)


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
def analytics_summary(
    agent_id: str = Depends(authenticate_agent),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
):
    data = _build_analytics(agent_id, from_, to)
    return AnalyticsSummaryResponse(generated_at=data["generated_at"], period=data["period"], summary=data["summary"])


@router.get("/analytics/patterns", response_model=AnalyticsPatternsResponse)
def analytics_patterns(
    agent_id: str = Depends(authenticate_agent),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
):
    data = _build_analytics(agent_id, from_, to)
    return AnalyticsPatternsResponse(generated_at=data["generated_at"], period=data["period"], patterns=data["patterns"])


@router.get("/analytics/sentiment", response_model=AnalyticsSentimentResponse)
def analytics_sentiment(
    agent_id: str = Depends(authenticate_agent),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
):
    data = _build_analytics(agent_id, from_, to)
    return AnalyticsSentimentResponse(generated_at=data["generated_at"], period=data["period"], sentiment=data["sentiment"])


@router.get("/analytics/users", response_model=AnalyticsUsersResponse)
def analytics_users(
    agent_id: str = Depends(authenticate_agent),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
):
    data = _build_analytics(agent_id, from_, to)
    return AnalyticsUsersResponse(generated_at=data["generated_at"], period=data["period"], users=data["users"])


@router.get("/analytics/timeline", response_model=AnalyticsTimelineResponse)
def analytics_timeline(
    agent_id: str = Depends(authenticate_agent),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
):
    data = _build_analytics(agent_id, from_, to)
    return AnalyticsTimelineResponse(generated_at=data["generated_at"], period=data["period"], timeline=data["timeline"])
