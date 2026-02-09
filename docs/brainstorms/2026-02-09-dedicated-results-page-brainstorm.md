---
title: "Navigate to dedicated results page after analysis"
topic: dedicated-results-page
date: 2026-02-09
ticket: "#26"
---

# Navigate to Dedicated Results Page After Analysis

## Problem

Currently, when a user clicks "Analyze!" on the dataset page (`/dataset/{source}/{id}`), the analysis results load inline via HTMX into `#analysis-results` on the same page. This keeps the config form visible above the results, making the page long and cluttered. The user wants a clean separation: dataset page for config, dedicated page for results.

## Decisions

### Navigation: Standard form POST → loading page → SSE redirect
The form submits as a standard POST. The server immediately redirects to a loading page. Analysis runs in the background. An SSE stream pushes a "done" event when complete, triggering a JS redirect to `/analysis/{id}`.

### Results page: Reuse existing `/analysis/{id}`
The existing `analysis.html` page already has a lazy-loading shell pattern. Currently it loads from `/api/saved/{id}` — we'll add a unified detail endpoint that checks pending analyses first, then falls back to saved.

### Config form: Not on results page
The results page shows only results. To re-analyze, the user goes back to the dataset page.

### Error handling: Redirect back to dataset page
On analysis failure, redirect back to the dataset page with an error query param. The dataset template shows the error banner above the form, preserving user context.

## Current Flow

```
dataset.html
  └─ includes partials/dataset_preview.html (config form)
       └─ form hx-post="/api/analyze" hx-target="#analysis-results"
  └─ <section id="analysis-results"> (empty, HTMX swaps results here)
```

```
analysis.py POST /api/analyze
  → runs analysis_engine.run() synchronously (in executor)
  → stores in pending_analyses
  → returns partials/analysis_results.html (HTMX partial)
```

## Proposed Flow

```
dataset.html
  └─ includes partials/dataset_preview.html (config form)
       └─ standard form POST action="/api/analyze" method="post"
  └─ NO #analysis-results section needed
```

```
POST /api/analyze
  → validates inputs
  → creates a job entry in app.state.analysis_jobs with status="running"
  → kicks off background task (asyncio.create_task)
  → returns RedirectResponse("/analysis/loading/{job_id}", status_code=303)
```

```
loading.html (/analysis/loading/{job_id})
  └─ "Running analysis..." with aria-busy spinner
  └─ <script> connects to SSE endpoint /api/analysis/{job_id}/stream
       → on "complete" event: window.location = /analysis/{analysis_id}
       → on "error" event: window.location = /dataset/...?error=...
```

```
GET /api/analysis/{job_id}/stream (SSE)
  → yields "running" events while job in progress
  → yields "complete" event with analysis_id when done
  → yields "error" event with message on failure
```

```
analysis.html (/analysis/{id})
  └─ hx-get="/api/analysis/{id}/detail" hx-trigger="load"
       → unified endpoint: checks pending_analyses first, then saved
       → returns partials/analysis_results.html
```

## Key Design Points

### 1. Form changes in dataset_preview.html
- Remove `hx-post`, `hx-target`, `hx-indicator` from the form
- Change to standard `action="/api/analyze" method="post"`
- Remove the `#analysis-spinner` div (loading is now a separate page)

### 2. Background analysis with job tracking
- New `app.state.analysis_jobs` dict tracks job status: `{job_id: {status, analysis_id?, error?}}`
- `POST /api/analyze` creates the job, starts analysis as a background task, and redirects immediately
- Background task updates job status on completion or failure

### 3. Loading page with SSE
- New route `GET /analysis/loading/{job_id}` renders `loading.html`
- New SSE endpoint `GET /api/analysis/{job_id}/stream` sends events
- Minimal JS: `EventSource` connects to stream, `onmessage` handles redirect
- Fallback: if SSE fails, the page can poll or show a "check status" link

### 4. Unified detail endpoint
- `GET /api/analysis/{id}/detail` checks `pending_analyses` first, then saved
- Returns same `partials/analysis_results.html` partial
- Replaces current `hx-get="/api/saved/{id}"` in `analysis.html`

### 5. Error handling
- Background task catches errors and sets `job.status = "error"` with message
- SSE sends error event → JS redirects back to dataset page with `?error=...`
- Dataset page template checks for `error` query param and shows banner

### 6. Remove inline results from dataset.html
- Remove `<section id="analysis-results">` and `#analysis-spinner`
- Dataset page becomes config-only

## Files to Change

| File | Change |
|------|--------|
| `app/templates/partials/dataset_preview.html` | Remove HTMX attrs from form, add `action` + `method`, remove spinner |
| `app/templates/dataset.html` | Remove `#analysis-results` section, add error banner for `?error=` |
| `app/routers/analysis.py` | Background task pattern, redirect to loading page, SSE stream endpoint, unified detail endpoint |
| `app/templates/loading.html` | **New** — loading page with SSE connection |
| `app/templates/analysis.html` | Change `hx-get` to unified detail endpoint |
| `app/routers/pages.py` | Add loading page route |

**NOT modified:** `app/services/analysis_engine.py`, `app/services/visualization.py`, `app/services/insights.py` (all ML/viz/LLM services stay clean).

## Approach Summary

Switch the analysis form from HTMX to standard POST. The server kicks off analysis as a background task and redirects to a loading page. The loading page connects via SSE and redirects to `/analysis/{id}` when complete. The analysis page reuses the existing shell but loads from a unified endpoint that serves both pending and saved analyses. Errors redirect back to the dataset page with a message.
