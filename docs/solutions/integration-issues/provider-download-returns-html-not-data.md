---
title: "Dataset providers return HTML pages instead of data files"
category: integration-issues
module: dataset-loader
tags: [providers, download, huggingface, uci, data-gov, content-validation]
symptoms:
  - "Dataset preview fails with parse error"
  - "Downloaded file contains HTML instead of CSV"
  - "HuggingFace/UCI datasets crash on load"
  - "XML data not supported error"
date_solved: 2026-02-07
ticket: "#13"
pr: "#3"
---

# Dataset providers return HTML pages instead of data files

## Problem

Datasets from HuggingFace, UCI, and some data.gov results failed to load because the download pipeline received HTML pages or unsupported formats instead of actual data files. Users would encounter:

- Parse errors when attempting to preview datasets
- Downloaded files containing HTML markup instead of CSV/tabular data
- Application crashes when trying to load HuggingFace or UCI datasets
- "XML data not supported" errors for certain data.gov resources

The core issue was that provider URLs pointed to landing pages rather than direct download links, and there was no content validation to catch this before attempting to parse the data.

## Root Cause

The system lacked provider-specific download handlers and content validation. Only Kaggle had custom download logic. Other providers were treated generically, leading to downloads of HTML landing pages.

| Provider | Issue | URL Pattern Problem |
|----------|-------|---------------------|
| **HuggingFace** | URLs pointed to dataset pages, not data files | `huggingface.co/datasets/{id}` returned HTML viewer page |
| **UCI** | URLs pointed to dataset landing pages; JSON API also returned HTML | `archive.ics.uci.edu/dataset/{id}` was not a download endpoint |
| **data.gov** | CKAN resource URLs sometimes pointed to landing pages or XML feeds | Resource URLs were inconsistent - some were HTML pages, others XML metadata |
| **Generic Path** | No content validation existed | HTML/XML was silently saved as `.csv` and later failed during parsing |

The fundamental problem: **the download pipeline assumed all URLs were direct data file links**, with no source-specific handling or content validation.

## Solution

The fix introduced three key improvements:

### 1. Provider-Specific Download Handlers

Added dedicated handlers for HuggingFace and UCI (matching the existing Kaggle pattern):

**HuggingFace Handler** - Uses datasets-server API to get actual parquet files:

```python
def _download_huggingface(self, dataset_id: str, save_path: Path) -> Path:
    """Download HuggingFace dataset using datasets-server API."""
    # Query the parquet API for actual file URLs
    api_url = f"https://datasets-server.huggingface.co/parquet?dataset={dataset_id}"
    response = requests.get(api_url)
    response.raise_for_status()

    parquet_info = response.json()

    # Prefer train split, fall back to first available
    splits = parquet_info.get("parquet_files", {})
    split_name = "train" if "train" in splits else next(iter(splits))
    parquet_url = splits[split_name][0]["url"]

    # Download and convert parquet to CSV
    parquet_response = requests.get(parquet_url)
    parquet_response.raise_for_status()

    df = pd.read_parquet(io.BytesIO(parquet_response.content))
    df.to_csv(save_path, index=False)

    return save_path
```

**UCI Handler** - Uses static public ZIP endpoint:

```python
def _download_uci(self, dataset_id: str, save_path: Path) -> Path:
    """Download UCI dataset from static public endpoint."""
    # Extract numeric ID from URL patterns
    id_match = re.search(r'/dataset/(\d+)', dataset_id)
    numeric_id = id_match.group(1) if id_match else dataset_id

    zip_url = f"https://archive.ics.uci.edu/static/public/{numeric_id}/{numeric_id}.zip"

    response = requests.get(zip_url)
    response.raise_for_status()

    # Extract first CSV from ZIP
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        csv_files = [f for f in zip_file.namelist() if f.endswith('.csv')]
        if not csv_files:
            raise ValueError("No CSV file found in UCI dataset ZIP")

        with zip_file.open(csv_files[0]) as csv_file:
            save_path.write_bytes(csv_file.read())

    return save_path
```

### 2. Content Validation

Added `_validate_content()` to detect and reject HTML/XML before saving:

```python
def _validate_content(self, content: bytes) -> None:
    """Validate that content is not HTML/XML."""
    # Check first 1KB for HTML/XML signatures
    prefix = content[:1024].lower()

    if b'<!doctype html' in prefix or b'<html' in prefix:
        raise ValueError("Downloaded content is HTML, not a data file")

    if prefix.startswith(b'<?xml') or b'<xml' in prefix:
        raise ValueError("Downloaded content is XML, not a supported data format")
```

### 3. Routing Logic

Updated `download()` to route requests to appropriate handlers:

```python
def download(self, url: str, dataset_name: str) -> Path:
    """Download dataset from URL with provider-specific handling."""
    save_path = self.cache_dir / f"{dataset_name}.csv"

    # Route to provider-specific handlers
    if "huggingface.co" in url:
        return self._download_huggingface(url, save_path)
    elif "archive.ics.uci.edu" in url:
        return self._download_uci(url, save_path)
    elif "kaggle.com" in url:
        return self._download_kaggle(url, save_path)
    else:
        # Generic download with content validation
        response = requests.get(url)
        response.raise_for_status()

        self._validate_content(response.content)

        save_path.write_bytes(response.content)
        return save_path
```

### 4. Additional Changes

- **UCI Provider**: Disabled search functionality since the JSON API now returns HTML instead of valid data
- **Tests**: Added `test_dataset_loader.py` with unit tests for all download handlers and content validation

## Prevention

To prevent similar issues in the future:

1. **Always validate content type** - Check file signatures/magic bytes before assuming format
2. **Provider-specific handlers** - Don't assume all data sources work the same way
3. **API over scraping** - Prefer official APIs (like HuggingFace datasets-server) over parsing HTML
4. **Error messages matter** - Clear errors like "Downloaded content is HTML" help users understand what went wrong
5. **Test with real providers** - Integration tests should verify actual downloads work, not just mock responses

**Pattern to follow when adding new providers:**

```python
# 1. Check if provider needs special handling
if "newprovider.com" in url:
    return self._download_newprovider(url, save_path)

# 2. In handler: validate before parsing
response = requests.get(api_url)
response.raise_for_status()
self._validate_content(response.content)  # Always validate

# 3. Handle provider-specific formats
data = self._parse_provider_format(response.content)
```

## Related

- **Files Changed**:
  - `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/src/dspal/dataset_loader.py` - Added handlers and validation
  - `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/src/dspal/providers/uci_provider.py` - Disabled broken search
  - `/Users/nifemimadarikan/Documents/ClaudeCode/DS-PAL/tests/test_dataset_loader.py` - New test coverage

- **See Also**:
  - Provider integration patterns
  - Content-type validation strategies
  - HuggingFace datasets-server API documentation
  - UCI ML Repository static public endpoint structure
