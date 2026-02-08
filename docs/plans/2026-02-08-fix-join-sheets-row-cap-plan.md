---
title: "fix: Remove silent row cap from sheet join flow"
type: fix
date: 2026-02-08
ticket: "#22"
---

# fix: Remove silent row cap from sheet join flow

## Overview

`join_sheets()` silently truncates joined results at `settings.max_dataset_rows` (10,000). When the joined CSV is later loaded for preview and analysis, `load_dataframe()` applies the same cap again. The user expects to see all joined rows.

## Problem Statement

The row cap is applied **three times** in the join flow:

1. `join_sheets()` at `dataset_loader.py:286` — caps the merge result
2. `load_dataframe()` at `dataset_loader.py:310` — caps when loading `joined.csv` for preview
3. `load_dataframe()` at `analysis.py:38` — caps when loading for analysis

The cap was designed to limit downloads from external sources (Kaggle, HuggingFace, etc.), not user-controlled joins. Users who join two sheets and get 15,000 rows see only 10,000 with no warning.

**Related institutional learning:** `docs/solutions/logic-errors/categorical-columns-dropped-silently.md` — same class of bug (silent data loss without user notification).

## Proposed Solution

Two changes in one file (`dataset_loader.py`):

1. **Remove the cap from `join_sheets()`** — delete `max_rows` param and truncation logic
2. **Detect `joined.csv` by filename in `load_dataframe()`** — skip the row cap for user-controlled joined data

Joined CSVs are only created by `save_joined_csv()`, so the filename `joined.csv` is a stable contract. External dataset downloads and non-joined uploads continue to respect the `max_dataset_rows` cap.

## Acceptance Criteria

- [ ] `join_sheets()` returns all rows from the merge (no truncation)
- [ ] Dataset preview page shows full joined row count
- [ ] Analysis pipeline receives full joined DataFrame
- [ ] Non-joined datasets still respect `max_dataset_rows` cap
- [ ] Existing tests pass, new test covers uncapped join

## Implementation

### 1. Remove cap from `join_sheets()`

**File:** `app/services/dataset_loader.py`

Remove the `max_rows` parameter and the truncation logic:

```python
def join_sheets(
    file_path: Path,
    sheet_configs: list[dict],
) -> pd.DataFrame:
    """Load and sequentially join multiple Excel sheets."""
    result = pd.read_excel(file_path, sheet_name=sheet_configs[0]["name"])

    for config in sheet_configs[1:]:
        right = pd.read_excel(file_path, sheet_name=config["name"])
        result = result.merge(
            right,
            on=config["join_key"],
            how=config.get("join_type", "inner"),
            suffixes=("", f"_{config['name']}"),
        )

    return result
```

### 2. Detect `joined.csv` in `load_dataframe()`

**File:** `app/services/dataset_loader.py`

Add filename check at the top of `load_dataframe()`. Joined CSVs are user-controlled data — don't cap them:

```python
def load_dataframe(
    file_path: Path,
    max_rows: Optional[int] = None,
    sheet_name: Optional[str] = None,
) -> pd.DataFrame:
    """Load a data file into a pandas DataFrame."""
    # Joined CSVs are user-controlled — don't apply row cap
    if file_path.name == "joined.csv":
        max_rows = None
    elif max_rows is None:
        max_rows = settings.max_dataset_rows
    # ... rest unchanged
```

### 3. Test

**File:** `tests/test_upload.py`

- [ ] `test_join_does_not_cap_results` — join producing >10K rows returns all rows

## Files Modified

| File | Change |
|------|--------|
| `app/services/dataset_loader.py` | Remove `max_rows` from `join_sheets()`. Add `joined.csv` detection in `load_dataframe()`. |
| `tests/test_upload.py` | Add test for uncapped join. |

## Edge Cases

- **Large cross-joins:** Bounded by the 50MB Excel file size limit and `pd.read_excel()` memory — practically limits joins to ~100K-500K rows. Acceptable for now.
- **NULL join keys:** pandas drops NULLs by default. No change needed.
- **Non-joined datasets:** Unaffected. `load_dataframe()` still defaults to `max_dataset_rows` when filename is not `joined.csv`.

## References

- Ticket: #22
- Institutional learning: `docs/solutions/logic-errors/categorical-columns-dropped-silently.md`
- Config: `app/config.py:11` — `max_dataset_rows: int = 10000`
