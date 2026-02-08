---
title: "feat: Upload dataset for analysis"
type: feat
date: 2026-02-08
ticket: 20
brainstorm: docs/brainstorms/2026-02-08-upload-dataset-brainstorm.md
---

# feat: Upload dataset for analysis

Add a file upload capability to the home page so users can upload their own CSV, Excel, JSON, or Parquet files for analysis. Uploaded files enter the same preview + analysis pipeline as search results.

## 1. Add `save_upload()` and upload guard to `dataset_loader.py`

**Current:** `download_dataset()` routes by source (kaggle, huggingface, uci, datagov) or falls through to generic HTTP download. `source="upload"` would hit the generic path with an empty URL and fail.

**Change:** Add a public `save_upload()` function for the router to call, and a one-line guard in `download_dataset()` after the existing cache check. The existing cache-check logic (lines 54-61) already finds uploaded files — we just need to prevent the fallthrough to HTTP download if the cache is empty.

### Files

- `app/services/dataset_loader.py` — Add `save_upload()` and upload guard

```python
# app/services/dataset_loader.py — new public function

def save_upload(content: bytes, ext: str) -> tuple[str, Path]:
    """Save an uploaded file to the cache directory.

    Returns (upload_id, file_path).
    """
    upload_id = str(uuid.uuid4())
    cache_dir = _cache_path("upload", upload_id)
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_path = cache_dir / f"data{ext}"
    file_path.write_bytes(content)
    return upload_id, file_path
```

```python
# app/services/dataset_loader.py — inside download_dataset(), AFTER the existing cache
# check (line ~62), BEFORE the provider routing (line ~66):

if source == "upload":
    raise ValueError("Uploaded file not found. Please re-upload your dataset.")
```

The existing cache check at lines 54-61 already finds the file in `.cache/datasets/upload_{uuid}/data.csv` and returns it. The one-line guard just prevents fallthrough to the HTTP download path when the cache is empty.

## 2. Make `_validate_content` url param optional

**Current:** `_validate_content(content: bytes, url: str)` requires a URL for error messages. The messages reference "URL" which makes no sense for uploads.

**Change:** Make `url` optional and adjust error messages to be source-agnostic.

### Files

- `app/services/dataset_loader.py:_validate_content()` — Make `url` param optional with default `""`

```python
def _validate_content(content: bytes, url: str = "") -> None:
    """Validate that content is actual data, not an HTML/XML error page."""
    # Adjust error messages: use url context if provided, generic otherwise
```

## 3. Upload API endpoint

**New file:** `app/routers/upload.py` — a dedicated router for the upload endpoint, since it has a fundamentally different response pattern (redirect) than the HTMX partial endpoints in `search.py`.

### Files

- `app/routers/upload.py` — New file

```python
"""Upload API route."""
import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import RedirectResponse

from app.config import settings
from app.main import templates
from app.services.dataset_loader import (
    MAX_FILE_BYTES,
    _validate_content,
    load_dataframe,
    save_upload,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

ALLOWED_EXTENSIONS = {".csv", ".json", ".parquet", ".xlsx", ".xls"}


@router.post("/dataset/upload")
async def upload_dataset(request: Request, file: UploadFile):
    """Upload a dataset file. Saves to cache, redirects to dataset page."""
    try:
        # 1. Validate extension
        original_name = file.filename or "dataset"
        ext = Path(original_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                "Unsupported format. Please upload CSV, Excel, JSON, or Parquet."
            )

        # 2. Read file content, reject empty and oversized files
        content = await file.read()
        if len(content) == 0:
            raise ValueError("The uploaded file is empty.")
        if len(content) > MAX_FILE_BYTES:
            raise ValueError(
                f"File exceeds {settings.max_file_size_mb} MB limit."
            )

        # 3. Validate content is not HTML/XML (re-raise with upload-friendly message)
        try:
            _validate_content(content)
        except ValueError:
            raise ValueError(
                "The uploaded file appears to be an HTML or XML page, not a dataset."
            )

        # 4. Save to cache
        upload_id, file_path = save_upload(content, ext)

        # 5. Verify file is loadable
        load_dataframe(file_path)

        # 6. Redirect to dataset page
        display_name = Path(original_name).stem
        return RedirectResponse(
            url=f"/dataset/upload/{upload_id}?name={quote(display_name)}",
            status_code=303,
        )

    except ValueError as e:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "max_file_size_mb": settings.max_file_size_mb,
                "upload_error": str(e),
            },
        )
    except Exception as e:
        logger.error("Upload failed: %s", e, exc_info=True)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "max_file_size_mb": settings.max_file_size_mb,
                "upload_error": f"Could not read file: {str(e)}",
            },
        )
```

- `app/main.py` — Register the new router

```python
from app.routers import pages, search, analysis, saved, upload
app.include_router(upload.router, prefix="/api")
```

**Key decisions:**
- **Dedicated router file** — upload returns RedirectResponse (not HTMX partials), so it doesn't belong in `search.py`
- Save as `data{ext}` (not original filename) — avoids path traversal, matches existing cache convention
- Use `status_code=303` (See Other) — browser changes POST to GET on redirect
- Read full content into memory — acceptable for ≤50 MB limit; reject empty files and oversized files before saving
- Only call `load_dataframe()` to verify parseability — `build_preview()` will run on the dataset page (avoid duplicate work)
- All errors return full `index.html` with `upload_error` — consistent strategy since this is a traditional form POST, not HTMX
- Wrap `_validate_content` errors with upload-appropriate message (no "URL" references)
- All imports at top of file (no inline imports)

## 4. Upload form on home page

**Current:** Home page has search bar only.

**Change:** Add an upload section below search, separated by a text divider.

### Files

- `app/templates/index.html` — Add upload section after search form

```html
<!-- After the search </section>, before <section id="search-results"> -->

{% if upload_error is defined and upload_error %}
<div class="error-message" role="alert">{{ upload_error }}</div>
{% endif %}

<section>
    <p style="text-align: center; color: var(--pico-muted-color);">&mdash; or upload your own &mdash;</p>
    <form id="upload-form"
          action="/api/dataset/upload"
          method="post"
          enctype="multipart/form-data">
        <fieldset role="group">
            <input type="file"
                   id="upload-file"
                   name="file"
                   accept=".csv,.json,.xlsx,.xls,.parquet"
                   aria-label="Upload a dataset file"
                   required>
            <button type="submit" id="upload-btn" disabled>Upload &amp; Preview</button>
        </fieldset>
        <small style="color: var(--pico-muted-color);">CSV, Excel, JSON, or Parquet &middot; max {{ max_file_size_mb }} MB</small>
    </form>
</section>
```

**Notes:**
- Traditional `<form>` POST (not HTMX) — the flow requires a full page redirect, not a partial swap
- `accept` attribute filters the file picker to allowed formats
- Button disabled until a file is selected (JS enables it)
- `upload_error` displayed above the form when present (server-side errors)
- `max_file_size_mb` passed from template context for the help text

## 5. Client-side JS — button enable/disable + upload spinner

**Minimal JS:** Only enable/disable the button and show a spinner on submit. No client-side extension or size validation — the `accept` attribute handles extension filtering, and the server enforces all validation.

### Files

- `app/static/js/app.js` — Add upload button logic

```javascript
// app/static/js/app.js — Upload button enable/disable + spinner
(function () {
    var fileInput = document.getElementById("upload-file");
    var uploadBtn = document.getElementById("upload-btn");
    var form = document.getElementById("upload-form");
    if (!fileInput || !uploadBtn || !form) return;

    fileInput.addEventListener("change", function () {
        uploadBtn.disabled = !fileInput.files.length;
    });

    form.addEventListener("submit", function () {
        uploadBtn.disabled = true;
        uploadBtn.setAttribute("aria-busy", "true");
        uploadBtn.textContent = "Uploading\u2026";
    });
})();
```

**Notes:**
- ES5 style (`var`, no arrow functions) matching existing `app.js`
- ~12 lines instead of ~40 — server validates everything, client just manages button state
- No `data-max-bytes` attribute needed
- No `#upload-error` div needed — errors come from server as full page re-render

## 6. Pass `max_file_size_mb` to home page template

### Files

- `app/routers/pages.py:home()` — Add config value to template context

```python
@router.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "max_file_size_mb": settings.max_file_size_mb},
    )
```

Only needed for the `<small>` help text ("max 50 MB"). No `data-max-bytes` attribute — client-side size validation was removed per review.

## 7. Tests

### Files

- `tests/test_upload.py` — New test file with 4 focused tests

```python
class TestUploadDataset:
    """Tests for the file upload feature."""

    @pytest.mark.asyncio
    async def test_upload_csv_saves_and_redirects(self, tmp_path):
        """Valid CSV upload saves file to cache and returns 303 redirect to dataset page."""

    @pytest.mark.asyncio
    async def test_upload_rejects_unsupported_extension(self):
        """Files with unsupported extensions return index.html with upload_error."""

    @pytest.mark.asyncio
    async def test_upload_rejects_empty_file(self):
        """Empty files (0 bytes) are rejected with clear error."""

    @pytest.mark.asyncio
    async def test_upload_rejects_unparseable_file(self):
        """Files that can't be loaded as DataFrame return index.html with upload_error."""


class TestDownloadDatasetUploadSource:
    """Tests for download_dataset with source='upload'."""

    @pytest.mark.asyncio
    async def test_resolves_cached_upload(self, tmp_path):
        """download_dataset('upload', id, '') finds and returns cached upload file."""

    @pytest.mark.asyncio
    async def test_missing_upload_raises(self):
        """download_dataset('upload', bad_id, '') raises ValueError."""
```

## Acceptance Criteria

- [x] Home page shows upload section below search with file picker and "Upload & Preview" button
- [x] Button is disabled until a file is selected
- [x] Upload button shows "Uploading..." spinner during submission
- [x] Uploading a valid CSV/Excel/JSON/Parquet file redirects to `/dataset/upload/{uuid}`
- [x] Dataset page shows preview and analysis config for uploaded file
- [x] Running analysis on uploaded dataset works correctly
- [x] Server rejects empty files (0 bytes)
- [x] Server rejects files exceeding `max_file_size_mb` setting
- [x] Server rejects files with HTML/XML content (with upload-friendly error message)
- [x] Server rejects unparseable files with clear error message
- [x] All server errors display on home page as `upload_error` (consistent error strategy)
- [x] Uploaded file saved as `data.{ext}` (not original filename) to prevent path traversal
- [x] `save_upload()` in dataset_loader.py encapsulates cache path logic (router doesn't import `_cache_path`)
- [x] All existing tests pass
- [x] New tests for upload validation, caching, and error cases

## Out of Scope

- Drag-and-drop upload (YAGNI — file picker is sufficient)
- Upload history / persistence (ephemeral cache only)
- Cache cleanup for old uploads (follow-up ticket)
- Re-upload from dataset page
- Client-side size/extension validation (server validates; `accept` attribute handles extension filtering)
- Magic byte validation (load_dataframe catches format mismatches; follow-up if needed)

## Review Feedback Incorporated

Changes from DHH, Kieran, and Simplicity reviewers:

1. **`_validate_content` signature** — made `url` optional with default `""` (was a 2-arg call bug)
2. **Consistent error handling** — all errors return `index.html` with `upload_error` (no partials for traditional POST)
3. **No inline imports** — `urllib.parse.quote` at top of file
4. **`save_upload()` in dataset_loader.py** — router doesn't reach into private `_cache_path` (DHH)
5. **1-line guard in `download_dataset()`** — reuses existing cache check, no duplicate file scanning (Simplicity)
6. **Stripped client-side JS to ~12 lines** — button enable/disable + spinner only (Simplicity)
7. **Removed `build_preview()` from upload endpoint** — only `load_dataframe()` for verification (Simplicity)
8. **Empty file rejection** — `len(content) == 0` check (Kieran)
9. **Dedicated `app/routers/upload.py`** — different response pattern than HTMX partials (Kieran)
10. **Upload-friendly error messages** — wrapped `_validate_content` errors (Kieran)

## References

- `app/services/dataset_loader.py:48-120` — `download_dataset()` routing logic
- `app/services/dataset_loader.py:33-45` — `_validate_content()`
- `app/services/dataset_loader.py:227-246` — `load_dataframe()` format dispatch
- `app/routers/search.py:39-74` — existing preview endpoint pattern
- `app/routers/pages.py:28-44` — dataset page route
- `app/templates/index.html` — current home page
- `docs/brainstorms/2026-02-08-upload-dataset-brainstorm.md` — design decisions
