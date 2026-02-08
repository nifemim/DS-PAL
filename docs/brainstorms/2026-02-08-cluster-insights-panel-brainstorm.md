---
topic: Cluster insights summary panel
ticket: "#5"
date: 2026-02-08
status: decided
---

# Cluster Insights Summary Panel

## What We're Building

An LLM-generated plain-language narrative that explains clustering results to users who may not be data scientists. The panel appears at the top of analysis results (before stats and charts) and loads asynchronously via HTMX after the main results render.

The narrative should cover: what the clusters represent, which features distinguish them, how good the clustering is (silhouette score interpretation), and any notable anomalies.

## Why This Approach

- **LLM-generated narrative** over templates or bullet points because the data varies wildly across datasets — templates would either be too generic or require dozens of special cases. An LLM can adapt its language to the actual feature names and domain.
- **Async loading** because LLM calls take 2-5 seconds and shouldn't block the user from seeing their analysis results immediately.
- **Multi-provider support** (Anthropic/OpenAI) via config so users can use whichever API key they have.

## Key Decisions

1. **Insight generation**: LLM-generated narrative (not templates or bullet points)
2. **LLM provider**: Configurable — support Anthropic (Claude) and OpenAI via env var
3. **Placement**: Top of analysis results, before the stats grid
4. **Loading strategy**: Async HTMX — results render immediately, narrative loads separately via `hx-get` with `hx-trigger="load"`
5. **Graceful degradation**: If no API key is configured or the call fails, the panel simply doesn't appear (no error shown to user)
6. **Tone**: Analyst report — professional and precise
7. **Structure**: Three headed sections — Overview, Cluster Characteristics, Anomalies & Quality — each 2-3 sentences
8. **Feature names**: Map encoded feature names back to original column names in the prompt for readable narratives
9. **Length**: ~200-300 words total across the three sections

## Prompt Design

**Tone**: Professional analyst report. Precise language with specific numbers.

**Structure** (3 sections, each 2-3 sentences):
- **Overview**: Dataset size, algorithm used, number of clusters found, overall quality assessment
- **Cluster Characteristics**: What distinguishes each cluster, using original column names. Reference z-deviations to indicate strength of distinguishing features.
- **Anomalies & Quality**: Silhouette score interpretation (poor/fair/good/excellent), anomaly count and what makes them unusual

**Feature name mapping**: Use `encoding_info` to map processed feature names (e.g. `city_encoded`, `category_Home`) back to original column names (e.g. `city`, `category`) in the prompt context so the LLM writes about recognizable column names.

**Prompt input data** (serialized from `AnalysisOutput`):
- `cluster_profiles`: size, percentage, top 5 features with z-deviations
- `silhouette_score`: float
- `anomaly_labels`: count of anomalies, total rows
- `algorithm` + `n_clusters`
- `encoding_info`: original column name mappings
- Dataset name for context

## UX Design

**Loading state**: Skeleton placeholder — gray animated lines mimicking the 3-section layout so the user sees the shape of what's coming while the LLM generates.

**Panel styling**: Bordered card (`<article>` element) that visually separates insights from the stats grid below.

**User interactions**:
- **Regenerate** button: small secondary button to request a fresh narrative
- **Copy to clipboard** button: copies the plain-text narrative for sharing in reports

## Failure & Edge Cases

- **API failure**: Auto-retry once, then show "Insights unavailable" with a manual Retry button
- **No API key configured**: Don't render the panel at all (graceful degradation)
- **Degenerate results** (0-1 clusters, all noise): Always send to LLM — let it explain what happened and suggest parameter adjustments
- **Large feature sets** (50+ features): Send all data to the LLM, no truncation. Modern LLMs handle long contexts and cost is minimal.

## Open Questions

- Should we cache insights for saved analyses or regenerate each time?
