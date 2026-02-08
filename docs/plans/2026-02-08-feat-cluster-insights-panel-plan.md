---
title: "Add LLM-generated cluster insights panel to analysis results"
type: feat
date: 2026-02-08
ticket: "#5"
priority: high
brainstorm: docs/brainstorms/2026-02-08-cluster-insights-panel-brainstorm.md
---

# Add LLM-Generated Cluster Insights Panel

## Overview

Add an LLM-powered plain-language narrative panel to analysis results that explains clustering findings in professional analyst report style. The panel loads asynchronously via HTMX after the main results render, supports Anthropic (Claude) and OpenAI providers via configuration, and degrades gracefully when no API key is configured.

## Problem Statement

The analysis results page shows raw numbers (silhouette score, cluster sizes, z-deviations) and charts, but non-technical users struggle to interpret what the clusters mean. A plain-language summary makes the analysis accessible to a wider audience.

## Proposed Solution

A new `insights` service calls a configured LLM provider to generate a ~200-300 word analyst report from the `AnalysisOutput` data. The report loads asynchronously into a bordered card at the top of the results, with Regenerate and Copy to Clipboard buttons.

### Architecture

```
[analysis_results.html]
    |
    | hx-get="/api/analysis/{id}/insights" hx-trigger="load"
    v
[GET /api/analysis/{id}/insights]  (analysis.py)
    |
    | lookup pending_analyses[id]
    v
[insights.py]  generate_insights(analysis)
    |
    | _build_prompt(analysis) -> messages
    | _map_feature_names(analysis) -> readable names
    v
[LLM provider]  (Anthropic or OpenAI via httpx)
    |
    v
[cluster_insights.html]  rendered card with narrative
```

## Acceptance Criteria

- [ ] Insights panel appears at the top of analysis results (before stats grid)
- [ ] Panel loads asynchronously — analysis results are visible immediately
- [ ] Skeleton placeholder shown while LLM generates narrative
- [ ] Narrative has 3 headed sections: Overview, Cluster Characteristics, Anomalies & Quality
- [ ] Supports both Anthropic and OpenAI providers via `LLM_PROVIDER` env var
- [ ] Graceful degradation: no API key configured = no panel rendered
- [ ] Auto-retry once on transient failure (5xx, 429, network error)
- [ ] After retry failure: shows "Insights unavailable" with manual Retry button
- [ ] Regenerate button triggers a fresh LLM call
- [ ] Copy to Clipboard button copies plain-text narrative
- [ ] Encoded feature names mapped back to original column names in the narrative
- [ ] Insights text persisted when analysis is saved
- [ ] Saved analysis detail page shows persisted insights (read-only, no Regenerate)
- [ ] LLM response rendered with Jinja2 auto-escaping (no `|safe`)
- [ ] Tests cover: prompt construction, provider routing, retry logic, graceful degradation, feature name mapping

## Technical Approach

### File 1: `app/config.py`

Add LLM settings following the existing credential pattern:

```python
# LLM insights
llm_provider: str = ""           # "anthropic" or "openai"; empty = disabled
anthropic_api_key: str = ""
openai_api_key: str = ""
llm_model: str = ""              # optional override; defaults per provider
```

Default models when `llm_model` is empty: `claude-haiku-4-5` (Anthropic), `gpt-4o-mini` (OpenAI).

Update `.env.example` with the new variables.

### File 2: `app/services/insights.py` (new)

Module-level functions following the existing service pattern (no classes). Key functions:

**`generate_insights(analysis: AnalysisOutput) -> Optional[str]`**
- Returns None if no API key configured
- Builds prompt via `_build_prompt()`
- Calls LLM via `_call_llm()`
- Auto-retries once on transient failure
- Returns the narrative text string, or None on failure

**`_build_prompt(analysis: AnalysisOutput) -> tuple[str, str]`**
- Returns `(system_prompt, user_prompt)`
- System prompt sets the analyst report tone and 3-section structure
- User prompt serializes: dataset name, algorithm, n_clusters, silhouette_score, cluster profiles with mapped feature names, anomaly count/percentage
- Maps encoded feature names to originals via `_map_feature_names()`

**`_map_feature_names(analysis: AnalysisOutput) -> dict[str, str]`**
- Uses `encoding_info` to build a map from processed names to original column names
- One-hot: `category_Home` -> `category`
- Label: `city` -> `city` (already original)
- Boolean/numeric-coerce: maps `new_columns[0]` -> `original_column`

**`_call_llm(system: str, user: str) -> str`**
- Routes to `_call_anthropic()` or `_call_openai()` based on `settings.llm_provider`
- Uses `httpx.AsyncClient` with 30s timeout
- Raises on non-retryable errors (400, 401, 403)

**`_call_anthropic(system: str, user: str) -> str`**
- POST `https://api.anthropic.com/v1/messages`
- Headers: `x-api-key`, `anthropic-version: 2023-06-01`
- Body: `model`, `max_tokens: 500`, `temperature: 0.3`, `system`, `messages`
- Extracts text from `content[0]["text"]`

**`_call_openai(system: str, user: str) -> str`**
- POST `https://api.openai.com/v1/chat/completions`
- Headers: `Authorization: Bearer {key}`
- Body: `model`, `max_tokens: 500`, `temperature: 0.3`, `messages` (system as first message)
- Extracts text from `choices[0]["message"]["content"]`

### File 3: `app/routers/analysis.py`

Add one new endpoint:

```python
@router.get("/analysis/{analysis_id}/insights")
async def get_insights(request: Request, analysis_id: str):
```

- Looks up `analysis_id` in `app.state.pending_analyses`
- If not found, checks saved analyses in DB for persisted insights text
- If no data found, returns empty `HTMLResponse("")`
- Calls `generate_insights()` in executor (blocks on LLM call)
- Returns `partials/cluster_insights.html` on success
- Returns error state HTML with Retry button on failure

Also fix the existing `created_at` bug: add `"created_at": time.time()` to the pending dict entry at line 59.

### File 4: `app/templates/partials/analysis_results.html`

Insert the insights placeholder **before** the stats grid, after the encoding info section. Only render the placeholder if LLM is configured:

```html
{% if insights_enabled %}
<article id="cluster-insights"
         hx-get="/api/analysis/{{ analysis.id }}/insights"
         hx-trigger="load"
         hx-swap="innerHTML"
         hx-request='{"timeout": 30000}'>
    <!-- Skeleton placeholder -->
    <div class="skeleton-heading"></div>
    <div class="skeleton-line"></div>
    <div class="skeleton-line"></div>
    <div class="skeleton-heading"></div>
    <div class="skeleton-line"></div>
    <div class="skeleton-line"></div>
    <div class="skeleton-line"></div>
    <div class="skeleton-heading"></div>
    <div class="skeleton-line"></div>
    <div class="skeleton-line"></div>
</article>
{% endif %}
```

Pass `insights_enabled = bool(settings.llm_provider and (settings.anthropic_api_key or settings.openai_api_key))` from the router.

### File 5: `app/templates/partials/cluster_insights.html` (new)

The insights card partial, returned by the GET endpoint:

```html
<h4>Overview</h4>
<p id="insights-text-overview">{{ overview }}</p>

<h4>Cluster Characteristics</h4>
<p id="insights-text-clusters">{{ cluster_characteristics }}</p>

<h4>Anomalies & Quality</h4>
<p id="insights-text-quality">{{ anomalies_quality }}</p>

<div class="insights-actions">
    <button class="outline secondary"
            hx-get="/api/analysis/{{ analysis_id }}/insights"
            hx-target="#cluster-insights"
            hx-swap="innerHTML"
            hx-indicator="#insights-regen-spinner">
        Regenerate
    </button>
    <span id="insights-regen-spinner" class="htmx-indicator" aria-busy="true"></span>
    <button class="outline secondary" data-copy-target="cluster-insights">
        Copy
    </button>
</div>
```

Section headers are hard-coded in the template. The LLM is instructed to return 3 paragraphs separated by `\n---\n` which the service splits into `overview`, `cluster_characteristics`, `anomalies_quality`.

Error state variant:

```html
<p>Insights unavailable.</p>
<button class="outline secondary"
        hx-get="/api/analysis/{{ analysis_id }}/insights"
        hx-target="#cluster-insights"
        hx-swap="innerHTML">
    Retry
</button>
```

### File 6: `app/static/css/style.css`

Add skeleton animation styles using Pico CSS variables for dark mode compatibility:

```css
.skeleton-line {
    height: 1rem;
    margin-bottom: 0.75rem;
    border-radius: var(--pico-border-radius);
    background: var(--pico-muted-border-color);
    animation: skeleton-pulse 1.5s ease-in-out infinite;
}
.skeleton-line:last-child { width: 60%; }
.skeleton-heading {
    height: 1.5rem;
    width: 40%;
    margin-bottom: 1rem;
    border-radius: var(--pico-border-radius);
    background: var(--pico-muted-border-color);
    animation: skeleton-pulse 1.5s ease-in-out infinite;
}
@keyframes skeleton-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}
```

### File 7: `app/static/js/app.js`

Add clipboard copy handler using event delegation (works with HTMX-swapped content):

```javascript
document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-copy-target]');
    if (!btn) return;
    var target = document.getElementById(btn.getAttribute('data-copy-target'));
    if (!target) return;
    navigator.clipboard.writeText(target.innerText).then(function() {
        var orig = btn.textContent;
        btn.textContent = 'Copied!';
        btn.setAttribute('disabled', '');
        setTimeout(function() { btn.textContent = orig; btn.removeAttribute('disabled'); }, 2000);
    });
});
```

### File 8: `app/database.py`

Add `insights_text TEXT` column to the `analyses` table for persisting insights when saving.

### File 9: `app/services/storage.py`

Include `insights_text` in the save/load cycle for saved analyses.

### File 10: `app/models/schemas.py`

Add `insights_text: str = ""` field to `SavedAnalysis`.

### File 11: `app/templates/partials/analysis_detail.html`

Show persisted insights in a static `<article>` card (no Regenerate, no async loading) if `insights_text` is present.

### File 12: `.env.example`

Add:
```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_anthropic_api_key
OPENAI_API_KEY=your_openai_api_key
LLM_MODEL=
```

### File 13: `tests/test_insights.py` (new)

Test cases:
- `test_build_prompt_includes_cluster_profiles` — prompt contains cluster sizes and top features
- `test_build_prompt_maps_encoded_features` — one-hot features mapped to original names
- `test_build_prompt_includes_anomaly_count` — anomaly percentage in prompt
- `test_generate_insights_returns_none_when_disabled` — no API key = None
- `test_generate_insights_calls_anthropic` — mocked httpx, verify request format
- `test_generate_insights_calls_openai` — mocked httpx, verify request format
- `test_generate_insights_retries_on_500` — first call 500, second succeeds
- `test_generate_insights_no_retry_on_401` — auth error not retried
- `test_generate_insights_returns_none_on_double_failure` — both attempts fail = None
- `test_map_feature_names_one_hot` — `category_Home` -> `category`
- `test_map_feature_names_label` — label encoded name unchanged
- `test_split_response_into_sections` — `\n---\n` separator produces 3 sections

## Files to Modify

| File | Changes |
|------|---------|
| `app/config.py` | Add `llm_provider`, `anthropic_api_key`, `openai_api_key`, `llm_model` |
| `app/services/insights.py` | **New** — LLM service with prompt construction, provider routing, retry |
| `app/routers/analysis.py` | Add `GET /analysis/{id}/insights` endpoint; fix `created_at` bug |
| `app/templates/partials/analysis_results.html` | Add insights skeleton placeholder before stats grid |
| `app/templates/partials/cluster_insights.html` | **New** — insights card partial with Regenerate/Copy buttons |
| `app/static/css/style.css` | Add skeleton animation styles |
| `app/static/js/app.js` | Add clipboard copy handler |
| `app/database.py` | Add `insights_text` column to analyses table |
| `app/services/storage.py` | Persist/load `insights_text` |
| `app/models/schemas.py` | Add `insights_text` to `SavedAnalysis` |
| `app/templates/partials/analysis_detail.html` | Show persisted insights |
| `.env.example` | Add LLM config variables |
| `tests/test_insights.py` | **New** — 12 tests for the insights service |

## Dependencies & Risks

- **No new pip dependencies** — uses existing `httpx` for LLM API calls
- **External API dependency** — LLM providers can be slow (2-10s) or unavailable; mitigated by async loading and retry
- **Cost** — ~500 input + 500 output tokens per call (~$0.001 with Haiku/mini). No cost guardrails needed at this scale.
- **Security** — LLM output rendered with Jinja2 auto-escaping (no `|safe`). Dataset names/column names in prompts are not sanitized but cannot break out of the prompt context.

## References

- Brainstorm: `docs/brainstorms/2026-02-08-cluster-insights-panel-brainstorm.md`
- Anthropic Messages API: `https://api.anthropic.com/v1/messages` (version `2023-06-01`)
- OpenAI Chat API: `https://api.openai.com/v1/chat/completions`
- Existing async HTMX pattern: `app/templates/analysis.html:3-6`
- Existing pending_analyses state: `app/routers/analysis.py:59`
- AnalysisOutput schema: `app/models/schemas.py:87-110`
- Encoding info structure: `app/services/analysis_engine.py:69-143`
