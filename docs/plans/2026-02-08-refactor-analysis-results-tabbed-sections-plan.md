---
title: "refactor: Restructure analysis results into 3 tabbed sections"
type: refactor
date: 2026-02-08
ticket: "#27"
brainstorm: "docs/brainstorms/2026-02-08-analysis-sections-restructure-brainstorm.md"
---

# refactor: Restructure analysis results into 3 tabbed sections

## Overview

Break the monolithic `analysis_results.html` partial into 3 inline server-rendered tabs — **Pre-Processing**, **EDA** (default), **Segmentation** — rendered via `{% include %}` in the initial POST response. Tab switching is pure JS show/hide with `Plotly.Plots.resize()`. Add 4 new data items: dropped columns summary, before/after feature count, missing values summary, and per-column feature distribution box plots.

**Scope:** Fresh analysis view only. Saved analysis detail view deferred to follow-up ticket.

## Problem Statement

The current results page is a single flat section mixing pre-processing info (encoding), statistical summaries (stats cards, column stats), and clustering results (profiles, 8 charts). Users scroll through everything to find what they care about. The content doesn't match the natural stages of a data science workflow.

Additionally, useful data computed by the pipeline is never shown:
- `analysis.column_stats` (mean, std, min, max, quartiles) — computed but not rendered
- `analysis.params` (algorithm parameters) — stored but not shown in live view
- Dropped columns (>50% NaN, zero-variance, ID-like) — logged but not surfaced
- Missing values per column — discarded during preprocessing

## Proposed Solution

### Architecture

```
POST /api/analyze  →  returns analysis_results.html (all content rendered server-side)
                          ├── LLM insights (hx-get, hx-trigger="load") — existing, stays async
                          ├── Save button
                          ├── Tab bar: [Pre-Processing] [EDA*] [Segmentation]
                          ├── {% include "partials/section_preprocessing.html" %}  (display: none)
                          ├── {% include "partials/section_eda.html" %}            (visible)
                          └── {% include "partials/section_segmentation.html" %}   (display: none)
```

All 3 sections render inline in the initial POST response. No new endpoints. Tab switching toggles `display: none` via JS and calls `Plotly.Plots.resize()` on the newly visible panel. The LLM insights panel remains the only HTMX lazy-loaded element (it calls an external LLM API with unpredictable latency — lazy-loading is justified there).

**Why inline instead of HTMX lazy-load?** The analysis data is already fully computed and in memory when the POST returns. Lazy-loading would turn 1 request into 4, introduce a cache race condition (save deletes cache while tabs still loading), and require a chart routing constant — all for zero latency benefit.

### Content Mapping

**Pre-Processing tab:**
- Encoding info table (column → encoding type → feature count) — existing data
- Ordinal warnings for label-encoded columns — existing data
- Dropped columns summary (column name + reason) — **new data**
- Before/after feature count comparison (original columns → after encoding) — **new data**

**EDA tab (default):**
- Summary stats cards: data points, features used, anomalies count — existing data
- Missing values summary (NaN counts per column, table) — **new data**
- Column statistics table (mean, std, min, max, median, q25, q75) — existing data, **not rendered**
- Per-column feature distribution box plots (from summary stats) — **new chart**
- Correlation heatmap — existing chart
- Feature box plots per cluster — existing chart
- Anomaly detection overlay — existing chart

**Segmentation tab:**
- Algorithm + params summary — existing data, **not rendered**
- Clusters found + silhouette score cards — existing data
- Cluster profiles table — existing data
- 2D/3D cluster scatter — existing charts
- Cluster size distribution — existing chart
- Silhouette quality — existing chart
- Parallel coordinates — existing chart

**Above tabs (top-level):**
- LLM insights panel (unchanged, stays HTMX lazy-loaded)
- Save button (moved from bottom to top)

### Chart Filtering (Jinja-level)

Charts are filtered by `chart_type` directly in each section template — no Python constant needed:

```jinja2
{# section_eda.html #}
{% for chart in charts if chart.chart_type in ["correlation_heatmap", "feature_boxplots", "anomaly_overlay", "feature_distributions"] %}

{# section_segmentation.html #}
{% for chart in charts if chart.chart_type in ["scatter_2d", "scatter_3d", "cluster_sizes", "silhouette", "parallel_coordinates"] %}
```

## Acceptance Criteria

- [x] Analysis results render in 3 tabs, all inline in the POST response
- [x] EDA tab is shown by default; other tabs are hidden via `display: none`
- [x] Tab switching is instant (pure JS show/hide, no network request)
- [x] Tab switch triggers `Plotly.Plots.resize()` for correct chart dimensions
- [x] LLM insights panel renders above tabs (unchanged, still HTMX lazy-loaded)
- [x] Save button renders above tabs and works correctly
- [x] Pre-Processing tab shows encoding info, ordinal warnings, dropped columns, before/after feature count
- [x] EDA tab shows stats cards, missing values, column stats table, distribution box plots, correlation heatmap, box plots, anomaly overlay
- [x] Segmentation tab shows algorithm/params, cluster cards, profiles, scatter plots, cluster sizes, silhouette, parallel coordinates
- [x] Tabs have ARIA roles (`role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected`)
- [x] Dark/light theme works correctly for tab styling
- [x] All existing tests pass; new tests cover new data and charts
- [x] Distribution box plots limited to 12 columns max

## Implementation

### 1. Add `DroppedColumn` model and new fields to `AnalysisOutput`

**File:** `app/models/schemas.py`

```python
class DroppedColumn(BaseModel):
    column: str
    reason: str


class AnalysisOutput(BaseModel):
    # ... existing fields ...
    missing_values: dict[str, int] = {}
    dropped_columns: list[DroppedColumn] = []
    original_column_count: int = 0
```

### 2. Add `PreprocessResult` and `EncodingResult` dataclasses

**File:** `app/services/analysis_engine.py`

Replace unwieldy tuples with named results:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class EncodingResult:
    encoded_df: pd.DataFrame
    encoding_info: list[dict[str, Any]]
    skipped_columns: list[dict[str, str]]

@dataclass(frozen=True)
class PreprocessResult:
    numeric_df: pd.DataFrame
    scaled_df: pd.DataFrame
    feature_names: list[str]
    encoding_info: list[dict[str, Any]]
    dropped_columns: list[dict[str, str]]
```

Update `encode_categoricals()` to return `EncodingResult`:

```python
def encode_categoricals(df, categorical_columns, ...) -> EncodingResult:
    skipped_columns = []
    # ... existing logic, but collect skipped columns:
    if nunique <= 1:
        skipped_columns.append({"column": col, "reason": "Single value"})
    if cardinality_ratio > 0.9:
        skipped_columns.append({"column": col, "reason": f"ID-like ({nunique} unique values)"})
    # ...
    return EncodingResult(encoded_df=result, encoding_info=encoding_info, skipped_columns=skipped_columns)
```

Update `preprocess()` to return `PreprocessResult`:

```python
def preprocess(df, columns, categorical_columns) -> PreprocessResult:
    dropped_columns = []

    # Track >50% NaN drops
    threshold = len(numeric_df) * 0.5
    for col in numeric_df.columns:
        if numeric_df[col].count() < threshold:
            dropped_columns.append({"column": col, "reason": "Over 50% missing values"})
    numeric_df = numeric_df.dropna(axis=1, thresh=int(threshold))

    # Categorical pipeline
    if categorical_columns:
        enc_result = encode_categoricals(df.loc[numeric_df.index], categorical_columns)
        encoding_info = enc_result.encoding_info
        dropped_columns.extend(enc_result.skipped_columns)
        if not enc_result.encoded_df.empty:
            combined_df = pd.concat([numeric_df, enc_result.encoded_df], axis=1)
        else:
            combined_df = numeric_df
    # ...

    # Track zero-variance drops
    zero_var_cols = variances[variances == 0].index.tolist()
    for col in zero_var_cols:
        dropped_columns.append({"column": col, "reason": "Zero variance"})

    return PreprocessResult(
        numeric_df=combined_df,
        scaled_df=scaled_df,
        feature_names=feature_names,
        encoding_info=encoding_info,
        dropped_columns=dropped_columns,
    )
```

### 3. Compute new data in `run()`

**File:** `app/services/analysis_engine.py`

```python
def run(df, ...):
    # Compute missing values BEFORE preprocessing
    missing_values = {
        col: count
        for col in df.columns
        if (count := int(df[col].isna().sum())) > 0
    }
    original_column_count = len(df.columns)

    # Preprocess
    result = preprocess(df, columns, categorical_columns)

    # Use named fields instead of tuple unpacking
    coords_2d, coords_3d = reduce_dimensions(result.scaled_df)
    labels, n_clust, sil_score, params = cluster(result.scaled_df, algorithm, n_clusters)
    profiles = profile_clusters(result.numeric_df, result.scaled_df, labels, result.feature_names, result.encoding_info)
    anomaly_labels, anomaly_scores = detect_anomalies(result.scaled_df, contamination)
    corr_matrix, col_stats = compute_stats(result.numeric_df, result.feature_names)

    return AnalysisOutput(
        ...
        feature_names=result.feature_names,
        encoding_info=result.encoding_info,
        missing_values=missing_values,
        dropped_columns=[
            DroppedColumn(column=d["column"], reason=d["reason"])
            for d in result.dropped_columns
        ],
        original_column_count=original_column_count,
    )
```

### 4. Add feature distribution box plot chart

**File:** `app/services/visualization.py`

Uses `go.Box` with pre-computed quartiles from `column_stats` — an honest representation of the five-number summary (unlike feeding stats into `go.Histogram` which would produce misleading charts):

```python
def feature_distributions(analysis: AnalysisOutput) -> ChartData:
    """Per-column distribution box plots from summary stats (max 12 columns)."""
    features = analysis.feature_names[:12]
    n = len(features)
    cols = min(n, 3)
    rows = math.ceil(n / cols)

    fig = make_subplots(rows=rows, cols=cols, subplot_titles=features)
    for i, feat in enumerate(features):
        r, c = divmod(i, cols)
        stats = analysis.column_stats.get(feat, {})
        if not stats:
            continue
        fig.add_trace(
            go.Box(
                lowerfence=[stats["min"]],
                q1=[stats["q25"]],
                median=[stats["median"]],
                q3=[stats["q75"]],
                upperfence=[stats["max"]],
                mean=[stats["mean"]],
                name=feat,
                showlegend=False,
            ),
            row=r + 1, col=c + 1,
        )

    fig.update_layout(title="Feature Distributions", height=300 * rows)
    return _to_chart(fig, "feature_distributions", "Feature Distributions")
```

Add to `generate_all()`:

```python
def generate_all(analysis):
    generators = [
        scatter_2d, scatter_3d, cluster_sizes, feature_boxplots,
        correlation_heatmap, silhouette_plot, parallel_coordinates,
        anomaly_overlay, feature_distributions,  # new — 9 charts total
    ]
    # ... existing logic ...
```

### 5. Rewrite `analysis_results.html` (tab shell with inline includes)

**File:** `app/templates/partials/analysis_results.html`

Replace entire content:

```html
<h2>{{ analysis.title }}</h2>

{% if insights_enabled %}
<article id="cluster-insights"
         hx-get="/api/analysis/{{ analysis.id }}/insights"
         hx-trigger="load"
         hx-swap="innerHTML">
    <p aria-busy="true">Generating insights...</p>
</article>
{% endif %}

<!-- Save button -->
<div style="margin-top: 1rem; text-align: center;">
    <button hx-post="/api/analysis/{{ analysis.id }}/save"
            hx-target="#save-status"
            hx-swap="innerHTML">
        Save Analysis
    </button>
    <div id="save-status" style="margin-top: 0.5rem;"></div>
</div>

<!-- Tab bar -->
<div class="analysis-tabs" role="tablist" aria-label="Analysis sections">
    <button role="tab" aria-selected="false" aria-controls="tab-preprocessing"
            data-tab="preprocessing" class="tab-btn">Pre-Processing</button>
    <button role="tab" aria-selected="true" aria-controls="tab-eda"
            data-tab="eda" class="tab-btn active">EDA</button>
    <button role="tab" aria-selected="false" aria-controls="tab-segmentation"
            data-tab="segmentation" class="tab-btn">Segmentation</button>
</div>

<!-- Tab panels — all rendered inline, toggled via JS -->
<div id="tab-preprocessing" role="tabpanel" class="tab-panel" style="display: none;">
    {% include "partials/section_preprocessing.html" %}
</div>

<div id="tab-eda" role="tabpanel" class="tab-panel">
    {% include "partials/section_eda.html" %}
</div>

<div id="tab-segmentation" role="tabpanel" class="tab-panel" style="display: none;">
    {% include "partials/section_segmentation.html" %}
</div>
```

### 6. Create 3 section partials

**File:** `app/templates/partials/section_preprocessing.html`

- Before/after comparison: `analysis.original_column_count` columns → `analysis.feature_names|length` features
- Encoding info table (from `analysis.encoding_info`), with ordinal warnings for label-encoded
- Dropped columns summary (from `analysis.dropped_columns`), conditionally rendered
- Empty state if no encoding and no drops: "All columns are numeric. No transformations were applied."

**File:** `app/templates/partials/section_eda.html`

- Stats cards: Data Points, Features Used, Anomalies count
- Missing values table (from `analysis.missing_values`), conditionally rendered
- Column statistics table (from `analysis.column_stats` — mean, std, min, max, median, q25, q75)
- Charts filtered in Jinja: `{% for chart in charts if chart.chart_type in ["correlation_heatmap", "feature_boxplots", "anomaly_overlay", "feature_distributions"] %}`

**File:** `app/templates/partials/section_segmentation.html`

- Algorithm + params card: `analysis.algorithm`, `analysis.params`
- Clusters found + silhouette score cards
- Cluster profiles (existing `<details>` markup, moved from current template)
- Charts filtered in Jinja: `{% for chart in charts if chart.chart_type in ["scatter_2d", "scatter_3d", "cluster_sizes", "silhouette", "parallel_coordinates"] %}`

### 7. Add tab switching JS

**File:** `app/static/js/app.js`

```javascript
// --- Analysis tab switching ---
document.body.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-tab]");
    if (!btn) return;

    var tabId = btn.getAttribute("data-tab");
    var tablist = btn.closest("[role='tablist']");
    if (!tablist) return;

    // Update tab buttons
    tablist.querySelectorAll("[role='tab']").forEach(function (t) {
        t.classList.remove("active");
        t.setAttribute("aria-selected", "false");
    });
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");

    // Show/hide panels
    var panels = tablist.parentElement.querySelectorAll("[role='tabpanel']");
    panels.forEach(function (panel) {
        var isTarget = panel.id === "tab-" + tabId;
        panel.style.display = isTarget ? "" : "none";
        // Resize Plotly charts in newly visible panel
        if (isTarget && typeof Plotly !== "undefined") {
            panel.querySelectorAll("[data-plotly]").forEach(function (el) {
                Plotly.Plots.resize(el);
            });
        }
    });
});
```

### 8. Add tab CSS

**File:** `app/static/css/style.css`

```css
/* Analysis tabs */
.analysis-tabs {
    display: flex;
    gap: 0;
    border-bottom: 2px solid var(--pico-muted-border-color);
    margin: 1.5rem 0 0;
}

.tab-btn {
    background: none;
    border: none;
    border-bottom: 3px solid transparent;
    padding: 0.75rem 1.25rem;
    cursor: pointer;
    font-size: 0.95rem;
    color: var(--pico-muted-color);
    margin-bottom: -2px;
}

.tab-btn:hover {
    color: var(--pico-color);
}

.tab-btn.active {
    color: var(--pico-primary);
    border-bottom-color: var(--pico-primary);
    font-weight: 600;
}

.tab-panel {
    padding: 1.5rem 0;
}
```

### 9. Persist new fields to SQLite

**File:** `app/services/storage.py`

Add new fields to the `analysis_result` JSON blob:

```python
analysis_result = json.dumps({
    "n_clusters": analysis.n_clusters,
    "silhouette_score": analysis.silhouette_score,
    "cluster_profiles": [p.model_dump() for p in analysis.cluster_profiles],
    "cluster_labels": analysis.cluster_labels,
    "anomaly_labels": analysis.anomaly_labels,
    "column_stats": analysis.column_stats,
    "missing_values": analysis.missing_values,
    "dropped_columns": [d.model_dump() for d in analysis.dropped_columns],
    "original_column_count": analysis.original_column_count,
})
```

### 10. Tests

**File:** `tests/test_analysis.py`

- [ ] `test_analysis_returns_tabbed_results` — POST /api/analyze response contains tab bar and all 3 section panels
- [ ] `test_eda_charts_in_eda_section` — correlation heatmap, box plots, anomaly overlay, feature distributions appear in EDA panel
- [ ] `test_segmentation_charts_in_segmentation_section` — scatter, cluster sizes, silhouette, parallel coordinates appear in Segmentation panel
- [ ] `test_feature_distributions_generated` — new chart type (9 total) included in generate_all output
- [ ] `test_dropped_columns_reported` — PreprocessResult includes dropped column info (>50% NaN, zero-variance, ID-like)
- [ ] `test_missing_values_computed` — run() populates missing_values field from pre-imputation DataFrame
- [ ] `test_preprocess_result_dataclass` — preprocess() returns PreprocessResult with named fields
- [ ] `test_encoding_result_dataclass` — encode_categoricals() returns EncodingResult with skipped_columns
- [ ] `test_feature_distributions_empty_stats` — feature_distributions handles missing column_stats gracefully
- [ ] Update existing tests that destructure preprocess() 4-tuple → use PreprocessResult fields

## Files Modified

| File | Change |
|------|--------|
| `app/models/schemas.py` | Add `DroppedColumn` model. Add `missing_values`, `dropped_columns`, `original_column_count` to `AnalysisOutput` |
| `app/services/analysis_engine.py` | Add `PreprocessResult` and `EncodingResult` dataclasses. Update `preprocess()` and `encode_categoricals()` return types. Compute missing values and dropped columns in `run()` |
| `app/services/visualization.py` | Add `feature_distributions()` generator using `go.Box`. Include in `generate_all()` (9 charts total) |
| `app/services/storage.py` | Persist `missing_values`, `dropped_columns`, `original_column_count` in `analysis_result` JSON |
| `app/templates/partials/analysis_results.html` | Complete rewrite: tab bar + 3 inline `{% include %}` sections |
| `app/templates/partials/section_preprocessing.html` | **New** — Pre-Processing section partial |
| `app/templates/partials/section_eda.html` | **New** — EDA section partial |
| `app/templates/partials/section_segmentation.html` | **New** — Segmentation section partial |
| `app/static/js/app.js` | Add tab switching with ARIA + Plotly resize |
| `app/static/css/style.css` | Add `.analysis-tabs`, `.tab-btn`, `.tab-panel` styles |
| `tests/test_analysis.py` | Add ~10 new tests, update existing tests for PreprocessResult |

## What was removed from v1 of this plan (after review)

| Removed | Why |
|---------|-----|
| 3 new GET section endpoints | Inline rendering eliminates need — data already in memory |
| `CHART_SECTIONS` Python constant | Chart filtering done in Jinja templates instead |
| HTMX lazy-load `hx-trigger="load"` on tab panels | No latency benefit — all data computed before POST returns |
| Cache race condition fix (`saved.py` line 30) | No lazy-loading means no race — `del` on save is fine |
| Arrow key keyboard navigation | YAGNI — standard Tab/Enter works; add later if needed |
| `go.Histogram` with 5 summary stats | Produces misleading charts — replaced with `go.Box` |
| `list[dict[str, str]]` for dropped columns | Replaced with `DroppedColumn` Pydantic model |
| 5-tuple from `preprocess()` | Replaced with `PreprocessResult` dataclass |
| `visibility: hidden; position: absolute;` | Contradicted later in plan — using `display: none` consistently |

## Edge Cases

- **All-numeric dataset (no categoricals):** Pre-Processing tab shows "All columns are numeric. No transformations were applied." Still shows before/after feature count.
- **No missing values:** Missing values section in EDA conditionally hidden: "No missing values detected."
- **DBSCAN noise cluster (id=-1):** Handled in existing template logic (Segmentation tab).
- **Many features (>12):** Distribution box plots capped at 12 columns. Existing box plots capped at 6. Parallel coordinates capped at 8.
- **Plotly in hidden tabs:** Hidden panels use `display: none`. Tab switch calls `Plotly.Plots.resize()` to fix dimensions. Charts render at 0x0 initially but resize correctly on first tab show.
- **Dark mode:** Tab styles use Pico CSS variables for automatic theme compatibility.
- **Saved analyses before this change:** Older saved analyses without `missing_values`/`dropped_columns`/`original_column_count` in JSON will load fine — Pydantic defaults to empty dict/list/0.

## Deferred

- Saved analysis detail view restructuring (follow-up ticket)
- Tab badge counts (e.g., "Pre-Processing (3 warnings)")
- Independent per-section analysis triggers
- Tab state persistence across page reloads
- HTMX lazy-load tabs (if per-section triggers are added later)

## References

- Ticket: #27
- Brainstorm: `docs/brainstorms/2026-02-08-analysis-sections-restructure-brainstorm.md`
- Institutional learning: `docs/solutions/architecture-patterns/async-llm-insights-with-graceful-degradation.md`
- Institutional learning: `docs/solutions/ui-bugs/pico-css-color-override-specificity.md`
- Current template: `app/templates/partials/analysis_results.html`
- Analysis engine: `app/services/analysis_engine.py:426` (`run()` function)
- Visualization service: `app/services/visualization.py:249` (`generate_all()`)
