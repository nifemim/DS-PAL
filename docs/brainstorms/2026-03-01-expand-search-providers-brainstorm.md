---
title: Expand Search Providers
date: 2026-03-01
ticket: "#57"
---

# Expand Search Providers

## Problem

Search returns empty for many common queries because only 2 of 4 providers are active:
- **data.gov** — active, but strict filtering (only CSV/JSON with direct download URLs)
- **HuggingFace** — active, but biased toward ML-specific datasets
- **Kaggle** — disabled (no valid credentials configured)
- **UCI** — disabled (API endpoint broken, returns HTML instead of JSON)

Provider failures are silently swallowed, so users have no idea why results are empty.

## What We're Building

1. **Add 4 new dataset providers:** OpenML, AWS Open Data, Google Dataset Search, Awesome Public Datasets
2. **Show active provider attribution** below search results so users know which sources returned results
3. **Remove or replace broken UCI provider**

## Why This Approach

- More providers = better coverage for common queries
- OpenML and AWS Open Data have free APIs with no auth required — easy to add
- Provider attribution gives users transparency and builds trust
- Replacing broken providers is better than silently failing

## Key Decisions

- Add OpenML, AWS Open Data, Google Dataset Search, Awesome Public Datasets
- Show which providers returned results (e.g., "Results from HuggingFace, OpenML, data.gov")
- Keep Kaggle provider but leave it optional (requires user credentials)
- Replace broken UCI provider

## Open Questions

- Does Google Dataset Search have a usable API, or is it scraping-only?
- Should Awesome Public Datasets be a static index or fetched from GitHub?
- Rate limits on OpenML and AWS Open Data APIs?
- Should we prioritize/rank results from certain providers higher?
