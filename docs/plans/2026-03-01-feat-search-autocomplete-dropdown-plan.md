---
title: "feat: Add autocomplete dropdown to search input"
type: feat
date: 2026-03-01
ticket: "#58"
reviewed: true
---

# feat: Add autocomplete dropdown to search input

## Overview

Add an HTMX-powered autocomplete dropdown below the search input that shows suggestions from search history as users type. Selecting a suggestion fills the input but doesn't auto-submit.

**Dropped from original plan (per review):**
- ~~HuggingFace live API fallback~~ — adds latency and complexity for zero value
- ~~Source hints~~ — only one source, nothing to distinguish
- ~~Custom JS dismiss behavior~~ — inline onclick + HTMX handles it

## Implementation

### 1. Backend: Add suggestion endpoint

**`app/services/storage.py`** — add `get_search_suggestions()`:
- Parameterized query: `SELECT DISTINCT query FROM search_history WHERE query LIKE ? ORDER BY created_at DESC LIMIT ?`
- Bind `f"{prefix}%"` as parameter (NOT string interpolation — SQL injection risk)

**`app/routers/search.py`** — add `GET /api/search/suggest`:
- Accept `query` param (align with existing input `name="query"`)
- Strip + validate min 2 chars
- Return HTML partial, or empty string for no matches

### 2. Frontend: HTMX autocomplete on input

**`app/templates/index.html`** — modify search input:
- Add `hx-get="/api/search/suggest"` with `hx-trigger="input changed delay:300ms"`
- Add `hx-target="#search-suggestions"` and `hx-indicator="none"` (prevent skeleton flash)
- Add `<div id="search-suggestions">` inside a positioned container below fieldset

**`app/templates/partials/search_suggestions.html`** — new partial:
- `<ul>` of suggestions, each with onclick to fill input and clear dropdown
- Empty response (no HTML) when zero matches — HTMX swaps in nothing

### 3. Styling

**`app/static/css/style.css`** — ~15 lines:
- `position: relative` on form, `position: absolute` on dropdown
- Sharp corners, `var(--pico-primary)` border, z-index above content
- Hover highlight, works in dark mode via Pico CSS variables

## Files to Create/Modify

| Action | File |
|--------|------|
| Modify | `app/services/storage.py` (add `get_search_suggestions`) |
| Modify | `app/routers/search.py` (add `/api/search/suggest` endpoint) |
| Modify | `app/templates/index.html` (HTMX attrs on input, dropdown container) |
| Create | `app/templates/partials/search_suggestions.html` |
| Modify | `app/static/css/style.css` (dropdown styles) |

## Acceptance Criteria

- [ ] Typing 2+ characters shows up to 5 suggestions from search history
- [ ] Clicking a suggestion fills the input without submitting
- [ ] Dropdown clears when a suggestion is selected
- [ ] No regressions to existing search-on-submit

## References

- Brainstorm: `docs/brainstorms/2026-03-01-responsive-search-autocomplete-brainstorm.md`
- Search history table: `app/database.py:33`
- HTMX version: 1.9.10
