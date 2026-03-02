---
title: "feat: Add Cluster Descriptions tab and rename Segmentation to Cluster Plots"
type: feat
date: 2026-03-02
---

# Add Cluster Descriptions Tab

Move cluster description/summary content into its own tab and rename "Segmentation" to "Cluster Plots".

## Current State

`app/templates/partials/analysis_results.html` has 3 tabs:
- **Pre-Processing** — dropped columns, encoding info, missing values
- **EDA** — distributions, correlation heatmap, anomaly overlay
- **Segmentation** — algorithm stats, cluster profiles table, AND cluster charts (scatter, sizes, silhouette, parallel coords)

LLM-generated cluster insights (`cluster_insights.html`) sit above the tabs in an `<article id="cluster-insights">` block.

## Proposed Changes

### 1. Add 4th tab button in `analysis_results.html`

Add "Cluster Descriptions" tab to the tab bar and create its panel. Move the `cluster-insights` article from above the tabs into this new panel.

```html
<!-- Tab bar -->
<button ... data-tab="preprocessing">Pre-Processing</button>
<button ... data-tab="eda" class="tab-btn active">EDA</button>
<button ... data-tab="clusters">Cluster Descriptions</button>
<button ... data-tab="segmentation">Cluster Plots</button>
```

```html
<!-- New panel -->
<div id="tab-clusters" role="tabpanel" class="tab-panel" style="display: none;">
    {% include "partials/section_clusters.html" %}
</div>
```

### 2. Create `section_clusters.html`

New partial that contains:
- The LLM insights block (moved from above tabs) — `<article id="cluster-insights">`
- The cluster profiles table (moved from `section_segmentation.html`)
- Algorithm stats cards (moved from `section_segmentation.html`)

### 3. Slim down `section_segmentation.html`

- Remove cluster profiles table and algorithm stats
- Rename heading from "Segmentation" to "Cluster Plots"
- Keep only the charts grid (scatter_2d, scatter_3d, cluster_sizes, silhouette, parallel_coordinates)

## Acceptance Criteria

- [x] 4 tabs visible: Pre-Processing | EDA | Cluster Descriptions | Cluster Plots
- [x] "Cluster Descriptions" tab contains: LLM insights, algorithm stats, cluster profiles
- [x] "Cluster Plots" tab contains only segmentation charts
- [x] Tab switching works correctly (existing JS handles this)
- [x] LLM insights HTMX load still triggers on page load (not on tab click)
- [x] All existing tests pass

## Files to Change

- `app/templates/partials/analysis_results.html` — add tab button, move insights block into tab panel
- `app/templates/partials/section_clusters.html` — new file with insights + profiles
- `app/templates/partials/section_segmentation.html` — remove profiles, rename heading
