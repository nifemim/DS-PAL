# Brainstorm: Restructure Analysis into 3 Sections

**Date:** 2026-02-08
**Ticket:** #27
**Status:** Ready for planning

## What We're Building

Restructure the monolithic analysis results page into 3 tabbed sections with HTMX lazy-loading:

1. **Pre-Processing** — transformations applied, encoding summary, dropped columns, before/after feature comparison
2. **Exploratory Data Analysis** — distributions, correlations, summary statistics, anomaly detection, missing values, histograms
3. **Segmentation** — cluster profiles, scatter plots, parallel coordinates, cluster sizes

The LLM insights panel stays as a top-level summary above the tabs. Each tab loads its content via HTMX. All 3 sections preload in the background after the first tab renders, so tab switching is instant.

## Why This Approach

The current results page is a single flat section mixing pre-processing info, statistical summaries, and clustering results. Users have to scroll through everything to find what they care about. The 3-section split matches the natural stages of a data science workflow and makes the page scannable.

HTMX lazy-load tabs were chosen over pure CSS tabs because:
- They set up the architecture for running each stage independently in the future
- Each section becomes its own partial template and endpoint, making the code more modular
- The analysis result is already cached in `app.state.pending_analyses`, so re-fetching sections from the cache adds no overhead

## Key Decisions

1. **Single trigger for now:** Keep one "Run Analysis" button that produces all 3 sections. The pipeline runs as before, but results are stored and served per-section via HTMX tabs. Code is structured so splitting into independent triggers later is straightforward.
2. **HTMX lazy-load tabs with background preload:** All 3 sections load via HTMX. The EDA tab (default) loads first and is visible. The other two preload in the background via `hx-trigger="load"` on hidden containers, so tab switching is instant with no spinner.
3. **Default tab: EDA.** Users ran analysis for insights — show them stats and distributions immediately, not pre-processing details.
4. **No tab persistence.** Always starts on EDA tab. Simplest implementation.
5. **LLM insights stay top-level:** The insights panel renders above the tabs as a high-level narrative summary, not inside any specific section.
6. **Anomaly detection → EDA section:** Anomaly count, scores, and the overlay chart live in the EDA tab.
7. **New Pre-Processing content:** Add dropped columns summary (which columns and why) and before/after feature count comparison.
8. **New EDA content:** Add missing values summary (NaN counts per column) and per-column distribution histograms.

## Content Mapping

### Tab 1: Pre-Processing
- Column transformations table (encoding_info: column → encoding type → feature count)
- Ordinal warnings for label-encoded columns
- Before/after feature count comparison (original columns → after encoding)
- Dropped columns summary (ID-like, zero-variance, high-NaN — with reason)

### Tab 2: Exploratory Data Analysis (default)
- Summary stats cards (data points, features used, anomalies count)
- Missing values summary (NaN counts per column, bar chart or table)
- Column statistics table (mean, std, min, max, quartiles)
- Per-column distribution histograms (new chart type)
- Correlation heatmap chart
- Feature box plots chart
- Anomaly detection overlay chart

### Tab 3: Segmentation
- Algorithm + params summary
- Clusters found + silhouette score cards
- Cluster profiles (size, centroid, top features)
- 2D/3D cluster scatter plots
- Cluster size distribution chart
- Silhouette quality chart
- Parallel coordinates chart

### Above Tabs (Top-Level)
- LLM insights panel (overview, cluster characteristics table, quality assessment)
- Save button

## Current Architecture

- Analysis results template: `app/templates/partials/analysis_results.html` (single flat section)
- Charts template: `app/templates/partials/cluster_charts.html` (all 8 charts in one grid)
- Analysis router: `app/routers/analysis.py` — `POST /api/analyze` returns full results partial
- Pending analyses cache: `app.state.pending_analyses` (keyed by UUID, TTL 1 hour)
- Visualization service: `app/services/visualization.py` — generates 8 Plotly charts

## Tab UX

- **Tab bar:** Horizontal tab buttons at the top of the results area (below LLM insights)
- **Active tab:** Highlighted with accent color, content area shows that section
- **Loading:** All 3 sections preload via HTMX `hx-trigger="load"`. EDA is visible first; Pre-Processing and Segmentation load in hidden containers. When user clicks a tab, content is already there — instant switch.
- **No persistence:** Always starts on EDA tab on page load

## Open Questions

None — ready to plan.
