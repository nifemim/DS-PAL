---
title: "Speed up analysis pipeline and cluster description generation"
type: feat
date: 2026-03-09
tickets: [79]
---

# Speed Up Analysis Pipeline and Cluster Description Generation

## Overview

Reduce analysis wait time by tuning expensive ML operations and add progress step indicators so users see what's happening instead of a generic spinner. Focused on small-medium datasets (<1000 rows) which are the most common use case on the 512MB Render instance.

## Problem Statement

The analysis pipeline takes 30s-3+ minutes for some datasets. Users see a generic "Analyzing..." spinner with no indication of progress. The main bottlenecks are:

1. **`find_optimal_k()` silhouette sweep**: Runs KMeans with `n_init=10` for each candidate k (up to k=10), plus computes `silhouette_score` on the **full dataset** (O(n²)) for each k. This is the single most expensive step.
2. **Double PCA fit**: `reduce_dimensions()` runs `PCA(2).fit_transform()` and `PCA(3).fit_transform()` separately. Mathematically, the first 2 components of PCA(3) are identical to PCA(2), so one fit suffices.
3. **KMeans `n_init=10` in final fit**: Even when users specify k explicitly, `cluster()` runs 10 random restarts. Lowering to 5 halves the cost with minimal quality impact.
4. **No progress feedback**: The loading page shows a static spinner with no step indication.

## Proposed Solution

### Part 1: Algorithm Tuning (`app/services/analysis_engine.py`)

#### 1a. Single PCA fit

**File**: `app/services/analysis_engine.py:274-289`

Change `reduce_dimensions()` to run `PCA(n_components=min(3, n_features))` once and slice `[:, :2]` for the 2D projection.

```python
# Before: two separate fits
pca_2d = PCA(n_components=min(2, n_features))
coords_2d = pca_2d.fit_transform(values)
pca_3d = PCA(n_components=min(3, n_features))
coords_3d = pca_3d.fit_transform(values)

# After: one fit, slice for 2D
pca = PCA(n_components=min(3, n_features))
coords_3d = pca.fit_transform(values)
coords_2d = coords_3d[:, :2]
```

**Edge case**: When `n_features=2`, PCA produces only 2 components. The 3D scatter chart already handles this with the `if coords.shape[1] >= 3 else [0]` guard.

#### 1b. Faster silhouette sweep

**File**: `app/services/analysis_engine.py:292-317`

Two changes to `find_optimal_k()`:
- Lower `n_init` from 10 to 3 (the sweep only needs a rough ranking)
- Use `silhouette_score(..., sample_size=min(n, 1000))` — sklearn supports this natively

```python
# Before
km = KMeans(n_clusters=k, n_init=10, random_state=42)
labels = km.fit_predict(scaled_df.values)
score = silhouette_score(scaled_df.values, labels)

# After
km = KMeans(n_clusters=k, n_init=3, random_state=42)
labels = km.fit_predict(scaled_df.values)
score = silhouette_score(scaled_df.values, labels, sample_size=min(n, 1000), random_state=42)
```

**Note**: `max_k` is already capped at 10 (line 297). No change needed.

#### 1c. Lower n_init in cluster()

**File**: `app/services/analysis_engine.py:348`

One-line change: lower `n_init` from 10 to 5 in the final `KMeans` fit inside `cluster()`. This applies to both auto-detect and user-specified k paths.

```python
# Before
model = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)

# After
model = KMeans(n_clusters=n_clusters, n_init=5, random_state=42)
```

No return type changes. No caching. Just a parameter tweak.

### Part 2: Progress Step Tracking

#### 2a. Update pending_analyses dict with step info

**File**: `app/routers/analysis.py:32-81`

Add a `"step"` key to the pending dict that `_run_analysis_task` updates between `await` points. Three steps that map to actual `await` boundaries:

1. `"Downloading dataset"` — before `download_dataset()`
2. `"Analyzing data"` — before `run_in_executor(analysis_engine.run)`
3. `"Generating charts"` — before `run_in_executor(generate_all)`

```python
async def _run_analysis_task(app, analysis_id: str, params: dict):
    def set_step(step: str):
        """Update step display. Must be called from the event loop, not from executor threads."""
        entry = app.state.pending_analyses.get(analysis_id)
        if entry:
            entry["step"] = step

    try:
        set_step("Downloading dataset")
        file_path = await download_dataset(...)

        set_step("Analyzing data")
        df = await loop.run_in_executor(...)
        analysis = await loop.run_in_executor(...)

        set_step("Generating charts")
        charts = await loop.run_in_executor(...)
        ...
```

#### 2b. Pass step to loading template

**File**: `app/routers/analysis.py:130-148`

Pass `pending.get("step", "")` to the template context.

#### 2c. Update loading template

**File**: `app/templates/partials/analysis_loading.html`

Show step name instead of static text:

```html
<h3>Analyzing {{ dataset_name }}...</h3>
<p>Running <strong>{{ algorithm|upper }}</strong> clustering analysis.</p>
{% if step %}
<p><small>{{ step }}...</small></p>
{% else %}
<p><small>Starting analysis...</small></p>
{% endif %}
```

## Acceptance Criteria

- [ ] PCA runs once (3D) and slices for 2D
- [ ] `find_optimal_k` uses `n_init=3` and `silhouette_score(sample_size=min(n, 1000))`
- [ ] `cluster()` uses `n_init=5`
- [ ] Loading page shows current pipeline step
- [ ] All existing tests pass
- [ ] Analysis results are equivalent quality (Iris: similar k, silhouette above 0.4)

## Testing

### Tests to update
- `tests/test_analysis.py` — `reduce_dimensions` tests should verify single PCA fit still produces correct shapes
- `tests/test_analysis_routes.py` — mock pending dict may need `"step"` key

### New tests
- Test `reduce_dimensions` with exactly 2 features (edge case: coords_3d has only 2 columns)

## Files Changed

| File | Change |
|------|--------|
| `app/services/analysis_engine.py` | PCA single fit, silhouette sampling, n_init tuning |
| `app/routers/analysis.py` | Progress step tracking in `_run_analysis_task`, pass step to template |
| `app/templates/partials/analysis_loading.html` | Display current step name |
| `tests/test_analysis.py` | Update for PCA changes if needed |

## Out of Scope (follow-up tickets)

- Label caching across `find_optimal_k`/`cluster()` (marginal gain after 1b)
- Double-click submission protection
- Retry button on analysis error page
- Background tab polling throttle
- LLM insights speed (already lazy-loaded)
- Parallel chart generation (diminishing returns on small datasets)

## References

- Brainstorm: `docs/brainstorms/2026-03-09-speed-up-analysis-pipeline-brainstorm.md`
- sklearn `silhouette_score` `sample_size` parameter: reduces O(n²) to O(n×sample)
- PCA component nesting property: first N components are identical regardless of total requested
