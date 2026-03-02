---
title: "fix: Chat returns 'Something went wrong' on Render"
type: fix
date: 2026-03-02
ticket: "#60"
reviewed: false
---

# fix: Chat returns "Something went wrong" on Render

## Overview

The PAL chat widget returns "Something went wrong" on the Render deployment. Two root causes: (1) `HUGGINGFACE_TOKEN` may not be set in Render env vars, and (2) `chat.py` has unhandled exceptions that bubble up as 500 errors.

## Problem

The chat calls HuggingFace's API (`app/routers/chat.py:68-85`). The error handling only catches `httpx.TimeoutException` and `httpx.HTTPStatusError`, but misses:

- `httpx.ConnectError` / `httpx.RequestError` (network failures common on Render's proxy layer)
- `KeyError` / `json.JSONDecodeError` (if HF response structure is unexpected)
- Database write failures during message persistence

Any unhandled exception causes FastAPI to return a 500, and the HTMX error handler in `app.js:186` shows "Something went wrong."

## Implementation

### 1. Set HUGGINGFACE_TOKEN on Render

Manual step: add `HUGGINGFACE_TOKEN` in Render dashboard > Environment.

### 2. Harden error handling in `_call_hf()`

**`app/routers/chat.py`** — broaden the except clause in `handle_message()`:

- Catch `httpx.RequestError` (base class covering `ConnectError`, `ProxyError`, `RemoteProtocolError`) alongside `httpx.HTTPStatusError`
- Wrap `_call_hf()` response parsing in try/except for `KeyError` and `json.JSONDecodeError`
- Log the specific error type for debugging

### 3. Protect database persistence

**`app/routers/chat.py`** — wrap the DB save calls in try/except so a DB failure doesn't prevent the chat response from being returned to the user. Log the error but still return the bot reply.

## Files to Modify

| Action | File |
|--------|------|
| Modify | `app/routers/chat.py` (broaden exception handling) |
| Manual | Render dashboard (set `HUGGINGFACE_TOKEN`) |

## Acceptance Criteria

- [ ] Chat works on Render when `HUGGINGFACE_TOKEN` is set
- [ ] Network errors (ConnectError, ProxyError) return a friendly message, not a 500
- [ ] Malformed API responses return a friendly message, not a 500
- [ ] DB save failures don't break the chat response
- [ ] All existing chat tests pass

## References

- Chat router: `app/routers/chat.py:68-121`
- Frontend error handler: `app/static/js/app.js:186-229`
- Config: `app/config.py` (`huggingface_token`)
- HTTP client setup: `app/main.py:59-62`
