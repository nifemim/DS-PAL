# Brainstorm: LLM Insights Summary — Exhaustive Cluster Coverage

**Date:** 2026-02-08
**Ticket:** #21
**Status:** Ready for planning

## What We're Building

A fix to ensure the LLM-generated insights panel describes characteristics of every cluster in the analysis, not just a subset. Currently the prompt says "for each cluster" but the LLM sometimes skips clusters due to token limits and insufficiently forceful instructions.

## Why This Approach

Two root causes work together: (1) `max_tokens=500` can truncate output before all clusters are covered, especially with 4+ clusters, and (2) the prompt isn't explicit enough about the requirement — it says "for each cluster" in flowing prose rather than demanding a structured enumeration. Fixing both is needed.

Additionally, even with a better prompt and higher token limit, LLMs can still occasionally skip clusters. A post-generation validation check with a single retry provides a safety net.

## Key Decisions

1. **Increase max_tokens** — Raise from 500 to a higher value that accommodates analyses with more clusters. Scale based on cluster count if needed.
2. **Restructure the prompt** — Make the cluster section more explicit: require a numbered/labeled subsection per cluster, reference the exact count (e.g., "You MUST describe all 4 clusters"), and list cluster IDs in the instruction.
3. **Post-generation validation** — After receiving the LLM response, check that each cluster ID (0, 1, 2, ...) appears in the clusters section. If any are missing, retry once with a prompt that explicitly names the skipped clusters.
4. **Single retry with explicit list** — If the first attempt misses clusters, the retry prompt says something like "Your previous response omitted Clusters 2 and 4. Rewrite the cluster characteristics section covering ALL clusters, especially Clusters 2 and 4." This avoids the complexity of stitching together partial responses.

## Current Architecture

- `app/services/insights.py:_build_prompt()` — Constructs system + user prompt
- `app/services/insights.py:generate_insights()` — Calls LLM, parses response
- `app/services/insights.py:split_sections()` — Splits response into overview/clusters/quality
- System prompt paragraph 2 says "for each cluster, give it an intuitive label"
- `max_tokens=500`, `temperature=0.3`
- Cluster profiles passed as text with top 5 features per cluster

## Open Questions

None — ready to plan.
