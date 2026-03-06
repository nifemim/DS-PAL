---
title: "fix: Dataset loader edge cases (max_rows crash, zip slip, ARFF garbage)"
type: fix
date: 2026-03-06
tickets: "#69, #70, #72"
---

# Fix Dataset Loader Edge Cases

## Overview

Three bugs in `app/services/dataset_loader.py`. All touch the same file with non-overlapping line ranges — ship as a single commit.

## Problem Statement

1. **#69 - max_rows crash**: `load_dataframe()` line 409 does `len(df) > max_rows` without guarding for `None` (TypeError). Line 405 uses truthiness which has a subtle `max_rows=0` bug. Latent — not reachable via current callers but breaks on any code change.

2. **#70 - Zip slip (CRITICAL)**: `_extract_zip()` line 308 calls `zf.extract(f, cache_dir)` without path validation. Crafted zip from generic HTTP download could write files anywhere on disk.

3. **#72 - ARFF garbage**: OpenML ARFF fallback (lines 223-238) saves ARFF as `data.csv`. ARFF headers can't be parsed by `pd.read_csv`; `on_bad_lines="skip"` silently produces garbage. Team already decided against ARFF support (`docs/plans/2026-03-01:30`).

## Proposed Solution

### Fix 1: Guard max_rows comparisons (Ticket #69)

Two-line change in `app/services/dataset_loader.py`:

```python
# Line 405 (JSON branch) - change from:
if max_rows and len(df) > max_rows:
# to:
if max_rows is not None and len(df) > max_rows:

# Line 409 (Parquet branch) - change from:
if len(df) > max_rows:
# to:
if max_rows is not None and len(df) > max_rows:
```

### Fix 2: Safe zip extraction (Ticket #70)

Replace `_extract_zip` in `app/services/dataset_loader.py`. Key changes:

- `Path(info.filename).name` flattens paths (kills zip slip)
- `zf.open()` + chunked write to disk (not `zf.read()` into memory) with runtime byte counting
- `Path.is_relative_to()` as belt-and-suspenders containment check
- Total extraction size capped
- **Behavioral change:** adds `.lower()` on filenames so `DATA.CSV` is now accepted (improvement)

```python
SUPPORTED_DATA_EXTENSIONS = (".csv", ".json", ".parquet", ".xlsx", ".tsv")
MAX_TOTAL_EXTRACT = MAX_FILE_BYTES * 3  # cap total decompressed output


def _extract_zip(content: bytes, cache_dir: Path) -> Path:
    """Extract a zip file securely and return path to the data file."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        candidates = [
            info for info in zf.infolist()
            if not info.is_dir()
            and not info.filename.startswith("__MACOSX")
            and info.filename.lower().endswith(SUPPORTED_DATA_EXTENSIONS)
        ]

        if not candidates:
            raise ValueError("No supported data files found in zip archive")

        extracted = []
        total_bytes = 0

        for info in candidates:
            safe_name = Path(info.filename).name
            if not safe_name or safe_name.startswith("."):
                continue

            dest = (cache_dir / safe_name).resolve()
            if not dest.is_relative_to(cache_dir.resolve()):
                raise ValueError(
                    f"Zip entry '{info.filename}' would extract outside target directory"
                )

            # Stream to disk with runtime byte counting
            member_bytes = 0
            try:
                with zf.open(info) as src, open(dest, "wb") as out:
                    while True:
                        chunk = src.read(65536)
                        if not chunk:
                            break
                        member_bytes += len(chunk)
                        total_bytes += len(chunk)
                        if member_bytes > MAX_FILE_BYTES:
                            raise ValueError(
                                f"File '{safe_name}' in zip exceeds "
                                f"{settings.max_file_size_mb}MB limit"
                            )
                        if total_bytes > MAX_TOTAL_EXTRACT:
                            raise ValueError(
                                "Total decompressed zip size exceeds limit"
                            )
                        out.write(chunk)
            except ValueError:
                # Clean up partial file on size limit errors
                dest.unlink(missing_ok=True)
                # Clean up any previously extracted files
                for f in extracted:
                    f.unlink(missing_ok=True)
                raise

            extracted.append(dest)

        if not extracted:
            raise ValueError("No valid data files could be extracted")

        return max(extracted, key=lambda p: p.stat().st_size)
```

**What was dropped from the deepened plan after review:**
- Compression ratio heuristic — uses untrusted `ZipInfo.file_size`, redundant given runtime byte counting
- Null byte filename check — Python's `zipfile` already rejects these
- `chunks = []` / `b"".join(chunks)` pattern — defeated streaming purpose; now writes directly to disk

**What was added after review:**
- Partial extraction cleanup on error (try/except removes already-written files)
- `SUPPORTED_DATA_EXTENSIONS` module constant (reduces duplication with other functions)
- `MAX_TOTAL_EXTRACT` named constant (was magic `* 3`)

**Not addressed (out of scope):**
- Kaggle's `api.dataset_download_files(unzip=True)` does its own zip extraction — separate code path
- Filename collisions after flattening (`dir1/data.csv` and `dir2/data.csv`) — second overwrites first; acceptable since we return largest file

### Fix 3: Remove ARFF fallback (Ticket #72)

Delete lines 223-238 in `_download_openml()`. Update the error message:

```python
raise ValueError(
    f"Could not download OpenML dataset '{dataset_id}'. "
    "Only parquet-format datasets are supported. "
    "This dataset may only be available in ARFF format."
)
```

Cached ARFF-as-CSV garbage in `.cache/datasets/openml_*` persists until manually cleared. Not worth automating.

## Acceptance Criteria

- [x] `load_dataframe()` JSON and parquet branches guard `max_rows` with `is not None`
- [x] Test: parquet with `max_rows=None` does not crash
- [x] Test: JSON with `max_rows=None` does not crash
- [x] Test: `max_rows=0` returns empty DataFrame
- [x] `_extract_zip` uses `zf.open()` + chunked disk write instead of `zf.extract()`
- [x] Test: zip with `../evil.csv` extracts safely as `evil.csv` (flattened)
- [x] Test: zip with oversized entry (runtime bytes exceed limit) raises `ValueError`
- [x] Test: valid zip extracts correctly and returns largest file
- [x] ARFF fallback block removed from `_download_openml()`
- [x] Test: OpenML with failed parquet URL raises `ValueError` even when valid ARFF URL exists in metadata

## Implementation Order

1. **#70 first** — critical security fix
2. **#69 second** — 2-line change
3. **#72 third** — code removal

## Key Files

| File | Change |
|------|--------|
| `app/services/dataset_loader.py:292-312` | Rewrite `_extract_zip` with safe streaming extraction |
| `app/services/dataset_loader.py:405` | Add `is not None` guard to JSON max_rows check |
| `app/services/dataset_loader.py:409` | Add `is not None` guard to parquet max_rows check |
| `app/services/dataset_loader.py:223-238` | Remove ARFF fallback block |
| `app/services/dataset_loader.py:240` | Update error message to mention ARFF |
| `tests/test_dataset_loader.py` | Add tests for `load_dataframe` and `_extract_zip` |

## Out-of-Scope Findings (Future Tickets)

- **SSRF** — `download_dataset()` line 93 fetches any user-controlled URL with `follow_redirects=True`
- **Cache validation** — line 73 reads entire file (up to 50MB) just to check first 500 bytes
- **Kaggle creds** — lines 134-135 set `os.environ` per-request (process-global, not thread-safe)

## References

- ARFF deferral: `docs/plans/2026-03-01-feat-expand-search-providers-plan.md:30`
- Zip handling learning: `docs/solutions/integration-issues/zenodo-dataset-download-requires-rest-api.md`
- `Path.is_relative_to()`: Python 3.9+ (project uses 3.9)
