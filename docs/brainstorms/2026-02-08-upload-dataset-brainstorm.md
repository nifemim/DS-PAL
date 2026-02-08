# Brainstorm: Upload Dataset

**Date:** 2026-02-08
**Ticket:** #20
**Status:** Ready for planning

## What We're Building

A file upload capability on the home page that lets users upload their own dataset files (CSV, Excel, JSON, Parquet) for analysis. Uploaded files go through the exact same preview and analysis pipeline as datasets found via search — upload is just another "source" in the system.

## Why This Approach

The existing dataset flow (download → load_dataframe → build_preview → analysis) already supports all target file formats. An upload feature only needs to:
1. Accept a file via multipart form
2. Save it to the cache directory
3. Redirect to the existing `/dataset/upload/{id}` page

Everything downstream (preview, column classification, encoding, clustering, visualization) works unchanged. This is the simplest possible integration.

## Key Decisions

1. **Upload UI location:** Home page, alongside the search bar — one page for all data entry points
2. **UX flow:** Upload saves the file and redirects straight to `/dataset/upload/{id}` (same dataset page as search results). No modal step.
3. **File formats:** CSV, Excel (.xlsx/.xls), JSON, Parquet — all already supported by `load_dataframe()`
4. **Interaction style:** Simple `<input type="file">` with a styled button. No drag-and-drop (YAGNI).
5. **Source identifier:** `source="upload"` — treated as another provider alongside kaggle, huggingface, etc.
6. **Storage:** `.cache/datasets/upload_{unique_id}/` following existing cache directory pattern
7. **Size limit:** Existing `max_file_size_mb` (50 MB) applies to uploads too
8. **Row limit:** Existing `max_dataset_rows` (10,000) applies at load time

## Current Architecture

- Dataset flow: `download_dataset()` → `load_dataframe()` → `build_preview()` → `run()`
- Cache dir: `.cache/datasets/{source}_{sanitized_id}/`
- File formats: CSV, JSON, Parquet, Excel already handled in `load_dataframe()`
- Size validation: `MAX_FILE_BYTES` computed from `settings.max_file_size_mb`
- Dataset page: `GET /dataset/{source}/{dataset_id:path}` renders preview + analysis config

## UI Design Decisions

1. **Layout:** Upload section sits below the search section, separated by a text divider ("— or upload your own —")
2. **Visual treatment:** Minimal — text divider + file input + styled button. Matches Pico CSS defaults. No card, no dashed border, no accent background.
3. **Upload button label:** "Upload & Preview" — communicates what happens next
4. **File input accept:** `.csv,.json,.xlsx,.xls,.parquet`
5. **Loading state:** Same spinner pattern as search (`aria-busy="true"`)

### Rough Layout

```
┌─────────────────────────────────────┐
│  Find & Analyze Datasets            │
│  Search across Kaggle, data.gov...  │
│                                     │
│  [search input...        ] [Search] │
│                                     │
│         — or upload your own —      │
│                                     │
│  [Choose file...] [Upload & Preview]│
│  CSV, Excel, JSON, or Parquet       │
│  (max 50 MB)                        │
└─────────────────────────────────────┘
```

## File Naming & Identification

- **Display name:** Original filename without extension (e.g., `sales_data.csv` → `sales_data`)
- **dataset_id:** Random UUID (e.g., `a3f8b2c1-4d5e-6f7a-8b9c-0d1e2f3a4b5c`)
- **Cache path:** `.cache/datasets/upload_a3f8b2c1/original_filename.csv`
- **URL:** `/dataset/upload/a3f8b2c1-4d5e-...?name=sales_data`
- The `name` query param carries the display name through the redirect, same as search results

## Persistence

- **Ephemeral (cache only):** Uploaded files are stored in `.cache/datasets/upload_{id}/` and treated the same as any cached dataset. No database record of uploads. No upload history UI.
- If the user wants to re-analyze, they re-upload. This keeps the feature simple and avoids managing upload state.
- Saved analyses already preserve results in the database — the upload file itself doesn't need to persist.

## Error Handling

1. **Error display:** Inline error message below the upload form (HTMX swaps into a target div). User stays on home page and can retry.
2. **Client-side validation:** Quick JS check on `file.size` before submitting — instant "File too large" feedback. Also validate file extension against accepted formats.
3. **Server-side validation:** Always validate size, format, and content server-side as safety net.
4. **Error scenarios:**
   - File too large (>50 MB) → "File exceeds 50 MB limit"
   - Unsupported format → "Unsupported file format. Please upload CSV, Excel, JSON, or Parquet"
   - Can't parse file → "Could not read file. Please check the format is valid"
   - Fewer than 2 usable columns → Shown on dataset page (existing validation in preview)

## Open Questions

None — ready to plan.
