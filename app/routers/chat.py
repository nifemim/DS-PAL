"""Chat API router — PAL assistant powered by HuggingFace."""
import logging
import time
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Form, HTTPException, Request

from app.config import settings
from app.database import get_db
from app.main import templates

logger = logging.getLogger(__name__)
router = APIRouter()

_HF_MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"
_HF_URL = "https://router.huggingface.co/v1/chat/completions"
_MAX_HISTORY = 20
_CONVERSATION_TTL = 3600  # 1 hour
_TIMEOUT_MSG = "I'm having trouble responding right now. Please try again."
_ERROR_MSG = "Something went wrong. Please try again."

SYSTEM_PROMPT = (
    "You are PAL, the DS-PAL assistant. You are professional, concise, and helpful.\n\n"
    "DS-PAL is a web app for dataset pre-processing, analysis, and learning. "
    "It supports:\n"
    "- Dataset search from Kaggle, HuggingFace, UCI ML Repository, and Data.gov\n"
    "- File uploads: CSV, JSON, Excel (.xlsx), Parquet\n"
    "- Clustering analysis: K-Means, DBSCAN\n"
    "- Anomaly detection with configurable contamination\n"
    "- Interactive Plotly visualizations\n"
    "- Saved analyses for later review\n\n"
    "Workflow: search or upload a dataset -> select it -> configure analysis -> view results.\n\n"
    "You can also answer general data science questions.\n\n"
    "IMPORTANT: If a user asks about something unrelated to DS-PAL, data science, "
    "or feedback, give a brief one-sentence acknowledgment then steer the conversation "
    "back. For example: 'That's an interesting question! But I'm best at helping with "
    "DS-PAL and data science topics. What dataset are you working with today?'\n\n"
    "When a user types 'feedback' or expresses they want to give feedback, "
    "switch to feedback collection mode. Ask these questions one at a time:\n"
    "1. What were you trying to do?\n"
    "2. How was your experience?\n"
    "3. Any suggestions for improvement?\n"
    "After collecting answers, thank them and confirm their feedback was recorded."
)


def _validate_session_id(session_id: str) -> None:
    """Validate that session_id is a proper UUID."""
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id")


def _evict_stale(conversations: dict) -> None:
    """Remove conversations inactive for longer than TTL."""
    cutoff = time.monotonic() - _CONVERSATION_TTL
    stale = [
        sid for sid, entry in conversations.items()
        if entry["last_active"] < cutoff
    ]
    for sid in stale:
        del conversations[sid]


async def _call_hf(
    messages: list[dict[str, str]],
    http_client: httpx.AsyncClient,
    token: str,
) -> str:
    """Call HuggingFace OpenAI-compatible chat endpoint."""
    resp = await http_client.post(
        _HF_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": _HF_MODEL,
            "messages": messages,
            "max_tokens": 512,
            "temperature": 0.7,
        },
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def handle_message(
    session_id: str,
    user_message: str,
    http_client: httpx.AsyncClient,
    token: str,
    conversations: dict,
) -> str:
    """Send message to LLM, persist exchange, return reply."""
    _evict_stale(conversations)

    # Build conversation context
    entry = conversations.setdefault(
        session_id, {"messages": [], "last_active": 0.0}
    )
    entry["last_active"] = time.monotonic()
    entry["messages"].append({"role": "user", "content": user_message})

    # Cap history
    if len(entry["messages"]) > _MAX_HISTORY:
        entry["messages"] = entry["messages"][-_MAX_HISTORY:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + entry["messages"]

    try:
        reply = await _call_hf(messages, http_client, token)
    except httpx.TimeoutException:
        logger.warning("LLM timeout for session %s", session_id)
        return _TIMEOUT_MSG
    except httpx.HTTPStatusError as exc:
        logger.error(
            "LLM API error %d for session %s",
            exc.response.status_code, session_id,
        )
        return _ERROR_MSG

    entry["messages"].append({"role": "assistant", "content": reply})

    # Save to DB
    is_feedback = int("feedback" in user_message.lower())
    db = await get_db()
    try:
        await db.executemany(
            "INSERT INTO chat_messages (session_id, role, content, is_feedback) "
            "VALUES (?, ?, ?, ?)",
            [
                (session_id, "user", user_message, is_feedback),
                (session_id, "assistant", reply, is_feedback),
            ],
        )
        await db.commit()
    finally:
        await db.close()

    return reply


@router.post("/chat/message")
async def chat_message(
    request: Request,
    message: Annotated[str, Form(min_length=1, max_length=500)],
    session_id: Annotated[str, Form(max_length=36)],
):
    """Handle a chat message and return user + bot cards."""
    _validate_session_id(session_id)

    if not settings.huggingface_token:
        bot_text = "PAL is not configured yet. Please set HUGGINGFACE_TOKEN."
    else:
        bot_text = await handle_message(
            session_id,
            message,
            request.app.state.http_client,
            settings.huggingface_token,
            request.app.state.conversations,
        )

    return templates.TemplateResponse(
        "partials/chat_message.html",
        {"request": request, "user_text": message, "bot_text": bot_text},
    )
