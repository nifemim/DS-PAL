---
title: "feat: Categorical encoding v2 — reverse centroids, adaptive DBSCAN, ordinal warning"
type: feat
date: 2026-02-08
ticket: 12
brainstorm: docs/brainstorms/2026-02-08-categorical-encoding-v2-brainstorm.md
---

# feat: Categorical encoding v2

Three improvements to categorical encoding and analysis quality, revised after multi-agent review.

**Scope reduction:** The original plan had 5 items. Review dropped 2 (per-column encoding override, heatmap sibling suppression) and simplified 2 (reverse centroids, adaptive eps). See [Review Feedback](#review-feedback) for rationale.

## 1. Reverse-mapped cluster centroids

**Current:** Cluster profiles show raw mean values for label-encoded columns (e.g. `4.73`), which are meaningless to users.

**Change:** Store a `label_mapping: dict[str, list[str]]` in each encoding_info entry during encoding. In `profile_clusters()`, map label-encoded centroid values back to the nearest original category name using that list.

**Why plain dict instead of LabelEncoder:** The original plan proposed storing `LabelEncoder` instances alongside encoding_info. Review flagged this as problematic — LabelEncoder isn't serializable, would bloat the return type, and `inverse_transform` can raise on out-of-bounds values. A plain `list[str]` (where index = encoded value) is simpler, serializable, and safe to index with bounds checking.

### Files

- `app/services/analysis_engine.py:encode_categoricals()` — At each label-encoding site (lines 101-110 and 123-133), capture the encoder's `classes_` as a list and add `"label_mapping": list(le.classes_)` to the encoding_info dict entry

```python
# Inside encode_categoricals(), after le.fit_transform (line ~103):
le = LabelEncoder()
encoded = pd.Series(le.fit_transform(series.astype(str)), index=series.index, name=col)
encoded_parts.append(encoded.to_frame())
encoding_info.append({
    "original_column": col,
    "encoding_type": "label",
    "new_columns": [col],
    "cardinality": nunique,
    "label_mapping": list(le.classes_),  # NEW: ["Compact", "SUV", "Sedan", ...]
})
```

- `app/services/analysis_engine.py:profile_clusters()` — Accept `encoding_info` param. For label-encoded features, map `round(centroid_value)` to the original category name via the `label_mapping` list

```python
def profile_clusters(
    numeric_df: pd.DataFrame,
    scaled_df: pd.DataFrame,
    labels: np.ndarray,
    feature_names: List[str],
    encoding_info: Optional[List[Dict[str, Any]]] = None,  # NEW
) -> List[ClusterProfile]:
    # Build lookup: {encoded_column_name: ["cat_a", "cat_b", ...]}
    label_maps = {}
    for enc in (encoding_info or []):
        if enc["encoding_type"] == "label" and "label_mapping" in enc:
            label_maps[enc["original_column"]] = enc["label_mapping"]

    # ... existing centroid loop ...
    for col in feature_names:
        raw_mean = round(float(cluster_data[col].mean()), 4)
        if col in label_maps:
            mapping = label_maps[col]
            idx = max(0, min(round(raw_mean), len(mapping) - 1))
            centroid[col] = mapping[idx]  # "Sedan" instead of 4.73
        else:
            centroid[col] = raw_mean
```

- `app/services/analysis_engine.py:run()` — Pass `encoding_info` to `profile_clusters()`

```python
# Line ~421:
profiles = profile_clusters(numeric_df, scaled_df, labels, feature_names, encoding_info)
```

- `app/models/schemas.py:ClusterProfile` — Widen centroid value type to accept both floats and strings

```python
class ClusterProfile(BaseModel):
    cluster_id: int
    size: int
    percentage: float
    centroid: Dict[str, Any] = {}  # float for numeric, str for label-encoded
    top_features: List[Dict[str, Any]] = []
```

- `app/templates/partials/analysis_results.html` — No template changes needed. The centroid values already render via `{{ feat.cluster_mean }}` which works for both floats and strings.

**Note:** The `top_features` list in cluster profiles also shows `cluster_mean` and `overall_mean` for the top distinguishing features. For label-encoded columns, these will now show category names in `centroid` but the z-deviation is still computed in scaled space (correct behavior — deviation is meaningful, raw mean isn't).

## 2. Adaptive DBSCAN eps

**Current:** `eps=0.5` is hardcoded (line 269). Performs poorly in higher-dimensional post-encoding spaces.

**Change:** Use median k-nearest-neighbor distance as eps. This is a well-known heuristic that's simpler and more robust than the custom second-derivative knee detector originally proposed.

**Why median instead of knee detection:** The review flagged that a custom second-derivative knee detector is unreliable — it's sensitive to noise, requires smoothing parameters, and can pick degenerate values. The median of k-distances is a single-line NumPy operation that's well-established in the literature as a reasonable default.

### Files

- `app/services/analysis_engine.py` — Add `_auto_eps()` function

```python
_MAX_KNN_SAMPLES = 10_000  # Cap kNN to avoid O(n^2) at large n

def _auto_eps(scaled_data: np.ndarray, min_samples: int) -> float:
    """Auto-select DBSCAN eps using median k-nearest-neighbor distance."""
    from sklearn.neighbors import NearestNeighbors

    # Subsample large datasets to bound kNN to ~1-3 seconds
    if len(scaled_data) > _MAX_KNN_SAMPLES:
        rng = np.random.default_rng(42)
        indices = rng.choice(len(scaled_data), _MAX_KNN_SAMPLES, replace=False)
        sample = scaled_data[indices]
    else:
        sample = scaled_data

    k = min(min_samples, len(sample) - 1)
    nn = NearestNeighbors(n_neighbors=k)
    nn.fit(sample)
    distances, _ = nn.kneighbors(sample)
    # Use median of k-th neighbor distances as eps
    eps = float(np.median(distances[:, -1]))
    # Floor to avoid degenerate eps=0 on identical points
    eps = max(eps, 0.01)
    logger.info("Auto-selected DBSCAN eps=%.4f (median %d-NN distance, n=%d)", eps, k, len(sample))
    return eps
```

- `app/services/analysis_engine.py:cluster()` — Replace hardcoded `eps=0.5` with `_auto_eps()`

```python
elif algorithm == "dbscan":
    min_samples = max(5, len(values) // 100)
    eps = _auto_eps(values, min_samples)
    model = DBSCAN(eps=eps, min_samples=min_samples)
    labels = model.fit_predict(values)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    params = {"eps": round(eps, 4), "min_samples": min_samples}
```

## 3. Label encoding ordinal warning

**Current:** The encoding info section mentions "label encoding" but doesn't warn that label encoding imposes an artificial ordinal relationship.

**Change:** Add a warning note next to label-encoded columns in both the preview and the analysis results.

### Files

- `app/templates/partials/dataset_preview.html` — Next to columns where `suggested_encoding == "label"`, add warning text (line ~109)

```html
<label>
    <input type="checkbox" name="categorical_columns" value="{{ col.name }}" checked>
    {{ col.name }}
    <small>{{ col.cardinality }} unique — {{ col.suggested_encoding }}
        {% if col.suggested_encoding == "label" %}
        <em>(assumes ordinal order)</em>
        {% endif %}
    </small>
</label>
```

- `app/templates/partials/analysis_results.html` — In the encoding info section, add warning for label-encoded columns (line ~8-9)

```html
<li><strong>{{ enc.original_column }}</strong>: {{ enc.encoding_type }} encoding
    ({{ enc.cardinality }} categories{% if enc.new_columns|length > 1 %} &rarr; {{ enc.new_columns|length }} features{% endif %})
    {% if enc.encoding_type == "label" %}
    <em>&mdash; assumes ordinal order</em>
    {% endif %}
</li>
```

## Acceptance Criteria

- [x] Cluster profiles show category names instead of raw floats for label-encoded features
- [x] `encoding_info` entries for label-encoded columns include `label_mapping` list
- [x] Centroid reverse-mapping handles edge cases (bounds check on index)
- [x] DBSCAN auto-selects eps via median k-NN distance (no hardcoded 0.5)
- [x] Auto-eps has floor of 0.01 to prevent degenerate clustering
- [x] Label-encoded columns show ordinal warning in preview and results
- [x] `ClusterProfile.centroid` accepts both float and str values
- [x] All existing tests pass
- [x] New tests for reverse-mapped centroids and auto-eps

## Tests

### Files

- `tests/test_analysis.py` — Add to existing test file

```python
class TestReverseMappedCentroids:
    """Tests for label-encoded centroid reverse-mapping."""

    def test_label_encoded_centroid_shows_category_name(self):
        """profile_clusters maps label-encoded centroid float to nearest category."""

    def test_centroid_clamps_out_of_bounds_index(self):
        """Round(mean) outside [0, len(mapping)-1] is clamped, not crashed."""

    def test_numeric_centroid_unchanged(self):
        """Non-label-encoded features still show float centroids."""

    def test_encoding_info_includes_label_mapping(self):
        """encode_categoricals adds label_mapping list to label-encoded entries."""


class TestAutoEps:
    """Tests for adaptive DBSCAN eps selection."""

    def test_auto_eps_returns_positive_float(self):
        """_auto_eps returns a positive float for valid scaled data."""

    def test_auto_eps_floor(self):
        """_auto_eps returns at least 0.01 even for identical points."""

    def test_dbscan_uses_auto_eps(self):
        """cluster() with algorithm='dbscan' uses _auto_eps, not hardcoded 0.5."""

    def test_auto_eps_subsamples_large_data(self):
        """_auto_eps subsamples when n > _MAX_KNN_SAMPLES and still returns valid eps."""
```

## Review Feedback

Changes from multi-agent review (Kieran, DHH, Architecture, Performance, Security, Simplicity, Data Integrity):

### Dropped items

1. **Per-column encoding override (original #1)** — YAGNI. Adds a `<select>` per column, dynamic `encoding_override__*` form fields requiring `await request.form()` parsing, and a new parameter threading through 3 layers. No user has requested this. The auto-detection (one-hot ≤10, label >10) with on/off checkboxes is sufficient. Can be added later if demand emerges.

2. **Correlation heatmap sibling suppression (original #3)** — Cosmetic. Would require introducing `None`/`NaN` into the correlation matrix (`Dict[str, Dict[str, float]]` → `float | None`), plus handling None in `visualization.py`'s text formatting (`f"{v:.2f}"` would crash on None). Two files changed for a visual nicety. The anti-correlations between one-hot siblings are mathematically correct — they're just noisy, not wrong.

### Simplified items

3. **Reverse-mapped centroids** — Use plain `list[str]` in encoding_info instead of storing `LabelEncoder` instances. Simpler, serializable, no out-of-bounds crash risk with bounds clamping.

4. **Adaptive DBSCAN eps** — Use `np.median(distances[:, -1])` instead of custom second-derivative knee detector. The knee detector would need smoothing parameters, is sensitive to noise, and is ~30 lines of numerical code that's hard to test. The median heuristic is 1 line, well-established, and deterministic.

### Kept as-is

5. **Ordinal warning** — Simple 2-line template change per file. No backend changes needed.

### Out of scope (deferred)

- **Column name sanitization** — Review noted that column names from user-uploaded CSVs flow unsanitized into Plotly chart HTML rendered via `|safe`. Plotly's JSON serialization provides some protection, but defense-in-depth sanitization of column names at the preprocessing boundary would be prudent. Deferred to a separate security-focused ticket.

## References

- `app/services/analysis_engine.py:20-150` — Current `encode_categoricals()`
- `app/services/analysis_engine.py:101-110` — Label encoding site (first)
- `app/services/analysis_engine.py:123-133` — Label encoding site (downgrade fallback)
- `app/services/analysis_engine.py:268-272` — Current DBSCAN config with hardcoded eps=0.5
- `app/services/analysis_engine.py:301-346` — Current `profile_clusters()`
- `app/services/analysis_engine.py:395-455` — `run()` pipeline orchestrator
- `app/models/schemas.py:79-84` — `ClusterProfile` model
- `app/templates/partials/dataset_preview.html:100-124` — Current categorical UI
- `app/templates/partials/analysis_results.html:3-12` — Encoding info display
- `docs/brainstorms/2026-02-08-categorical-encoding-v2-brainstorm.md` — Original design decisions
