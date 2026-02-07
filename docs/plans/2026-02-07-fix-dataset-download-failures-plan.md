---
title: "Fix dataset download failures for UCI, HuggingFace, and data.gov providers"
type: fix
date: 2026-02-07
ticket: "#13"
priority: high
---

# Fix Dataset Download Failures for UCI, HuggingFace, and data.gov Providers

## Overview

Datasets from UCI, HuggingFace, and some data.gov results fail to load because the download pipeline receives HTML pages or unsupported formats instead of data files. Each provider needs source-specific download handling (like Kaggle already has), plus content validation to catch bad downloads early.

## Problem Statement

Currently `download_dataset()` in `app/services/dataset_loader.py:33` has special handling only for Kaggle. All other sources fall through to a generic HTTP GET that assumes `url` is a direct file download. This fails for:

1. **UCI**: `url` is `https://archive.ics.uci.edu/dataset/{id}` (HTML page). The `download_url()` method returns `/static/public/{id}` which 404s (needs `/{name}.zip` suffix). Additionally, the UCI JSON API at `/api/datasets` now returns HTML instead of JSON — the provider's search is likely broken entirely.
2. **HuggingFace**: `url` is `https://huggingface.co/datasets/{id}` (HTML page). HF datasets are available as parquet via `https://datasets-server.huggingface.co/parquet?dataset={id}`.
3. **data.gov**: `url` is sometimes an API endpoint, landing page, or XML feed rather than a direct CSV/JSON file. No content validation catches this.

## Proposed Solution

### 1. Add source-specific download handlers in `dataset_loader.py`

Add `_download_uci()` and `_download_huggingface()` alongside existing `_download_kaggle()`, and route to them from `download_dataset()`.

### 2. Add content validation for all downloads

After any HTTP download, sniff the first bytes to detect HTML/XML responses masquerading as data files. Reject with a clear error message.

### 3. Fix UCI provider search (API broken)

The UCI API at `https://archive.ics.uci.edu/api/datasets` now returns HTML. Either find the updated endpoint or disable the provider gracefully.

## Acceptance Criteria

- [x] HuggingFace datasets download via the parquet API (`datasets-server.huggingface.co/parquet`)
- [x] UCI datasets download via `/static/public/{id}/{name}.zip` pattern (if search is fixable) or provider disabled gracefully
- [x] data.gov downloads validated — HTML/XML responses rejected with clear error
- [x] Content validation catches non-data responses (HTML, XML) for all providers
- [x] Existing Kaggle and valid data.gov downloads still work
- [x] Tests cover all provider-specific download paths and content validation
- [x] Error messages tell the user *why* a dataset couldn't be loaded

## Technical Approach

### File 1: `app/services/dataset_loader.py`

**Add source routing in `download_dataset()` (line 33):**
```python
async def download_dataset(source: str, dataset_id: str, url: str) -> Path:
    # ... cache check (unchanged) ...

    if source == "kaggle":
        return await _download_kaggle(dataset_id, cache_dir)
    elif source == "huggingface":
        return await _download_huggingface(dataset_id, cache_dir)
    elif source == "uci":
        return await _download_uci(dataset_id, cache_dir)

    # Generic HTTP download (data.gov and others)
    # ... existing logic + content validation ...
```

**New function `_download_huggingface()`:**
```python
async def _download_huggingface(dataset_id: str, cache_dir: Path) -> Path:
    """Download from HuggingFace via the datasets-server parquet API."""
    api_url = f"https://datasets-server.huggingface.co/parquet?dataset={dataset_id}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(api_url)
        resp.raise_for_status()
        data = resp.json()

    parquet_files = data.get("parquet_files", [])
    if not parquet_files:
        raise ValueError(f"No parquet files available for HuggingFace dataset '{dataset_id}'")

    # Prefer "train" split, fall back to first available
    target = next((f for f in parquet_files if f["split"] == "train"), parquet_files[0])
    file_url = target["url"]

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(file_url)
        resp.raise_for_status()

    file_path = cache_dir / "data.parquet"
    file_path.write_bytes(resp.content)
    return file_path
```

**New function `_download_uci()`:**
```python
async def _download_uci(dataset_id: str, cache_dir: Path) -> Path:
    """Download from UCI ML Repository via static zip URL."""
    # UCI zips live at /static/public/{id}/{slug}.zip
    # Try to fetch the zip — the slug is typically the lowercase dataset name
    # First try without slug (directory listing), then with common patterns
    base_url = f"https://archive.ics.uci.edu/static/public/{dataset_id}"

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Try .zip extension directly on the ID path
        for suffix in [".zip", ""]:
            try:
                resp = await client.get(f"{base_url}{suffix}")
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")
                    if "zip" in content_type or "octet-stream" in content_type:
                        return _extract_zip(resp.content, cache_dir)
            except Exception:
                continue

    raise ValueError(
        f"Could not download UCI dataset '{dataset_id}'. "
        "The UCI repository may not have a direct download available for this dataset."
    )
```

**New function `_validate_content()`:**
```python
def _validate_content(content: bytes, url: str) -> None:
    """Check that downloaded content is actual data, not HTML/XML error pages."""
    # Check first 500 bytes for HTML/XML signatures
    head = content[:500].strip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        raise ValueError(
            f"The URL returned an HTML page instead of a data file. "
            f"This dataset may not have a direct download link."
        )
    if head.startswith(b"<?xml"):
        raise ValueError(
            f"The URL returned XML data which is not supported. "
            f"This dataset may require a different format."
        )
```

Call `_validate_content()` in the generic HTTP download path before saving the file.

### File 2: `app/services/providers/uci_provider.py`

The UCI API at `/api/datasets` now returns HTML. Options:
- **Option A**: Fix the API endpoint if a new one exists
- **Option B**: Disable UCI search with a log warning (keep the provider shell for future re-enablement)

Given that the API appears broken, use **Option B**: return empty results with a warning. Store the dataset name in search results for download URL construction.

### File 3: `app/services/providers/huggingface_provider.py`

No changes needed to search — it works. The download fix is entirely in `dataset_loader.py`.

### File 4: `tests/test_dataset_loader.py` (new)

Test cases:
- `test_validate_content_html` — HTML content raises ValueError
- `test_validate_content_xml` — XML content raises ValueError
- `test_validate_content_csv` — valid CSV passes
- `test_validate_content_parquet` — valid parquet bytes pass
- `test_download_routes_to_kaggle` — source="kaggle" calls _download_kaggle
- `test_download_routes_to_huggingface` — source="huggingface" calls _download_huggingface
- `test_download_routes_to_uci` — source="uci" calls _download_uci

## Files to Modify

| File | Changes |
|------|---------|
| `app/services/dataset_loader.py` | Add `_download_huggingface()`, `_download_uci()`, `_validate_content()`; update `download_dataset()` routing |
| `app/services/providers/uci_provider.py` | Disable search gracefully (API returns HTML) |
| `tests/test_dataset_loader.py` | New test file for content validation and download routing |

## References

- HuggingFace parquet API: `https://datasets-server.huggingface.co/parquet?dataset={id}`
- UCI download pattern: `https://archive.ics.uci.edu/static/public/{id}/{name}.zip`
- Current download logic: `app/services/dataset_loader.py:33-79`
- Kaggle handler (reference pattern): `app/services/dataset_loader.py:82-103`
