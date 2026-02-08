# Brainstorm: Structured Cluster Characteristics Table

**Date:** 2026-02-08
**Ticket:** #23
**Status:** Ready for planning

## What We're Building

Replace the current two-part cluster display (free-form LLM paragraph + per-cluster profile tables) with a single structured table. Each row represents a cluster with an LLM-generated label, size, and concise description. The Overview and Anomalies & Quality sections also become structured rather than free-text paragraphs.

The LLM prompt switches from requesting prose separated by `---` to returning structured JSON that we parse and render directly into HTML.

## Why This Approach

The current free-text paragraph for cluster characteristics is hard to scan — the user has to read through a wall of text to find what makes each cluster unique. A table is immediately scannable. By requesting structured JSON from the LLM, we get reliable per-cluster data that maps directly to table rows, rather than trying to parse natural language.

Converting all three sections (overview, clusters, quality) to structured JSON keeps the prompt consistent and makes the entire insights panel more predictable and testable.

## Key Decisions

1. **Merge LLM insights + cluster profiles into one table** — Remove the separate "Cluster Profiles" section with its Feature/Mean/Deviation tables. The new table has one row per cluster: Label, Size (count + %), Description (1 sentence from LLM).
2. **LLM returns structured JSON** — Change the prompt to request a JSON object with `overview` (string), `clusters` (array of `{id, label, description}`), and `quality` (string). Parse with `json.loads()` and fall back gracefully if parsing fails.
3. **All three sections become structured** — Overview renders as a summary paragraph from JSON `overview` field. Clusters render as a table. Quality renders as a paragraph from JSON `quality` field. The `---` separator format is retired.
4. **Keep it simple** — Table columns are just Label, Size, Description. No feature stats in the table — the cluster profiles detail tables were useful but dense. If users want feature-level detail, they can look at the charts.

## Current Architecture

- `app/services/insights.py:_build_prompt()` — Builds system + user prompt, currently requests 3 paragraphs separated by `---`
- `app/services/insights.py:split_sections()` — Splits response on `---` into overview/clusters/quality strings
- `app/services/insights.py:generate_insights()` — Returns `dict[str, str]` with keys overview, clusters, quality
- `app/templates/partials/cluster_insights.html` — Renders each section as `<p>{{ sections.X }}</p>`
- `app/templates/partials/analysis_results.html` — Renders cluster profile tables (Feature/Mean/Deviation) separately
- `app/routers/analysis.py:get_insights()` — HTMX endpoint returning the insights partial

## JSON Schema

The LLM returns this structure:

```json
{
  "overview": "The Iris dataset was analyzed using K-Means with 3 clusters...",
  "clusters": [
    {
      "id": 0,
      "label": "Large-petaled flowers",
      "description": "Flowers with significantly above-average petal length and width."
    }
  ],
  "quality": "The silhouette score of 0.55 indicates good cluster separation..."
}
```

- `id` matches `cluster_id` from analysis — pairs LLM labels with size data we already have
- `label` is a short intuitive name (2-4 words)
- `description` is exactly 1 sentence explaining what makes the cluster unique
- `overview` and `quality` remain free-text strings
- Size/percentage are NOT in the JSON — already available from `cluster_profiles`, merged at render time

## Table Layout

| Cluster | Label | Size | Description |
|---------|-------|------|-------------|
| 0 | **Large-petaled flowers** | 50 (33.3%) | Flowers with above-average petal length and width. |
| 1 | **Compact flowers** | 62 (41.3%) | Small flowers with below-average measurements. |
| -1 | **Noise** | 5 (3.3%) | Outlier points not assigned to any cluster. |

- Cluster column shows ID (or "Noise" for -1)
- Label is bold, most prominent — the LLM's intuitive name
- Size combines count + percentage in one cell
- Description is the widest column, one concise sentence
- Standard `<table>` with Pico CSS styling (matches existing tables in the app)

## Fallback Behavior

1. **JSON parsing fails** — Auto-retry once with the same prompt. If still not valid JSON, show "Insights unavailable" with a Retry button.
2. **LLM disabled** — No table rendered. Summary stats (Clusters Found, Silhouette Score, etc.) still display as they come from the analysis, not the LLM.
3. **Cluster ID mismatch** — Render LLM rows that match, show a fallback row ("No description available") for any cluster IDs missing from the LLM response.
4. **LLM call fails** (network/timeout) — Same as today: "Insights unavailable" with Retry button.

## Open Questions

None — ready to plan.
