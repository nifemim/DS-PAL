---
title: "fix: Zenodo dataset download returns HTML instead of data file"
type: fix
date: 2026-03-02
ticket: 62
---

# fix: Zenodo dataset download returns HTML instead of data file

## Overview

Clicking a Zenodo search result fails with "The URL returned an HTML page instead of a data file." This happens because `zenodo_provider.py` returns record landing page URLs (`https://zenodo.org/records/{id}`) instead of direct file download links. The `_validate_content()` check correctly catches the HTML but the user gets a confusing error.

## Proposed Solution

Follow the established pattern from `docs/solutions/integration-issues/provider-download-returns-html-not-data.md`: add a Zenodo-specific download handler in `dataset_loader.py` that uses the Zenodo REST API to resolve the direct file download link.

The Zenodo API at `https://zenodo.org/api/records/{id}` returns a JSON response with a `files` array containing direct download links (`links.self`). The handler picks the first data file (CSV, JSON, XLSX, Parquet, TSV) and downloads it.

## Implementation

### `app/services/dataset_loader.py`

Add a `_download_zenodo()` handler and route to it from `download_dataset()`:

```python
# In download_dataset(), add before the generic HTTP download:
elif source == "zenodo":
    return await _download_zenodo(dataset_id, cache_dir)

# New handler:
async def _download_zenodo(dataset_id: str, cache_dir: Path) -> Path:
    """Download from Zenodo using their REST API to get direct file links."""
    api_url = f"https://zenodo.org/api/records/{dataset_id}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(api_url)
        if resp.status_code == 404:
            raise ValueError(f"Zenodo record {dataset_id} not found.")
        resp.raise_for_status()
        record = resp.json()

    # Find the first data file
    DATA_EXTS = {".csv", ".json", ".xlsx", ".parquet", ".tsv", ".zip"}
    files = record.get("files", [])
    data_file = None
    for f in files:
        key = f.get("key", "")
        if any(key.lower().endswith(ext) for ext in DATA_EXTS):
            data_file = f
            break

    if not data_file:
        raise ValueError(
            "This Zenodo record has no downloadable data files (CSV, JSON, Excel, or Parquet)."
        )

    file_url = data_file["links"]["self"]
    filename = data_file["key"]

    # Use longer timeout for file download (API call is fast, file download is slow)
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(file_url)
        resp.raise_for_status()

    # Enforce file size limit before writing to disk
    if len(resp.content) > MAX_FILE_BYTES:
        raise ValueError(
            f"File too large ({len(resp.content)} bytes). Maximum allowed: {MAX_FILE_BYTES} bytes."
        )

    _validate_content(resp.content, file_url)

    if filename.endswith(".zip"):
        return _extract_zip(resp.content, cache_dir)

    file_path = cache_dir / filename
    file_path.write_bytes(resp.content)
    logger.info("Downloaded Zenodo file %s to %s (%d bytes)", filename, file_path, len(resp.content))
    return file_path
```

**Note:** Do NOT modify `zenodo_provider.py`'s `download_url()` — it returns the landing page URL for UI display purposes, which is the correct behavior.

## Acceptance Criteria

- [x] Clicking a Zenodo search result downloads the actual data file
- [x] Handler picks first CSV/JSON/XLSX/Parquet/TSV/ZIP file from the record
- [x] Records with no supported data files show a clear error message
- [x] Content validation still runs on the downloaded file
- [x] ZIP files are extracted correctly
- [x] File size limit is enforced
- [x] Existing tests pass

## Edge Cases

- **Record has only unsupported files** (e.g., PDFs, images) — show clear error instead of HTML error
- **Record has multiple data files** — pick the first one (good enough for MVP)
- **Zenodo API is down** — existing exception handling in the generic path covers this
- **Large files** — enforce `MAX_FILE_BYTES` before writing

## References

- Zenodo provider: `app/services/providers/zenodo_provider.py:91-92`
- Download routing: `app/services/dataset_loader.py:83-89`
- Content validation: `app/services/dataset_loader.py:47-59`
- Documented pattern: `docs/solutions/integration-issues/provider-download-returns-html-not-data.md`
- Zenodo API docs: `https://developers.zenodo.org/`
