---
title: "fix: Dataset loader remaining edge cases (join KeyError, empty CSV, detect_sheets memory)"
type: fix
date: 2026-03-09
tickets: "#74, #75, #73"
---

# Fix Dataset Loader Remaining Edge Cases

## Overview

Three bugs in `app/services/dataset_loader.py`, all touching non-overlapping code. Ship as a single commit.

## Problem Statement

1. **#74 — join_sheets KeyError (MED)**: `join_sheets()` passes `config["join_key"]` directly to `pd.merge(on=...)`. If the column doesn't exist in either DataFrame, pandas raises a raw `KeyError` with no context. Worse, `execute_join` in `pages.py:148` has no try/except, so this becomes a 500 error.

2. **#75 — Malformed CSV empty DataFrame (MED)**: `pd.read_csv(..., on_bad_lines="skip")` at lines 409, 411, and 442 silently drops all unparseable rows. A fully malformed file produces an empty DataFrame with no error — the user sees a blank preview with no explanation.

3. **#73 — detect_sheets memory (LOW)**: `detect_sheets()` calls `pd.read_excel(xls, sheet_name=name)` for every sheet, loading all cell data into memory just to get row counts and column names. For large workbooks this is slow and memory-wasteful.

## Proposed Solution

### Fix 1: Catch merge errors and surface them (Ticket #74)

**Two changes, ~10 lines total.**

**a)** Wrap `merge()` in try/except in `join_sheets`:

**File:** `app/services/dataset_loader.py:361-383`

```python
def join_sheets(file_path: Path, sheet_configs: list[dict]):
    import pandas as pd
    result = pd.read_excel(file_path, sheet_name=sheet_configs[0]["name"])

    for config in sheet_configs[1:]:
        right = pd.read_excel(file_path, sheet_name=config["name"])
        join_key = config.get("join_key", "")
        try:
            result = result.merge(
                right,
                on=join_key,
                how=config.get("join_type", "inner"),
                suffixes=("", f"_{config['name']}"),
            )
        except (KeyError, MergeError) as e:
            raise ValueError(
                f"Cannot join on column '{join_key}' with sheet "
                f"'{config['name']}': {e}. "
                f"Available columns in left table: "
                f"{', '.join(result.columns[:20])}. "
                f"Available columns in '{config['name']}': "
                f"{', '.join(right.columns[:20])}."
            ) from e

    return result
```

This catches both `KeyError` (missing column) and `MergeError` (incompatible types, etc.) and wraps them in a `ValueError` with context. No pre-validation needed — let pandas do the work, just translate the error.

**b)** Catch `ValueError` in `execute_join` and redirect back with error:

**File:** `app/routers/pages.py:138-171`

```python
try:
    joined_df = join_sheets(file_path, sheet_configs)
except ValueError as e:
    selected = [c["name"] for c in sheet_configs]
    return RedirectResponse(
        url=(
            f"/dataset/upload/{upload_id}/sheets"
            f"?name={quote(name)}"
            f"&error={quote(str(e))}"
        ),
        status_code=303,
    )
```

Redirect back to the sheet selection page (which already rebuilds its own context via `detect_sheets`). The error message travels as a query param. The `select_sheets_page` handler needs a one-line addition to pass `error` through to the template.

### Fix 2: Check for empty DataFrame after CSV/TSV read (Ticket #75)

**File:** `app/services/dataset_loader.py:408-444`

Single check before the return, covering all paths (TSV, CSV, and fallback):

```python
# Insert before line 444 (the logger.info line):
if df.empty:
    raise ValueError(
        "The file contains no readable data rows. "
        "It may be malformed or in an unsupported encoding."
    )
```

One check at the function exit instead of three checks at each read site. All CSV/TSV paths flow to this point.

**Note:** A CSV with a valid header but zero data rows also triggers this — intentional, since an empty dataset can't be analyzed.

### Fix 3: Use openpyxl read_only mode for detect_sheets (Ticket #73)

**File:** `app/services/dataset_loader.py:342-358`

```python
def detect_sheets(file_path: Path) -> list[dict]:
    """Detect sheets in an Excel file.

    Returns list of dicts with keys: name, num_rows, num_columns, columns.
    """
    suffix = file_path.suffix.lower()

    # openpyxl read_only mode for .xlsx — fast metadata without loading all cells
    if suffix == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheets = []
        try:
            for name in wb.sheetnames:
                ws = wb[name]
                # Read first row for column names
                columns = []
                for row in ws.iter_rows(min_row=1, max_row=1, values_only=True):
                    columns = [str(c) for c in row if c is not None and str(c).strip()]
                # max_row is approximate in read_only mode (may over-count trailing empty rows)
                num_rows = max(0, (ws.max_row or 1) - 1)
                sheets.append({
                    "name": name,
                    "num_rows": num_rows,
                    "num_columns": len(columns),
                    "columns": columns,
                })
        finally:
            wb.close()
        return sheets

    # Fallback for .xls — openpyxl doesn't support legacy format
    import pandas as pd
    xls = pd.ExcelFile(file_path)
    sheets = []
    for name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=name)
        sheets.append({
            "name": name,
            "num_rows": len(df),
            "num_columns": len(df.columns),
            "columns": df.columns.tolist(),
        })
    return sheets
```

**Key decisions:**
- `.xlsx` uses openpyxl `read_only=True` — streams lazily, never loads full cell data
- `.xls` falls back to existing pandas path — openpyxl only supports `.xlsx`
- `max_row` is approximate in read_only mode; acceptable for sheet selection display
- Filters empty-string column names (`str(c).strip()`)
- `wb.close()` in `finally` block to release file handle

## Acceptance Criteria

- [x] `join_sheets` catches `KeyError`/`MergeError` and raises `ValueError` with column context
- [x] `execute_join` catches `ValueError` and redirects back with error message
- [x] Sheet selection page displays join error when present
- [x] `load_dataframe` raises `ValueError` for fully malformed CSV/TSV (empty DataFrame)
- [x] `detect_sheets` uses openpyxl `read_only=True` for `.xlsx` files
- [x] `detect_sheets` falls back to pandas for `.xls` files
- [x] Test: join_sheets with missing join_key column raises ValueError
- [x] Test: join_sheets with three sheets where second merge fails
- [x] Test: load_dataframe on header-only CSV raises ValueError
- [x] Test: load_dataframe on header-only TSV raises ValueError
- [x] Test: detect_sheets on .xlsx returns correct metadata via openpyxl
- [x] Test: detect_sheets on empty sheet handles gracefully

## Implementation Order

1. **#74 first** — user-facing 500 errors are the worst UX
2. **#75 second** — silent data loss is misleading
3. **#73 third** — performance optimization, lowest risk

## Key Files

| File | Change |
|------|--------|
| `app/services/dataset_loader.py:374-381` | Wrap merge in try/except, catch KeyError → ValueError |
| `app/services/dataset_loader.py:444` | Add empty-check before return |
| `app/services/dataset_loader.py:342-358` | Rewrite `detect_sheets` with openpyxl fast path |
| `app/routers/pages.py:148` | Catch ValueError, redirect with error query param |
| `app/routers/pages.py:79-87` | Pass error query param through to template |
| `tests/test_dataset_loader.py` | Add tests for empty CSV, malformed TSV |
| `tests/test_upload.py` | Add tests for join_key validation, detect_sheets |

## What Changed After Review

- **Dropped**: Explicit `join_key` pre-validation (10 lines) → replaced with try/except around `merge()` (4 lines)
- **Dropped**: Re-render join config template on error (15 lines) → replaced with redirect (3 lines). Reviewers caught that the template context was wrong and would crash.
- **Dropped**: `join_type` whitelist sanitization — UI only sends valid values
- **Dropped**: Empty `join_key` guard — caught naturally by KeyError handler
- **Consolidated**: 3 separate `df.empty` checks → single check before return
- **Added**: Filter empty-string column names in openpyxl path
- **Added**: Comment about `max_row` approximation in read_only mode
- **Added**: Test for three-sheet join failure and empty sheet detection

## Out-of-Scope (Follow-up Tickets)

- Warning users when `on_bad_lines="skip"` drops a significant percentage of rows
- Caching `detect_sheets` results within a single upload flow (called up to 3 times)
- Validating that sheet names in join form actually exist in the file
- Empty JSON/parquet DataFrames (different concern than `on_bad_lines`)

## References

- Previous batch: `docs/plans/2026-03-06-fix-dataset-loader-edge-cases-plan.md`
- Related learnings: `docs/solutions/logic-errors/upload-validation-must-match-loader-capabilities.md`
- Related learnings: `docs/solutions/logic-errors/categorical-columns-dropped-silently.md`
