---
title: Responsive Search Autocomplete
date: 2026-03-01
ticket: "#58"
---

# Responsive Search Autocomplete

## Problem

Users must click the Search button to see results. There's no feedback as they type — no suggestions, no autocomplete, no indication that the system recognizes their query. This makes search feel sluggish.

## What We're Building

1. **Autocomplete dropdown** that appears below the search input as the user types
2. **Hybrid suggestion source**: search history first (instant, local), then live API suggestions if no history matches (debounced)
3. **Selection behavior**: selecting a suggestion fills the search box but doesn't auto-submit — user can edit or press Search

## Why This Approach

- HTMX-rendered dropdown keeps the codebase consistent (no JS libraries)
- Search history suggestions are free (already stored in `search_history` table)
- Live API fallback ensures suggestions even for first-time queries
- Fill-only selection is least surprising — user stays in control

## Key Decisions

- Use HTMX `hx-get` with `hx-trigger="input changed delay:300ms"` on the search input
- New endpoint: `GET /api/search/suggest?q=...` returns HTML `<ul>` dropdown
- Backend checks search history first, then fires a fast single-provider query (e.g., HuggingFace) for live suggestions
- Dropdown positioned absolutely below the search input via CSS
- Clicking a suggestion fills the input text, closes the dropdown
- Minimum 2 characters before triggering suggestions

## Open Questions

- Should we show the source of each suggestion (e.g., "iris — from history" vs "iris — HuggingFace")?
- How many suggestions to show? (5-8 seems right)
- Should pressing Enter in the dropdown select the highlighted suggestion or submit the search?
