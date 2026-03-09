---
title: "Upload validation must match loader capabilities and respect file type"
category: logic-errors
tags:
  - upload
  - validation
  - file-formats
  - pipeline-ordering
module: app.routers.upload
symptom: |
  TSV files rejected with "Unsupported format" despite full loader support.
  Multi-sheet Excel files validated against only the first sheet, producing
  misleading empty previews when sheet 0 is empty but others have data.
root_cause: |
  Two mismatches between the upload router and the dataset loader:
  (1) ALLOWED_EXTENSIONS didn't include .tsv even though load_dataframe handles it.
  (2) load_dataframe was called before the multi-sheet check, so it validated
  sheet 0 unconditionally — even when the user would be redirected to choose sheets.
date_solved: 2026-03-06
tickets: "#76, #78"
---

# Upload Validation Must Match Loader Capabilities

## Problem

Two related bugs in `upload.py`:

1. `.tsv` was missing from `ALLOWED_EXTENSIONS` even though `dataset_loader.py` fully supports TSV via `pd.read_csv(sep="\t")`.
2. `load_dataframe(file_path)` ran before the multi-sheet Excel redirect, validating only sheet 0. Multi-sheet files where sheet 0 is empty passed validation misleadingly.

## Root Cause

The upload pipeline had validation steps that didn't account for the loader's actual capabilities or the file's structure. The extension allowlist drifted out of sync when TSV support was added to the loader. The validation ordering assumed all files should be fully validated before any redirect decisions.

## Solution

### 1. Keep extension lists in sync

```python
# upload.py
ALLOWED_EXTENSIONS = {".csv", ".tsv", ".json", ".parquet", ".xlsx", ".xls"}
```

### 2. Check file type before generic validation

```python
# Move multi-sheet check BEFORE load_dataframe:

# 5. Check for multi-sheet Excel (before generic validation)
if ext in (".xlsx", ".xls"):
    sheets = detect_sheets(file_path)
    if len(sheets) > 1:
        return RedirectResponse(url=f"/dataset/upload/{id}/sheets?name=...")

# 6. Verify file is loadable (single-sheet/flat files only)
load_dataframe(file_path)
```

Multi-sheet files skip straight to sheet selection. Single-sheet files still get validated.

## Key Principle

**Validate after you know what you're dealing with.** Generic validation (like `load_dataframe` with default args) can give misleading results when the file needs special handling (like sheet selection). Move type-specific branching before generic validation.

## Prevention

When adding a new file format to the loader:
1. Add extension to `ALLOWED_EXTENSIONS` in `upload.py`
2. Add extension to `SUPPORTED_DATA_EXTENSIONS` in `dataset_loader.py`
3. Update the user-facing error message
4. Verify the upload → load → preview pipeline end-to-end

This is the same "match extensions everywhere" pattern from the Zenodo learning.

## Related

- `docs/solutions/integration-issues/zenodo-dataset-download-requires-rest-api.md` — "new formats must be registered in ALL pipeline stages"
