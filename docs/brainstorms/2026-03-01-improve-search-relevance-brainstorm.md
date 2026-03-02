# Improve Search Result Relevance

**Date:** 2026-03-01
**Ticket:** #61
**Status:** Ready for planning

## What We're Building

A relevance scoring and ranking system for search results, with fuzzy matching, deduplication across providers, and a light UI for sorting. Currently results are just concatenated in provider order with no ranking — data.gov always first, then Kaggle, etc., regardless of query relevance.

## Why This Approach

- **rapidfuzz** for fuzzy string matching — handles typos, partial matches, word order. Single well-tested dependency.
- **Score-and-rank** all results together instead of displaying provider-by-provider. Interleave results so the best match from any provider appears first.
- **Deduplicate** by fuzzy-matching dataset names across providers. Keep the best source (prefer the one with more metadata / higher download count).
- **Light UI** — add a sort dropdown (Relevance / Downloads / Name) to the results partial. No heavy filtering panel.

## Key Decisions

1. **Scoring formula:** Weighted combination of title match (highest weight), description match, tag match, and provider quality signals (downloads where available)
2. **Fuzzy matching library:** `rapidfuzz` (token-set ratio for relevance, partial ratio for dedup)
3. **Deduplication:** Fuzzy name comparison across providers. When two results match above a threshold, keep the one with richer metadata
4. **UI:** Sort dropdown in search results header (Relevance default, Downloads, Name A-Z)
5. **No query expansion** — keep it simple, rapidfuzz handles enough
6. **DatasetResult schema change:** Add optional `relevance_score` field for sorting

## Open Questions

- What fuzzy match threshold for deduplication? (Start with 85, tune from there)
- Should the sort preference persist across searches? (Probably not — default to Relevance each time)
