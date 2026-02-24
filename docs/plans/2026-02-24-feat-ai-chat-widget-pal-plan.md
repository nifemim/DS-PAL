---
title: "feat: Add AI-powered chat widget (PAL)"
type: feat
date: 2026-02-24
ticket: "#48"
brainstorm: docs/brainstorms/2026-02-23-feedback-chatbot-brainstorm.md
deepened: 2026-02-24
reviewed: 2026-02-24
---

# feat: Add AI-powered chat widget (PAL)

## Enhancement Summary

**Deepened on:** 2026-02-24
**Reviewed on:** 2026-02-24
**Reviewers:** DHH-style, Kieran Python, Code Simplicity

### Key changes from deepening
1. **Dropped client-side history JSON** — server-side in-memory conversation store instead (eliminates prompt injection vector)
2. **Dropped JS feedback state machine** — system prompt handles feedback naturally (massive simplification)
3. **Updated HF endpoint** — use new `router.huggingface.co` URL with better model (`Qwen2.5-Coder-32B-Instruct`)
4. **Added double-submit prevention** — `hx-disabled-elt` + JS state guard
5. **Scoped HTMX error handlers** — prevent global handlers from clobbering chat messages
6. **Added server-side input validation** — max_length, pattern constraints on all form fields
7. **Shared httpx client** — created in lifespan, reused across requests (eliminates TLS handshake per message)

### Key changes from review
1. **Cut Phase 8 (Security Hardening) entirely** — rate limiting doesn't work on Render proxy IPs, CSRF is meaningless without auth, CSP neutered by required `'unsafe-inline'`, SRI disproportionate for beta demo
2. **Eliminated `chat_service.py`** — inline all logic into `chat.py` router; reuse shared OpenAI-compat helper from `insights.py`
3. **Cut from 7 new files to 3** — `chat.py`, `chat_widget.html`, `chat_message.html`
4. **Merged `send_message` + `save_messages` into single `handle_message()`** — router shouldn't coordinate two operations
5. **Removed DB composite index** — write-only table with no read queries in V1 (YAGNI)
6. **Hardcoded model name** as module constant, not config field
7. **Added session eviction** — stale conversations evicted from in-memory dict
8. **Proper UUID validation** — replace weak regex with `uuid.UUID()` check
9. **Full type annotations** on all functions

---

## Overview

Add a floating AI-powered chat assistant named "PAL" to the bottom-right corner of every page. PAL is a general-purpose assistant that knows about DS-PAL, can help with data science questions, and collects feedback conversationally. Powered by HuggingFace Inference API (free tier). All messages saved to SQLite for review.

## Problem Statement

DS-PAL is now live and shared with colleagues for feedback. There's no in-app way for users to get help, ask questions, or submit feedback. A chat widget solves all three needs in one component.

## Proposed Solution

A custom chat widget built natively with the existing stack (HTMX, Jinja2, Pico CSS, vanilla JS). No third-party embed — full control over design, theme-awareness, and DB persistence.

### Architecture decisions

- **Conversation state:** Server-side in-memory dict keyed by session_id. Capped at 20 messages per session. Stale sessions evicted after 1 hour. Resets on server restart (acceptable for demo). Eliminates client-provided history (prompt injection risk).
- **Feedback mode:** Handled entirely by the system prompt — PAL naturally asks follow-up questions when users say "feedback". No client-side state machine needed.
- **User card rendering:** Both user and bot cards returned together from the server as a single HTMX response fragment. Simpler than split JS/HTMX rendering.
- **Fallback:** If `HUGGINGFACE_TOKEN` is empty or API fails, PAL responds with a static error message. Widget still renders.
- **DB persistence:** Write-only audit log. All messages saved for review. No read endpoint in V1.
- **HF API call:** Reuse shared OpenAI-compatible call pattern from `insights.py`. Extract/adapt `_call_ollama` helper rather than writing from scratch.
- **Single entry point:** One `handle_message()` function does LLM call + DB save. Router calls one function, not two.

### Security decisions (proportionate to beta demo)

- **XSS:** All template output uses `{{ variable }}` (Jinja2 auto-escaped). Never use `| safe` on LLM output. Add comment in template.
- **Input validation:** Server-side `Form(max_length=500)` on message, UUID validation on session_id.
- **Prompt injection:** No client-provided history or page_url sent to LLM. Server reconstructs context from its own memory.
- **Minimal security headers:** `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY` as inline middleware in `main.py` (5 lines, no separate file).
- **No rate limiting** — HuggingFace free tier is the natural throttle. Add slowapi later if abuse appears.
- **No CSRF middleware** — no auth, no cookies, no session tokens = no CSRF threat model.
- **No SRI hashes** — disproportionate for 5-user beta. Add when moving to production.

## Technical Approach

### Files to create

| File | Purpose |
|------|---------|
| `app/routers/chat.py` | Chat API router, HF API call, conversation store, DB save — all in one file |
| `app/templates/partials/chat_widget.html` | Widget HTML (bubble + drawer + welcome message + form) |
| `app/templates/partials/chat_message.html` | Message pair partial (user card + bot card, returned by HTMX) |

### Files to modify

| File | Change |
|------|--------|
| `app/database.py` | Add `chat_messages` table to `SQL_CREATE_TABLES` |
| `app/main.py` | Register `chat.router`, create shared `httpx.AsyncClient`, add `app.state.conversations`, add 5-line security headers middleware |
| `app/templates/base.html` | Include `chat_widget.html` partial before `</body>` |
| `app/static/css/style.css` | Add chat widget styles |
| `app/static/js/app.js` | Add chat drawer toggle, auto-scroll, session ID, scoped error handling |
| `tests/conftest.py` | Add `chat_messages` to table cleanup |

### Implementation phases

#### Phase 1: Config + Shared HTTP Client

**No config change needed.** Model name hardcoded as module constant in `chat.py`.

Update `app/main.py` lifespan to create a shared httpx client and conversation store:

```python
# In lifespan, after init_db():
app.state.http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(connect=10.0, read=35.0, write=10.0, pool=5.0),
    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
)
app.state.conversations = {}  # matches existing app.state.pending_analyses pattern

# In shutdown:
await app.state.http_client.aclose()
```

Add inline security headers middleware in `create_app()`:

```python
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response
```

> **Performance insight:** Per-request `async with httpx.AsyncClient()` creates a new TCP+TLS handshake every time (~100-300ms overhead). A shared client reuses connections via HTTP keep-alive.

#### Phase 2: Database

Add `chat_messages` table to `SQL_CREATE_TABLES` in `app/database.py` (not a separate migration — consistent with existing pattern):

```sql
CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    is_feedback INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

No index — write-only table with no read queries in V1. Add index when a read endpoint is added.

#### Phase 3: Chat router (all logic in one file)

Create `app/routers/chat.py` with everything inline:

```python
import logging
import time
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Form, HTTPException, Request

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

SYSTEM_PROMPT = """You are PAL, the DS-PAL assistant. ..."""  # Full prompt here

# Typed conversation store with eviction
_conversations: dict[str, dict] = {}  # {session_id: {"messages": [...], "last_active": float}}


def _evict_stale() -> None:
    cutoff = time.monotonic() - _CONVERSATION_TTL
    stale = [sid for sid, entry in _conversations.items() if entry["last_active"] < cutoff]
    for sid in stale:
        del _conversations[sid]


def _validate_session_id(session_id: str) -> None:
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id")


async def _call_hf(
    messages: list[dict[str, str]],
    http_client: httpx.AsyncClient,
    token: str,
) -> str:
    """Call HuggingFace OpenAI-compatible chat endpoint."""
    resp = await http_client.post(
        _HF_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={"model": _HF_MODEL, "messages": messages, "max_tokens": 512, "temperature": 0.7},
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def handle_message(
    session_id: str,
    user_message: str,
    http_client: httpx.AsyncClient,
    token: str,
) -> str:
    """Send message, persist exchange, return reply."""
    _evict_stale()

    # Build conversation context
    entry = _conversations.setdefault(session_id, {"messages": [], "last_active": 0.0})
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
        logger.error("LLM API error %d for session %s", exc.response.status_code, session_id)
        return _ERROR_MSG

    entry["messages"].append({"role": "assistant", "content": reply})

    # Save to DB
    is_feedback = "feedback" in user_message.lower()
    db = await get_db()
    try:
        await db.executemany(
            "INSERT INTO chat_messages (session_id, role, content, is_feedback) VALUES (?, ?, ?, ?)",
            [
                (session_id, "user", user_message, int(is_feedback)),
                (session_id, "assistant", reply, int(is_feedback)),
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
) -> templates.TemplateResponse:
    _validate_session_id(session_id)
    from app.config import settings
    if not settings.huggingface_token:
        bot_text = "PAL is not configured yet. Please set HUGGINGFACE_TOKEN."
    else:
        bot_text = await handle_message(
            session_id, message, request.app.state.http_client, settings.huggingface_token,
        )
    return templates.TemplateResponse(
        "partials/chat_message.html",
        {"request": request, "user_text": message, "bot_text": bot_text},
    )
```

Key design choices:
- **Single `handle_message()` entry point** — router calls one function, not two
- **Typed conversation store with TTL eviction** — prevents unbounded memory growth
- **UUID validation** via `uuid.UUID()` — rejects invalid session IDs
- **Distinct error handling** for timeout vs HTTP errors — logs include session_id
- **Model name as module constant** — not a config field (single consumer, single provider)
- **`_call_hf()` follows `_call_ollama()` pattern** from `insights.py`

#### Phase 4: Widget UI

**`app/templates/partials/chat_widget.html`:**

```html
<button id="chat-toggle-btn" class="chat-toggle-btn"
        aria-expanded="false" aria-controls="chat-widget"
        aria-label="Open chat assistant">Chat</button>

<aside id="chat-widget" class="chat-widget" aria-hidden="true"
       role="complementary" aria-label="PAL Assistant">
  <div class="chat-header">
    <span>PAL</span>
    <button class="chat-header__close" id="chat-close-btn"
            aria-label="Close chat">&times;</button>
  </div>

  <div id="chat-log" class="chat-log" role="log"
       aria-live="polite" aria-relevant="additions" aria-atomic="false">
    <!-- Welcome message (static, not saved to DB) -->
    <div class="chat-msg chat-msg--assistant">
      <span class="chat-msg__text">Hi, I'm PAL. I can help you navigate DS-PAL,
      answer data science questions, or collect your feedback.
      Type "feedback" anytime to share your thoughts.</span>
    </div>
  </div>

  <form id="chat-form" class="chat-input-area"
        hx-post="/api/chat/message"
        hx-target="#chat-log"
        hx-swap="beforeend scroll:bottom"
        hx-disabled-elt="find button[type='submit']"
        hx-indicator="#chat-spinner">
    <input type="hidden" name="session_id" id="chat-session-id" value="">
    <label for="chat-input" class="sr-only">Message</label>
    <input id="chat-input" type="text" name="message"
           placeholder="Ask PAL..." autocomplete="off" required
           maxlength="500" aria-label="Chat message">
    <button type="submit">Send</button>
    <span id="chat-spinner" class="htmx-indicator" aria-hidden="true">...</span>
  </form>
</aside>
```

> **HTMX insight:** `hx-swap="beforeend scroll:bottom"` — the `scroll:bottom` modifier auto-scrolls the target after append. No custom JS scroll handler needed.

> **Double-submit prevention:** `hx-disabled-elt="find button[type='submit']"` natively disables the Send button for the entire round-trip. Critical during HF cold starts (10-20s).

**`app/templates/partials/chat_message.html`:**

```html
{# SECURITY: Never add | safe here — content is LLM output #}
<div class="chat-msg chat-msg--user" role="article">
  <span class="chat-msg__text">{{ user_text }}</span>
</div>
<div class="chat-msg chat-msg--assistant" role="article">
  <span class="chat-msg__text">{{ bot_text }}</span>
</div>
```

> **Security insight:** Both user and bot messages are Jinja2 auto-escaped. The template comment is a guardrail against future `| safe` additions.

#### Phase 5: JavaScript

Add to `app/static/js/app.js`:

```javascript
// 1. Session ID — generate on page load, store in sessionStorage with fallback
// 2. Drawer toggle — open/close via class toggle + aria attributes
// 3. Focus management — auto-focus input on open, return focus to button on close
// 4. Escape to close
// 5. Scoped error handling — chat errors append an error card, don't replace all messages
// 6. Form reset on success — clear input after successful send
```

**Critical: Scope HTMX error handlers.** The existing global `htmx:responseError` handler sets `target.innerHTML = '<div class="error-message">...'`. If the chat POST fails, this nukes all messages. Fix:

```javascript
document.body.addEventListener('htmx:responseError', function(event) {
    var target = event.detail.target;
    if (target.id === 'chat-log') {
        // Append error card — don't replace all messages
        var err = document.createElement('div');
        err.className = 'chat-msg chat-msg--assistant';
        err.setAttribute('role', 'alert');
        err.textContent = 'Something went wrong. Please try again.';
        target.appendChild(err);
        return;
    }
    // Existing behavior for other targets
    target.innerHTML = '<div class="error-message"><p>An error occurred.</p></div>';
});
```

**Session ID with storage fallback:**

```javascript
function getOrCreateSessionId() {
    try {
        var id = sessionStorage.getItem('pal-session-id');
        if (!id) {
            id = crypto.randomUUID();
            sessionStorage.setItem('pal-session-id', id);
        }
        return id;
    } catch (e) {
        if (!window._palSessionId) window._palSessionId = crypto.randomUUID();
        return window._palSessionId;
    }
}
```

#### Phase 6: CSS

Add to `app/static/css/style.css`:

```css
/* Chat toggle — fixed bottom-right */
.chat-toggle-btn {
    position: fixed;
    bottom: 1.5rem;
    right: 1.5rem;
    z-index: 900;
    border-radius: 0;  /* DS-PAL sharp corners */
}

/* Chat widget — slide-up drawer */
.chat-widget {
    position: fixed;
    bottom: 0;
    right: 1.5rem;
    width: 360px;
    height: 520px;
    max-height: calc(100vh - 6rem);
    z-index: 950;
    display: flex;
    flex-direction: column;
    background: var(--pico-background-color);
    border: 1px solid var(--pico-muted-border-color);
    transform: translateY(100%);
    opacity: 0;
    visibility: hidden;
    transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1),
                opacity 0.22s ease,
                visibility 0s linear 0.28s;
}

.chat-widget--open {
    transform: translateY(0);
    opacity: 1;
    visibility: visible;
    transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1),
                opacity 0.22s ease,
                visibility 0s linear 0s;
}

/* Messages — card style, sharp corners */
.chat-msg { max-width: 85%; padding: 0.45rem 0.7rem; font-size: 0.875rem; word-break: break-word; }
.chat-msg--user { align-self: flex-end; background: var(--pico-primary); color: var(--pico-primary-inverse); border: 1px solid var(--pico-primary); }
.chat-msg--assistant { align-self: flex-start; border: 1px solid var(--pico-muted-border-color); }

/* Chat log — scrollable flex column */
.chat-log { flex: 1; overflow-y: auto; padding: 0.75rem; display: flex; flex-direction: column; gap: 0.5rem; }

/* Mobile: full-width */
@media (max-width: 480px) {
    .chat-widget { right: 0; width: 100vw; height: 65vh; }
}
```

> **Z-index stacking:** Toggle button at 900, widget panel at 950, both below any native `<dialog>` top layer. Nav bar at 100 stays below both.

## Acceptance Criteria

- [ ] Chat bubble visible on all pages (bottom-right)
- [ ] Clicking bubble opens slide-up drawer with PAL welcome message
- [ ] User can send messages and receive AI responses from HuggingFace
- [ ] Messages display as card-style (user right, bot left, sharp corners)
- [ ] Typing "feedback" triggers PAL to ask structured follow-up questions (via system prompt)
- [ ] All messages saved to `chat_messages` table in SQLite
- [ ] Widget respects light/dark theme
- [ ] Responsive on mobile (full-width under 480px)
- [ ] Escape key closes drawer, focus returns to toggle button
- [ ] No XSS — all content Jinja2 auto-escaped, no `| safe` on LLM output
- [ ] Double-submit prevented — button disabled during request
- [ ] Chat errors append error card, don't replace all messages
- [ ] Graceful fallback when HuggingFace token is missing or API fails
- [ ] Existing tests still pass

## Dependencies & Risks

- **HuggingFace free tier rate limits** — fine for a few colleagues. If exceeded, PAL shows error message.
- **Model cold starts** — 10-20s on first request after idle. `hx-indicator` shows loading state.
- **Render ephemeral storage** — DB resets on redeploy. Acceptable for V1.
- **In-memory conversation store** — resets on server restart. Stale sessions evicted after 1 hour. Acceptable for demo.
- **No new pip dependencies** — `httpx` already in requirements.txt. No slowapi.

## Verification

1. Start app: `uvicorn app.main:app --reload`
2. Open any page — chat bubble visible in bottom-right
3. Click bubble — drawer slides up with welcome message
4. Send a message — user card + bot response appear
5. Type "feedback" — PAL asks structured follow-up questions
6. Toggle light/dark theme — widget adapts
7. Press Escape — drawer closes, focus returns to button
8. Run `pytest` — all existing tests pass
9. Check DB: `sqlite3 ds_pal.db "SELECT * FROM chat_messages;"` — messages saved

## References

- Brainstorm: `docs/brainstorms/2026-02-23-feedback-chatbot-brainstorm.md`
- Router pattern: `app/routers/search.py`
- LLM API pattern: `app/services/insights.py:199-244`
- HuggingFace auth pattern: `app/services/providers/huggingface_provider.py:26-27`
- Base template: `app/templates/base.html`
- Pico CSS gotchas: `docs/solutions/ui-bugs/pico-css-interactive-elements-polish.md`
- HTMX async pattern: `docs/solutions/architecture-patterns/async-llm-insights-with-graceful-degradation.md`
- HTMX `scroll:bottom` modifier: Context7 `/bigskysoftware/htmx`
- HuggingFace chat completion: Context7 `/huggingface/huggingface_hub`
- HF router endpoint: `https://router.huggingface.co/v1/chat/completions`
