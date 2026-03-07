---
title: "fix: Upload rejects TSV files and only validates first Excel sheet"
type: fix
date: 2026-03-06
tickets: "#76, #78"
---

# Fix Upload TSV Rejection and Excel Sheet Validation

## Overview

Two bugs in `app/routers/upload.py` where the upload validation is too strict (#76) and too lenient (#78).

## Problem Statement

1. **#76 — TSV rejected**: `ALLOWED_EXTENSIONS` (line 22) doesn't include `.tsv`, but `dataset_loader.py` fully supports TSV via `pd.read_csv(sep="\t")`. Users uploading `.tsv` files get "Unsupported format" error.

2. **#78 — First sheet only**: `load_dataframe(file_path)` at line 58 validates without a sheet name, so it only loads sheet 0. If the first sheet is empty but others have data, validation "passes" but the user sees an empty preview. The multi-sheet redirect at line 62-68 happens after this check, so the damage is done.

## Proposed Solution

### Fix 1: Add .tsv to ALLOWED_EXTENSIONS (Ticket #76)

**File:** `app/routers/upload.py`

```python
# Line 22 - change from:
ALLOWED_EXTENSIONS = {".csv", ".json", ".parquet", ".xlsx", ".xls"}
# to:
ALLOWED_EXTENSIONS = {".csv", ".tsv", ".json", ".parquet", ".xlsx", ".xls"}
```

Also update the error message at line 34 to include TSV:
```python
"Unsupported format. Please upload CSV, TSV, Excel, JSON, or Parquet."
```

### Fix 2: Skip load_dataframe for multi-sheet Excel (Ticket #78)

**File:** `app/routers/upload.py`

Move the multi-sheet check (step 6) before the `load_dataframe` call (step 5). For multi-sheet Excel files, skip the early validation entirely — the sheet selection page handles its own preview.

```python
# Reorder steps 5 and 6:

# 5. Check for multi-sheet Excel files (before validation)
display_name = Path(original_name).stem
if ext in (".xlsx", ".xls"):
    sheets = detect_sheets(file_path)
    if len(sheets) > 1:
        return RedirectResponse(
            url=f"/dataset/upload/{upload_id}/sheets?name={quote(display_name)}",
            status_code=303,
        )

# 6. Verify file is loadable (single-sheet only)
load_dataframe(file_path)
```

This way, multi-sheet Excel files skip straight to the sheet selection page. Single-sheet files still get validated.

## Acceptance Criteria

- [x] `.tsv` files upload successfully
- [x] Error message mentions TSV format
- [x] Multi-sheet Excel files redirect to sheet selection without first validating sheet 0
- [x] Single-sheet Excel files still get validated via `load_dataframe`
- [ ] Test: upload `.tsv` file succeeds
- [ ] Test: multi-sheet Excel skips to sheet selection

## Key Files

| File | Change |
|------|--------|
| `app/routers/upload.py:22` | Add `.tsv` to `ALLOWED_EXTENSIONS` |
| `app/routers/upload.py:34` | Update error message to mention TSV |
| `app/routers/upload.py:57-68` | Reorder multi-sheet check before `load_dataframe` |
