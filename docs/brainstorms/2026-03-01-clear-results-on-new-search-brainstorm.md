# Clear Existing Results When Starting a New Search

**Date:** 2026-03-01
**Ticket:** #59
**Status:** Ready for planning

## What We're Building

When a user submits a new search, the old results should disappear immediately and be replaced by the skeleton loader. Currently, old results linger until the new response arrives, which feels stale and confusing.

## Why This Approach

- **Skeleton loader only** — no blank/empty state, no fade animation. Instant swap to skeleton on submit.
- **Submit only** — old results stay visible if the user clears the input field; they only clear on a new search submission.
- HTMX already swaps `#search-results` on response, so we just need to clear it slightly earlier — on request start rather than response arrival.

## Key Decisions

1. **Clear trigger:** `htmx:beforeRequest` event on the search form (or `hx-on::before-request` attribute)
2. **Clear content:** Replace `#search-results` innerHTML with the skeleton loader markup
3. **Scope:** Search form submit only, not input clear
4. **No backend changes needed** — purely a frontend timing fix

## Open Questions

None — this is a small, well-scoped change.
