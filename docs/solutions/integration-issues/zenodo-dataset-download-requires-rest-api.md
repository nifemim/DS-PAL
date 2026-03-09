---
title: "Zenodo dataset download requires REST API for direct file links"
category: integration-issues
module: dataset-loader
tags: [providers, download, zenodo, rest-api, content-validation, zip-extraction]
symptoms:
  - "The URL returned an HTML page instead of a data file"
  - "No supported data files found in zip archive"
  - "'utf-8' codec can't decode byte — invalid start byte"
date_solved: 2026-03-02
ticket: "#62"
---

# Zenodo dataset download requires REST API for direct file links

## Problem

Clicking a Zenodo search result failed with "The URL returned an HTML page instead of a data file." After fixing the initial HTML issue, two more errors surfaced:

1. "No supported data files found in zip archive" — zip contained shapefiles, not tabular data
2. "'utf-8' codec can't decode byte" — binary files (.dbf) picked up by a too-broad fallback

## Root Cause

Three layered issues:

| Layer | Issue |
|-------|-------|
| **Download URL** | `zenodo_provider.py` returned landing page URLs (`https://zenodo.org/records/{id}`), not direct file links. The generic HTTP download path fetched the HTML page. |
| **File selection** | The handler picked `.zip` files as a fallback when no flat data files existed. Many Zenodo zips contain non-tabular data (shapefiles, R scripts, etc.). |
| **Search filtering** | Zenodo search results included records with no tabular data files at all — users could click on records that would always fail. |

## Solution

### 1. Provider-specific download handler

Added `_download_zenodo()` that uses the Zenodo REST API (`/api/records/{id}`) to resolve direct file download links:

```python
# app/services/dataset_loader.py
async def _download_zenodo(dataset_id: str, cache_dir: Path) -> Path:
    api_url = f"https://zenodo.org/api/records/{dataset_id}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(api_url)
        if resp.status_code == 404:
            raise ValueError(f"Zenodo record {dataset_id} not found.")
        resp.raise_for_status()
        record = resp.json()

    # Find the first tabular data file — no zip fallback
    DATA_EXTS = {".csv", ".json", ".xlsx", ".parquet", ".tsv"}
    files = record.get("files", [])
    data_file = None
    for f in files:
        key = f.get("key", "").lower()
        if any(key.endswith(ext) for ext in DATA_EXTS):
            data_file = f
            break

    file_url = data_file["links"]["self"]
    # Download with longer timeout (60s for file, 30s for API)
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(file_url)
        resp.raise_for_status()
```

### 2. Filter search results at the provider level

Records without tabular data files are excluded from search results entirely:

```python
# app/services/providers/zenodo_provider.py
data_exts = exts & {"CSV", "JSON", "PARQUET", "XLSX", "TSV"}
if not data_exts:
    continue  # no tabular data files — skip this record
```

This prevents users from ever clicking on a record that will fail. Zip-only records are excluded because their contents are unpredictable (could be shapefiles, PDFs, R scripts, etc.).

### 3. TSV support added throughout

`.tsv` was missing from several places in the pipeline:

- Cache file lookup (`download_dataset()`)
- Zip extraction (`_extract_zip()`)
- DataFrame loading (`load_dataframe()` — explicit `sep="\t"`)

## Key Lesson: Don't download zips blindly

The biggest gotcha was **zip files as a fallback**. Research data zips are unpredictable — they might contain shapefiles, images, scripts, or any binary format. The fix that worked: only offer records with known flat data files, never fall back to zip for Zenodo.

A broad fallback in `_extract_zip` ("pick any file if no known extensions") made things worse by selecting binary `.dbf` files that crashed the CSV parser.

## Prevention

1. **Filter at the source** — Don't show users results they can't use. Check file extensions in search results before presenting them.
2. **Prefer flat files over zip** — When a provider has both, always pick CSV/JSON/XLSX/Parquet/TSV first.
3. **No broad fallbacks for zip extraction** — Only extract files with known tabular extensions. Binary files will crash the parser.
4. **Match extensions everywhere** — When adding a new format (like `.tsv`), update ALL places: cache lookup, zip extraction, file loading, and search result filtering.

## Related

- Prior art: `docs/solutions/integration-issues/provider-download-returns-html-not-data.md` — same pattern for HuggingFace/UCI
- Files changed:
  - `app/services/dataset_loader.py` — new `_download_zenodo()` handler, TSV support
  - `app/services/providers/zenodo_provider.py` — filter out non-tabular records
  - `tests/test_dataset_loader.py` — 6 new tests for Zenodo handler
- Zenodo REST API: `https://zenodo.org/api/records/{id}` returns JSON with `files[].links.self` for direct download
