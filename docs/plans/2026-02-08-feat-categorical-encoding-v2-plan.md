---
title: "feat: Categorical encoding v2 — per-column override, reverse centroids, heatmap cleanup, adaptive DBSCAN"
type: feat
date: 2026-02-08
ticket: 12
brainstorm: docs/brainstorms/2026-02-08-categorical-encoding-v2-brainstorm.md
---

# feat: Categorical encoding v2

Five improvements to categorical encoding and analysis quality.

## 1. Per-column encoding override

**Current:** Auto-selects one-hot (≤10 unique) or label (>10 unique). User can only toggle columns on/off.

**Change:** Add a `<select>` dropdown next to each categorical column checkbox with options: `auto`, `one-hot`, `label`.

### Files

- `app/templates/partials/dataset_preview.html` — Add `<select name="encoding_override__{col.name}">` next to each categorical checkbox
- `app/routers/analysis.py:run_analysis()` — Parse `encoding_override__*` form fields into a dict `{column_name: "one-hot"|"label"|"auto"}`
- `app/services/analysis_engine.py:encode_categoricals()` — Accept optional `encoding_overrides: dict` param. When a column has an override, use that method instead of auto-detecting

### Form field pattern

```html
<select name="encoding_override__{{ col.name }}">
    <option value="auto" selected>auto ({{ col.suggested_encoding }})</option>
    <option value="one-hot">one-hot</option>
    <option value="label">label</option>
</select>
```

## 2. Reverse-mapped cluster centroids

**Current:** Cluster profiles show raw mean values for label-encoded columns (e.g. `4.73`), which are meaningless.

**Change:** Store the `LabelEncoder` instance per column during encoding. In `profile_clusters()`, reverse-map label-encoded centroid values to the nearest original category name.

### Files

- `app/services/analysis_engine.py:encode_categoricals()` — Return `label_encoders: dict[str, LabelEncoder]` alongside encoding_info
- `app/services/analysis_engine.py:profile_clusters()` — Accept `label_encoders` param. For label-encoded features, map `round(centroid_value)` → `encoder.inverse_transform([rounded])[0]`
- `app/templates/partials/analysis_results.html` — Display mapped category name instead of raw float for label-encoded features

## 3. Correlation heatmap: suppress one-hot siblings

**Current:** One-hot encoded columns from the same source (e.g. `color_red`, `color_blue`) produce strong anti-correlations that clutter the heatmap.

**Change:** In the correlation matrix, set within-group one-hot sibling correlations to `None`/`NaN` so they render as blank cells.

### Files

- `app/services/analysis_engine.py:compute_stats()` — After computing correlation matrix, use `encoding_info` to identify one-hot sibling groups. Set `corr[col_a][col_b] = None` for all pairs within the same group
- `app/services/visualization.py:correlation_heatmap()` — Handle `None` values in the heatmap (render as blank/gray cells)

## 4. Adaptive DBSCAN eps

**Current:** `eps=0.5` is hardcoded. Performs poorly in higher-dimensional post-encoding spaces.

**Change:** Implement k-distance graph method to auto-select eps. Compute k-nearest-neighbor distances (k=min_samples), sort descending, find the "knee" point.

### Files

- `app/services/analysis_engine.py` — Add `_auto_eps(scaled_data, min_samples)` function:
  1. Compute k-nearest-neighbor distances using `sklearn.neighbors.NearestNeighbors`
  2. Sort distances descending
  3. Find knee point (maximum curvature) — use simple second-derivative method
  4. Return the distance at the knee as eps
- `app/services/analysis_engine.py:run_analysis()` — Replace `eps=0.5` with `eps=_auto_eps(values, min_samples)`

## 5. Label encoding ordinal warning

**Current:** The encoding info section mentions "label encoding" but doesn't warn about the ordinal assumption.

**Change:** Add a warning badge next to label-encoded columns in both the preview and the analysis results.

### Files

- `app/templates/partials/dataset_preview.html` — Next to columns where `suggested_encoding == "label"`, add: `<small class="warning">assumes ordinal order</small>`
- `app/templates/partials/analysis_results.html` — In the encoding info section, add warning text for label-encoded columns

## Acceptance Criteria

- [ ] Each categorical column has an encoding dropdown (auto/one-hot/label)
- [ ] Overriding encoding to one-hot or label works correctly in analysis
- [ ] Cluster profiles show category names instead of raw floats for label-encoded features
- [ ] One-hot sibling correlations are blanked out in the heatmap
- [ ] DBSCAN auto-selects eps via k-distance method (no hardcoded 0.5)
- [ ] Label-encoded columns show an ordinal warning in preview and results
- [ ] All existing tests pass
- [ ] New tests for encoding overrides and auto-eps

## References

- `app/services/analysis_engine.py:20-150` — Current `encode_categoricals()`
- `app/services/analysis_engine.py:268-272` — Current DBSCAN config
- `app/services/analysis_engine.py:317-336` — Current `profile_clusters()`
- `app/services/visualization.py:140-157` — Current `correlation_heatmap()`
- `app/templates/partials/dataset_preview.html:100-124` — Current categorical UI
