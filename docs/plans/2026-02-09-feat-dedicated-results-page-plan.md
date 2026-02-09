---
title: "feat: Navigate to dedicated results page after analysis"
type: feat
date: 2026-02-09
ticket: "#26"
reviewed_by: DHH, Kieran, Simplicity
---

# feat: Navigate to Dedicated Results Page After Analysis

## Overview

Switch the analysis submission flow from inline HTMX (results load on dataset page) to a dedicated results page. The form submits as a standard POST, the server runs the analysis synchronously (as it does today), then redirects (303) to `/analysis/{id}`. Classic Post/Redirect/Get pattern.

## Problem Statement

Currently, clicking "Analyze!" on the dataset page loads results inline via HTMX into `#analysis-results`. This keeps the config form visible above the results, making the page long and cluttered. Users want a clean separation: dataset page for configuration, dedicated page for results.

## Proposed Solution

1. **Standard form POST** — Remove HTMX attrs from the config form, use `action="/api/analyze" method="post"`
2. **Synchronous analysis + redirect** — `POST /api/analyze` runs analysis exactly as it does today (via `run_in_executor`), stores results in `pending_analyses`, then returns `RedirectResponse("/analysis/{id}", status_code=303)`
3. **Unified detail endpoint** — `GET /api/analysis/{id}/detail` checks pending analyses first, then saved, returning the appropriate partial
4. **Error redirect** — Analysis errors redirect back to dataset page with `?error=` query param

No SSE. No background tasks. No loading page. No new JavaScript. The browser shows its native loading indicator during the POST, then the user lands on the results page.

## Technical Approach

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Analysis execution | **Synchronous in request** (unchanged) | `run_in_executor` already handles this cleanly. No need for background tasks. |
| Navigation pattern | **Post/Redirect/Get (303)** | Standard web pattern. Browser shows native loading during POST. |
| Unified detail endpoint | **Two partials, one endpoint** | Returns `analysis_results.html` for pending, `analysis_detail.html` for saved. |
| Form value preservation on error | **Not preserved** (v1) | Accept the loss for now. Can enhance later with sessionStorage. |
| Error display | **Redirect back to dataset page** | `?error=` query param, banner above the config form. |

### Files to Modify

| File | Change |
|------|--------|
| `app/routers/analysis.py` | Change `run_analysis()` return from `TemplateResponse` to `RedirectResponse`; add unified detail endpoint; add `get_analysis` import |
| `app/routers/pages.py` | Add `error` query param to `dataset_page` route |
| `app/templates/partials/dataset_preview.html` | Remove HTMX attrs from form, add `action`/`method`, remove spinner div |
| `app/templates/dataset.html` | Remove `#analysis-results` section, add error banner for `?error=` |
| `app/templates/analysis.html` | Change `hx-get` to unified detail endpoint |
| `tests/test_analysis.py` | Update tests for redirect behavior, add unified detail endpoint tests |

**NOT modified:** `app/services/analysis_engine.py`, `app/services/visualization.py`, `app/services/insights.py`, `app/main.py`.

### Implementation Steps

#### Phase A: Config Form + Dataset Page

- [x] Update config form in `app/templates/partials/dataset_preview.html`:
  - Remove `hx-post`, `hx-target`, `hx-indicator` from `<form>`
  - Add `action="/api/analyze" method="post"`
  - Remove `#analysis-spinner` div at the bottom

- [x] Update `app/templates/dataset.html`:
  - Remove `<section id="analysis-results">` block
  - Add error banner support above the preview section:

```html
{% if error_message %}
<section>
    <div class="error-message">
        <p>{{ error_message }}</p>
    </div>
</section>
{% endif %}
```

- [x] Add `error` query param to `dataset_page` route in `app/routers/pages.py`:

```python
@router.get("/dataset/{source}/{dataset_id:path}")
async def dataset_page(
    request: Request, source: str, dataset_id: str,
    name: str = "", url: str = "", sheet: str = "", joined: str = "",
    error: str = "",
):
```

  Pass `error_message=error` to template context.

- [x] Tests for Phase A:
  - Verify dataset page shows error banner when `?error=` is provided
  - Verify dataset page renders normally without error param

#### Phase B: Redirect + Error Handling

- [x] Change `run_analysis()` in `app/routers/analysis.py` to return redirect on success:

```python
@router.post("/analyze")
async def run_analysis(request: Request, source: str = Form(...), ...):
    try:
        file_path = await download_dataset(source, dataset_id, url)
        df = load_dataframe(file_path)

        loop = asyncio.get_event_loop()
        analysis = await loop.run_in_executor(
            None,
            lambda: analysis_engine.run(df=df, ...),
        )
        analysis.dataset_description = dataset_description
        charts = await loop.run_in_executor(None, lambda: generate_all(analysis))

        app = request.app
        app.state.pending_analyses[analysis.id] = {
            "analysis": analysis, "charts": charts, "created_at": time.time(),
        }
        _evict_old_pending(app)

        return RedirectResponse(f"/analysis/{analysis.id}", status_code=303)

    except Exception as e:
        logger.error("Analysis failed: %s", e, exc_info=True)
        error_msg = quote(str(e)[:200])
        return RedirectResponse(
            f"/dataset/{source}/{dataset_id}?name={quote(name)}&url={quote(url)}&error={error_msg}",
            status_code=303,
        )
```

- [x] Add `from urllib.parse import quote` to imports in `app/routers/analysis.py`

- [x] Tests for Phase B:
  - `test_run_analysis_redirects_to_analysis_page` — POST returns 303 to `/analysis/{id}`
  - `test_run_analysis_stores_in_pending` — verify analysis stored in `pending_analyses`
  - `test_run_analysis_error_redirects_to_dataset` — verify error redirect with `?error=`

#### Phase C: Unified Detail Endpoint + Analysis Page

- [x] Add unified detail endpoint in `app/routers/analysis.py`:

```python
@router.get("/analysis/{analysis_id}/detail")
async def analysis_detail(request: Request, analysis_id: str):
    # Check pending first
    pending = request.app.state.pending_analyses.get(analysis_id)
    if pending:
        return templates.TemplateResponse(
            "partials/analysis_results.html",
            {
                "request": request,
                "analysis": pending["analysis"],
                "charts": pending["charts"],
                "insights_enabled": settings.insights_enabled,
            },
        )

    # Fall back to saved
    saved = await get_analysis(analysis_id)
    if saved:
        return templates.TemplateResponse(
            "partials/analysis_detail.html",
            {"request": request, "analysis": saved},
        )

    return templates.TemplateResponse(
        "partials/error.html",
        {"request": request, "message": "Analysis not found or expired."},
    )
```

- [x] Add `from app.services.storage import get_analysis` to imports in `app/routers/analysis.py`

- [x] Update `app/templates/analysis.html` — change `hx-get`:

```html
<div id="analysis-detail"
     hx-get="/api/analysis/{{ analysis_id }}/detail"
     hx-trigger="load"
     hx-indicator="#analysis-spinner">
</div>
```

- [x] Confirm insights flow still works: `analysis_results.html` fires `hx-get="/api/analysis/{{ analysis.id }}/insights"` which reads from `pending_analyses` — no change needed since the analysis is stored there by the redirect flow

- [x] Tests for Phase C:
  - `test_unified_detail_returns_pending` — verify pending analysis returns `analysis_results.html`
  - `test_unified_detail_returns_saved` — verify saved analysis returns `analysis_detail.html`
  - `test_unified_detail_returns_not_found` — verify error partial for missing ID

#### Phase D: Final Cleanup + Verification

- [x] Verify all existing tests pass (insights tests, saved tests, upload tests)
- [ ] Manual testing: full flow from dataset page → analyze → results page
- [ ] Manual testing: error flow (bad data) → redirects back to dataset page with banner
- [ ] Manual testing: save analysis → refresh `/analysis/{id}` → loads from saved
- [ ] Manual testing: insights load correctly on the results page

## Acceptance Criteria

- [ ] "Analyze!" button on dataset page submits a standard HTML form (no HTMX)
- [ ] POST `/api/analyze` runs analysis synchronously and redirects (303) to `/analysis/{id}`
- [ ] Browser shows native loading indicator during the POST
- [ ] On success, user lands on `/analysis/{id}` which shows results via unified detail endpoint
- [ ] On error, user redirects back to dataset page with error banner
- [ ] `/analysis/{id}` works for both pending and saved analyses
- [ ] Insights panel loads correctly on the results page
- [ ] Save button works on the results page
- [ ] All existing tests pass, new tests cover redirect and detail flows
- [ ] No new dependencies, no new templates, no JavaScript added
- [ ] `analysis_engine.py` is NOT modified

## Review Feedback Applied

| Reviewer | Feedback | Resolution |
|----------|----------|------------|
| All 3 | SSE + background tasks is over-engineering for this use case | Removed entirely. Analysis runs synchronously, redirect on completion. |
| All 3 | Loading page unnecessary — analysis already completes in-request | Removed `loading.html`, SSE endpoint, job tracking dict, event formatting |
| All 3 | Use Post/Redirect/Get (standard web pattern) | `run_analysis()` returns `RedirectResponse(..., status_code=303)` |
| Kieran | `except (ValueError, Exception)` is dead code | Simplified to `except Exception` |
| Kieran | Missing `quote` import | Added to Phase B imports |
| Kieran | Confirm insights flow is unaffected | Added explicit verification step in Phase C |
| Simplicity | ~250 LOC plan reduced to ~30-40 LOC changes | 4 phases → simple form + redirect + unified endpoint |

## References

- Brainstorm: `docs/brainstorms/2026-02-09-dedicated-results-page-brainstorm.md`
- Current analysis form: `app/templates/partials/dataset_preview.html:60-136`
- Analysis route: `app/routers/analysis.py:21-97`
- Pages router: `app/routers/pages.py:37-41` (analysis page), `145-177` (dataset page)
- Dataset page: `app/templates/dataset.html`
- Analysis page: `app/templates/analysis.html`
- Saved detail partial: `app/templates/partials/analysis_detail.html`
- Results partial: `app/templates/partials/analysis_results.html`
- Institutional learning: `docs/solutions/architecture-patterns/async-llm-insights-with-graceful-degradation.md`
