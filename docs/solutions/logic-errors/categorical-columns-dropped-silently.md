---
title: "Categorical columns silently dropped during clustering"
category: logic-errors
module: analysis-engine
tags: [preprocessing, categorical-encoding, clustering, data-loss]
symptoms:
  - "Categorical columns missing from analysis"
  - "Only numeric columns used in clustering"
  - "Valuable features silently discarded"
date_solved: 2026-02-07
ticket: "#10"
pr: "#1"
---

# Categorical Columns Silently Dropped During Clustering

## Problem

When users ran clustering analysis on datasets containing categorical columns (e.g., "city", "gender", "product_category"), those columns were silently excluded from the analysis without any warning or notification. The `preprocess()` function in the analysis engine used `select_dtypes(include=["number"])` to filter the dataset, which discarded all non-numeric columns immediately.

This resulted in:
- Loss of potentially valuable features for clustering
- Incomplete analysis that didn't reflect the full dataset structure
- User confusion about why certain columns weren't being used
- Misleading results that only captured numeric relationships

For example, a customer segmentation dataset with demographic fields like "occupation", "region", and "product_preference" would have all these critical features removed, leaving only raw numeric fields like age and income.

## Root Cause

The core issue was in the `preprocess()` function in `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/services/analysis_engine.py`:

```python
# OLD CODE - silently dropped non-numeric columns
def preprocess(df: pd.DataFrame, columns: Optional[List[str]] = None):
    if columns:
        numeric_df = df[columns].select_dtypes(include=["number"])
    else:
        numeric_df = df.select_dtypes(include=["number"])

    # ... rest of preprocessing ...
```

The function had no mechanism to:
1. Accept categorical columns as input
2. Encode categorical data into numeric representations
3. Inform users which columns were being excluded
4. Detect which columns could be encoded vs. those that should be excluded (e.g., ID columns)

This design assumed all ML algorithms could only work with pre-numeric data, ignoring the standard practice of categorical encoding.

## Solution

The solution implemented a comprehensive categorical encoding pipeline with intelligent column classification and user control:

### 1. Column Classification System

Added `_classify_column()` function in `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/services/dataset_loader.py` to automatically detect column types:

- **Numeric**: Pass through unchanged
- **Boolean**: Convert to 0/1 integers
- **Datetime**: Exclude (temporal data requires special handling)
- **ID-like**: Exclude columns where cardinality ratio > 0.9 (likely unique identifiers)
- **Numeric-as-string**: Coerce to float if >80% of values are parseable as numbers
- **Categorical**: Recommend one-hot encoding (≤10 unique values) or label encoding (>10 unique)

### 2. Automatic Encoding Selection

Implemented `encode_categoricals()` function with smart encoding strategy:

```python
def encode_categoricals(
    df: pd.DataFrame,
    categorical_columns: List[str],
    cardinality_threshold: int = 10,
    max_total_features: int = 100,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """Encode categorical columns. Returns encoded DataFrame and encoding metadata."""
```

**Encoding rules:**
- **Low cardinality (≤10 unique)**: One-hot encoding (creates binary dummy variables)
- **High cardinality (>10 unique)**: Label encoding (creates single integer column)
- **Boolean**: Direct 0/1 mapping
- **Numeric strings**: Coerce to float with median imputation
- **NaN values**: Filled with "MISSING" sentinel before encoding
- **Constant columns**: Skipped (nunique ≤ 1)

### 3. Feature Cap Protection

To prevent dimension explosion from high-cardinality categorical columns:
- **100-feature maximum**: If one-hot encoding would exceed this limit, downgrade to label encoding
- Smart prioritization: Processes highest-cardinality columns first (most likely to need downgrading)
- Graceful degradation: Maintains analysis viability while preserving information

### 4. User Interface Controls

Updated analysis forms and templates to give users control:

**Schema changes** (`/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/models/schemas.py`):
- Added `categorical_columns` field to `AnalysisRequest`
- Added `encoding_info` field to `AnalysisOutput` to track transformations
- Added classification metadata to `ColumnInfo` (cardinality, suggested_encoding, is_id_like)

**Route changes** (`/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/routers/analysis.py`):
- Added `categorical_columns: List[str] = Form([])` parameter
- Passes categorical columns to analysis engine

**UI enhancements**:
- Dataset preview modal shows classification for each column
- Checkboxes allow users to include/exclude categorical columns
- Color-coded badges indicate encoding method (one-hot, label, boolean, etc.)
- ID-like columns are highlighted with warning badges

### 5. Transformation Transparency

Added encoding metadata to analysis results:
- Each encoded column includes: original name, encoding type, new column names, cardinality
- Results page displays "Transformations Applied" section showing all encodings
- Users can see exactly how their data was processed

## Code Examples

### Key Function: `encode_categoricals()`

```python
def encode_categoricals(
    df: pd.DataFrame,
    categorical_columns: List[str],
    cardinality_threshold: int = 10,
    max_total_features: int = 100,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """Encode categorical columns. Returns encoded DataFrame and encoding metadata.

    Args:
        df: Input DataFrame
        categorical_columns: List of column names to encode
        cardinality_threshold: Max unique values for one-hot encoding (default: 10)
        max_total_features: Maximum total features after encoding (default: 100)

    Returns:
        Tuple of (encoded_df, encoding_info)
        - encoded_df: DataFrame with encoded columns
        - encoding_info: List of dicts describing each transformation
    """
    if not categorical_columns:
        return pd.DataFrame(index=df.index), []

    encoding_info = []
    encoded_parts = []

    # Filter to existing columns and remove >50% NaN
    cat_cols = [c for c in categorical_columns if c in df.columns]
    cat_df = df[cat_cols].copy()
    threshold = len(cat_df) * 0.5
    valid_cols = [c for c in cat_df.columns if cat_df[c].count() >= threshold]
    cat_df = cat_df[valid_cols]

    # Process each column with appropriate encoding
    one_hot_candidates = []

    for col in cat_df.columns:
        series = cat_df[col]
        dtype = series.dtype
        non_null = series.dropna()
        nunique = int(non_null.nunique())

        # Skip single-value columns
        if nunique <= 1:
            continue

        # Skip ID-like columns (cardinality ratio > 0.9)
        cardinality_ratio = nunique / len(df) if len(df) > 0 else 0
        if cardinality_ratio > 0.9:
            continue

        # Boolean: cast to int
        if dtype == bool or (dtype == object and set(non_null.unique()) <= {True, False}):
            encoded = series.map({True: 1, False: 0}).fillna(0).astype(int)
            encoded_parts.append(encoded.to_frame())
            encoding_info.append({
                "original_column": col,
                "encoding_type": "boolean",
                "new_columns": [col],
                "cardinality": 2,
            })
            continue

        # Numeric-as-string: coerce to float
        if dtype == object:
            coerced = pd.to_numeric(non_null, errors="coerce")
            numeric_ratio = coerced.notna().sum() / len(non_null) if len(non_null) > 0 else 0
            if numeric_ratio > 0.8:
                encoded = pd.to_numeric(series, errors="coerce").fillna(encoded.median())
                encoded_parts.append(encoded.to_frame())
                encoding_info.append({
                    "original_column": col,
                    "encoding_type": "numeric-coerce",
                    "new_columns": [col],
                    "cardinality": nunique,
                })
                continue

        # Impute NaN with sentinel
        series = series.fillna("MISSING")

        # Choose encoding by cardinality
        if nunique <= cardinality_threshold:
            one_hot_candidates.append((col, nunique, series))
        else:
            # Label encoding
            le = LabelEncoder()
            encoded = pd.Series(le.fit_transform(series.astype(str)), index=series.index, name=col)
            encoded_parts.append(encoded.to_frame())
            encoding_info.append({
                "original_column": col,
                "encoding_type": "label",
                "new_columns": [col],
                "cardinality": nunique,
            })

    # Process one-hot candidates with feature cap enforcement
    current_features = sum(part.shape[1] for part in encoded_parts)
    one_hot_candidates.sort(key=lambda x: x[1], reverse=True)

    for col, nunique, series in one_hot_candidates:
        new_cols = nunique - 1  # drop_first=True
        if current_features + new_cols > max_total_features:
            # Downgrade to label encoding
            le = LabelEncoder()
            encoded = pd.Series(le.fit_transform(series.astype(str)), index=series.index, name=col)
            encoded_parts.append(encoded.to_frame())
            encoding_info.append({
                "original_column": col,
                "encoding_type": "label",
                "new_columns": [col],
                "cardinality": nunique,
            })
            current_features += 1
        else:
            dummies = pd.get_dummies(series.astype(str), prefix=col, drop_first=True).astype(int)
            encoded_parts.append(dummies)
            encoding_info.append({
                "original_column": col,
                "encoding_type": "one-hot",
                "new_columns": dummies.columns.tolist(),
                "cardinality": nunique,
            })
            current_features += dummies.shape[1]

    if not encoded_parts:
        return pd.DataFrame(index=df.index), encoding_info

    result = pd.concat(encoded_parts, axis=1)
    return result, encoding_info
```

### Column Classification Function: `_classify_column()`

```python
def _classify_column(series: pd.Series) -> dict:
    """Classify a column and return encoding metadata.

    Returns dict with keys: cardinality, suggested_encoding, is_id_like.
    """
    dtype = series.dtype
    n_rows = len(series)
    non_null = series.dropna()

    # Numeric columns: no encoding needed
    if pd.api.types.is_numeric_dtype(dtype):
        return {"cardinality": None, "suggested_encoding": None, "is_id_like": False}

    # Datetime columns: excluded
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return {"cardinality": None, "suggested_encoding": None, "is_id_like": False}

    # Boolean columns
    if dtype == bool or (dtype == object and set(non_null.unique()) <= {True, False}):
        return {"cardinality": 2, "suggested_encoding": "boolean", "is_id_like": False}

    # Object/category columns
    nunique = int(non_null.nunique())
    cardinality_ratio = nunique / n_rows if n_rows > 0 else 0

    # Single-value: exclude
    if nunique <= 1:
        return {"cardinality": nunique, "suggested_encoding": None, "is_id_like": False}

    # ID-like: cardinality ratio > 0.9
    if cardinality_ratio > 0.9:
        return {"cardinality": nunique, "suggested_encoding": None, "is_id_like": True}

    # Numeric-as-string: >80% values coerce to numeric
    if dtype == object:
        coerced = pd.to_numeric(non_null, errors="coerce")
        numeric_ratio = coerced.notna().sum() / len(non_null) if len(non_null) > 0 else 0
        if numeric_ratio > 0.8:
            return {"cardinality": nunique, "suggested_encoding": "numeric-coerce", "is_id_like": False}

    # Categorical: choose encoding by cardinality
    if nunique <= 10:
        return {"cardinality": nunique, "suggested_encoding": "one-hot", "is_id_like": False}
    else:
        return {"cardinality": nunique, "suggested_encoding": "label", "is_id_like": False}
```

### Updated `preprocess()` Function

```python
def preprocess(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    categorical_columns: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str], List[Dict[str, Any]]]:
    """Select numeric columns, encode categoricals, handle missing values, scale.

    Returns (original_df, scaled_df, feature_names, encoding_info).
    """
    # Numeric pipeline
    if columns:
        numeric_df = df[columns].select_dtypes(include=["number"])
    else:
        numeric_df = df.select_dtypes(include=["number"])

    # Drop columns with >50% NaN
    threshold = len(numeric_df) * 0.5
    numeric_df = numeric_df.dropna(axis=1, thresh=int(threshold))

    # Impute remaining NaNs with median
    numeric_df = numeric_df.dropna(how="all")
    for col in numeric_df.columns:
        numeric_df[col] = numeric_df[col].fillna(numeric_df[col].median())

    # Categorical pipeline
    encoding_info: List[Dict[str, Any]] = []
    if categorical_columns:
        encoded_df, encoding_info = encode_categoricals(df.loc[numeric_df.index], categorical_columns)
        if not encoded_df.empty:
            combined_df = pd.concat([numeric_df, encoded_df], axis=1)
        else:
            combined_df = numeric_df
    else:
        combined_df = numeric_df

    # Drop zero-variance columns
    variances = combined_df.var()
    zero_var_cols = variances[variances == 0].index.tolist()
    if zero_var_cols:
        combined_df = combined_df.drop(columns=zero_var_cols)

    feature_names = combined_df.columns.tolist()
    if len(feature_names) < 2:
        raise ValueError(f"Need at least 2 features for analysis, found {len(feature_names)}")

    # Scale
    scaler = StandardScaler()
    scaled_array = scaler.fit_transform(combined_df)
    scaled_df = pd.DataFrame(scaled_array, columns=feature_names, index=combined_df.index)

    return combined_df, scaled_df, feature_names, encoding_info
```

## Prevention

To prevent similar issues in the future:

### 1. Design Principles
- **No silent data loss**: Always inform users when columns are excluded
- **Intelligent defaults**: Use heuristics to classify and handle different data types
- **User control**: Provide UI controls for users to override automatic decisions
- **Transparency**: Show all transformations applied to the data

### 2. Code Patterns
- Add metadata tracking for all data transformations
- Return information about excluded data and reasons
- Include sanity checks for ID-like columns and constant values
- Implement dimension caps to prevent computational issues

### 3. Testing Strategy
- Test with mixed-type DataFrames (numeric + categorical)
- Test edge cases: all categorical, all numeric, high cardinality, constant columns
- Verify encoding metadata is accurate and complete
- Test dimension cap enforcement

### 4. Documentation
- Document encoding strategies in code comments
- Provide examples in tests showing expected behavior
- Include user-facing documentation about how categoricals are handled

## Related

- **Dataset Preview Modal** (PR #1): Shows column classifications before analysis
- **Search Validation** (PR #1): Ensures dataset metadata includes categorical column info
- **Storage Layer** (PR #1): Preserves encoding_info in saved analyses
- **Visualization** (future): Could add charts showing feature importance by encoding type

### Related Files Changed

- `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/services/analysis_engine.py`: Core encoding logic
- `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/services/dataset_loader.py`: Column classification
- `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/models/schemas.py`: Schema updates
- `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/routers/analysis.py`: Route parameter handling
- `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/app/routers/search.py`: Preview validation
- `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/tests/test_analysis.py`: Comprehensive encoding tests
- Templates: `dataset_preview_modal.html`, `analysis_form.html`, `analysis_results.html`

### Similar Issues to Watch For

- Datetime columns being silently dropped (currently excluded by design)
- Text columns that could benefit from vectorization
- Ordinal categorical variables that would benefit from custom encoding
- Multi-label categorical columns (e.g., comma-separated tags)
