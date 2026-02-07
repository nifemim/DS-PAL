---
title: "feat: Add label encoding for categorical columns before clustering"
type: feat
date: 2026-02-06
ticket: "#10"
priority: medium
---

# Add Label Encoding for Categorical Columns Before Clustering

## Overview

Implement automatic encoding of non-numeric categorical columns so they can be included in clustering analysis. The system will auto-select the encoding method based on column cardinality (one-hot for low-cardinality, label encoding for high-cardinality), auto-encode columns by default, and allow users to toggle individual categorical columns on/off in the dataset preview form.

## Problem Statement

Currently, `preprocess()` in `app/services/analysis_engine.py:28` drops all non-numeric columns via `select_dtypes(include=["number"])`. This silently discards potentially valuable categorical features (e.g., "species", "region", "category") that could improve cluster separation. Users have no visibility into what was dropped or ability to include these columns.

## Proposed Solution

### Encoding Strategy (Auto-Select)

| Cardinality | Encoding | Rationale |
|-------------|----------|-----------|
| <= 10 unique values | One-hot (`pd.get_dummies`, `drop_first=True`) | Avoids false ordinal relationships; manageable dimensionality |
| > 10 unique values | Label encoding (`LabelEncoder`) | Prevents dimension explosion; trade-off acknowledged |

### Column Classification Rules

| Column Type | Detection | Handling |
|-------------|-----------|----------|
| Numeric (`int64`, `float64`) | `select_dtypes(include=["number"])` | Passthrough (existing behavior) |
| Boolean (`bool`) | `dtype == bool` | Cast to `int` (0/1) directly; show as "boolean (auto-converted)" |
| Categorical (`object`, `category`) | Not numeric, not bool, not datetime | Encode per cardinality rules |
| Datetime (`datetime64`) | `select_dtypes(include=["datetime"])` | Exclude from analysis; show as "datetime (excluded)" |
| Numeric-as-string | `object` dtype but >80% values coerce to numeric | Coerce to float via `pd.to_numeric(errors='coerce')`; treat as numeric |
| ID-like | `nunique() / len(df) > 0.9` | Auto-exclude; show notice "appears to be an identifier" |
| Single-value | `nunique() == 1` | Auto-exclude; show notice "constant value" |
| All-NaN | `isna().all()` | Auto-exclude (caught by existing >50% NaN threshold) |

### User Controls

- All categorical columns are **checked by default** (auto-encode)
- Users can **uncheck** to exclude specific categorical columns
- Encoding method is **auto-selected** (no per-column override in v1)
- Excluded/flagged columns show a brief reason in the UI

## Technical Approach

### Pipeline Ordering (New)

```
1. Separate selected columns into numeric + categorical
2. Categorical pipeline:
   a. Drop columns with >50% NaN
   b. Drop ID-like columns (cardinality ratio > 0.9)
   c. Drop single-value columns
   d. Attempt numeric coercion on object columns
   e. Cast booleans to int
   f. Impute remaining NaN with "MISSING" sentinel
   g. Encode: one-hot (<=10 cardinality, drop_first=True) or label (>10)
3. Numeric pipeline: existing behavior (drop >50% NaN cols, drop NaN rows, median impute)
4. Concatenate encoded + numeric
5. Drop any zero-variance columns post-encoding
6. Scale with StandardScaler
7. Verify >= 2 features remain
```

### Cap on Dimensions

If total post-encoding feature count would exceed **100 columns**, fall back from one-hot to label encoding for the highest-cardinality columns until under the cap. Log which columns were downgraded.

## Acceptance Criteria

- [x] Categorical columns detected and shown in dataset preview modal with cardinality info
- [x] Categorical column toggles appear in the analysis config form (separate fieldset from numeric)
- [x] Encoding badge shown next to each categorical toggle (e.g., "one-hot" or "label")
- [x] Auto-encoding by default (all categorical checked), users can uncheck to exclude
- [x] Boolean columns auto-cast to 0/1
- [x] Datetime columns excluded with notice
- [x] ID-like columns auto-excluded with notice
- [x] Numeric-as-string columns auto-coerced
- [x] NaN in categorical columns handled (impute "MISSING")
- [x] Zero-variance columns dropped post-encoding
- [x] Transformation notice shown above analysis results (which columns encoded, what method)
- [x] Encoding metadata persisted in saved analyses
- [x] Full pipeline works with: all-numeric, mixed, all-categorical datasets
- [x] Tests cover all encoding paths and edge cases

## Files to Modify

### 1. Schema Changes — `app/models/schemas.py`

**`ColumnInfo` (line 42):** Add fields:
```python
cardinality: Optional[int] = None          # unique value count
suggested_encoding: Optional[str] = None   # "one-hot", "label", "boolean", "numeric-coerce", or None
is_id_like: bool = False                   # cardinality ratio > 0.9
```

**`DatasetPreview` (line 50):** Add field:
```python
categorical_columns: List[str] = []        # encodable categorical column names
```

**`AnalysisOutput` (line 83):** Add field:
```python
encoding_info: List[Dict[str, Any]] = []   # [{original_column, encoding_type, new_columns, cardinality}]
```

### 2. Preview Data Enrichment — `app/services/dataset_loader.py`

**`build_preview()` (line 152):** Enhance column iteration to compute:
- `cardinality` for non-numeric columns
- `suggested_encoding` based on classification rules
- `is_id_like` flag
- Populate `categorical_columns` list (excluding datetime, ID-like, single-value)
- Attempt numeric coercion detection for object columns

### 3. Encoding Logic — `app/services/analysis_engine.py`

**New function `encode_categoricals()`:**
```python
def encode_categoricals(
    df: pd.DataFrame,
    categorical_columns: List[str],
    cardinality_threshold: int = 10,
    max_total_features: int = 100,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """Encode categorical columns. Returns encoded DataFrame and encoding metadata."""
```

- Handles NaN imputation, boolean casting, numeric coercion
- Applies one-hot or label encoding per cardinality
- Respects the 100-feature cap
- Returns encoding info for the transformation notice

**Modify `preprocess()` (line 20):** Add `categorical_columns` parameter. Call `encode_categoricals()` before `select_dtypes`. Concatenate results. Drop zero-variance columns post-merge.

**Modify `run()` (line 245):** Accept and pass through `categorical_columns`. Include `encoding_info` in `AnalysisOutput`.

### 4. API Route — `app/routers/analysis.py`

**`run_analysis()` (line 17):** Add form parameter:
```python
categorical_columns: List[str] = Form([])
```
Pass to `analysis_engine.run()`.

### 5. Search Route — `app/routers/search.py`

**`preview_dataset()` (line 53):** Relax validation:
```python
# Old: len(preview.numeric_columns) < 2
# New: len(preview.numeric_columns) + len(preview.categorical_columns) < 2
```

### 6. Modal Preview Template — `app/templates/partials/modal_preview.html`

Add a "Cardinality" column to the column details table for non-numeric columns. Show encoding badge (e.g., `<mark>one-hot</mark>`, `<mark>label</mark>`, `<small>excluded</small>`) next to categorical columns.

### 7. Dataset Preview Template — `app/templates/partials/dataset_preview.html`

**Add categorical column fieldset (after numeric columns fieldset, line ~98):**
```html
{% if preview.categorical_columns %}
<fieldset>
  <legend>Categorical Columns (will be encoded)</legend>
  {% for col in preview.columns %}
    {% if col.name in preview.categorical_columns %}
    <label>
      <input type="checkbox" name="categorical_columns" value="{{ col.name }}" checked>
      {{ col.name }}
      <small>{{ col.cardinality }} unique — {{ col.suggested_encoding }}</small>
    </label>
    {% endif %}
  {% endfor %}
</fieldset>
{% endif %}
```

Show excluded columns (datetime, ID-like) as disabled with explanation.

### 8. Analysis Results Template — `app/templates/partials/analysis_results.html`

Add transformation notice section above results:
```html
{% if output.encoding_info %}
<details open>
  <summary>Column Transformations Applied</summary>
  <ul>
    {% for enc in output.encoding_info %}
    <li><strong>{{ enc.original_column }}</strong>: {{ enc.encoding_type }} encoding
        ({{ enc.cardinality }} categories{% if enc.new_columns %} → {{ enc.new_columns|length }} features{% endif %})</li>
    {% endfor %}
  </ul>
</details>
{% endif %}
```

### 9. Storage — `app/services/storage.py`

**`save_analysis()` (line 20):** Include `encoding_info` in the persisted analysis config so it can be displayed when viewing saved analyses.

### 10. Tests — `tests/test_analysis.py`

New test cases:
- `test_encode_categoricals_one_hot` — low-cardinality column produces expected dummy columns
- `test_encode_categoricals_label` — high-cardinality column produces single integer column
- `test_encode_categoricals_auto_select` — correct method chosen per cardinality
- `test_encode_boolean_columns` — booleans cast to 0/1
- `test_encode_nan_handling` — NaN imputed as "MISSING" category
- `test_encode_id_like_excluded` — high cardinality ratio columns excluded
- `test_encode_single_value_excluded` — constant columns excluded
- `test_encode_numeric_as_string` — object columns with numeric values coerced
- `test_preprocess_with_categoricals` — full preprocess pipeline with mixed types
- `test_preprocess_all_categorical` — dataset with zero numeric columns
- `test_run_full_pipeline_with_categoricals` — end-to-end with mixed DataFrame
- `test_dimension_cap` — one-hot encoding respects 100-feature limit

## Known Limitations (v1)

1. **Label encoding imposes ordinal relationships on nominal data.** A warning is shown in the transformation notice. Per-column encoding override is deferred to a future iteration.
2. **One-hot encoded columns produce noisy correlation heatmaps.** Anti-correlated dummies from the same source variable. No grouping in v1.
3. **Cluster profile centroids for label-encoded features are hard to interpret.** Centroid value "4.73" for a label-encoded column has no human meaning. Reverse-mapping deferred to v2.
4. **DBSCAN's hard-coded `eps=0.5` may need adjustment** for higher-dimensional post-encoding feature spaces. Not addressed in v1.
5. **No per-column encoding method override.** Users can only include/exclude, not choose between one-hot and label.

## References

- Current preprocessing: `app/services/analysis_engine.py:20-58`
- Dataset preview builder: `app/services/dataset_loader.py:152-197`
- Schemas: `app/models/schemas.py:42-59` (ColumnInfo), `50-59` (DatasetPreview)
- Modal preview template: `app/templates/partials/modal_preview.html`
- Dataset preview template: `app/templates/partials/dataset_preview.html:88-98`
- Analysis route: `app/routers/analysis.py:17-85`
- Search route validation: `app/routers/search.py:53`
- Storage: `app/services/storage.py:20`
- Tests: `tests/test_analysis.py`
