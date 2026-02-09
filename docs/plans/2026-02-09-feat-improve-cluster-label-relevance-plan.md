---
title: "feat: Improve cluster label relevance with domain grounding"
type: feat
date: 2026-02-09
ticket: "#24"
reviewed_by: DHH, Kieran, Simplicity
---

# feat: Improve Cluster Label Relevance with Domain Grounding

## Overview

Make LLM-generated cluster labels domain-aware so they reflect the actual dataset being analyzed. Currently labels tend to be generic ("High-value group") rather than grounded in the dataset's domain ("Large-petaled flowers" for iris data). Two changes: (1) improve the prompt with domain grounding instructions and few-shot examples, and (2) add an optional user-provided dataset description field that feeds into the prompt.

## Problem Statement

The current system prompt (`app/services/insights.py` `_build_prompt()`) tells the LLM to create "2-4 word intuitive name like 'high-income urbanites'" but doesn't instruct it to infer the domain from the dataset name and columns. The LLM defaults to generic analytical language regardless of dataset.

## Proposed Solution

### 1. Prompt Enhancement

Add domain grounding to the system prompt:
- Explicit instruction to infer domain from dataset name + column names
- "Labels MUST use domain-specific vocabulary" directive
- Good/bad few-shot example showing domain-specific vs generic labels

Add conditional user context to the user prompt:
- If `analysis.dataset_description` is non-empty: `"Dataset context: {description}"`

### 2. User-Provided Dataset Description

Add an optional textarea for users to describe their dataset. Minimal plumbing:

```
Form textarea → route param → set on AnalysisOutput after run() → _build_prompt() reads from analysis object
```

**Key design decision (from review):** Do NOT thread `dataset_description` through `analysis_engine.run()`. The ML pipeline has no use for it. Set it on `AnalysisOutput` in the route handler after `run()` returns. Do NOT add separate params to `generate_insights()` or `_build_prompt()` — they already receive the full `AnalysisOutput` object and should read `analysis.dataset_description` directly, same as they read `analysis.dataset_name`.

### 3. Regenerate with Updated Description

Keep existing GET endpoint for initial load. Add a POST endpoint on the same path for regeneration that accepts an updated description. Use an always-visible textarea (no JavaScript toggle) with HTMX `hx-include` on the Regenerate button.

## Technical Approach

### Files to Modify

| File | Change |
|------|--------|
| `app/models/schemas.py` | Add `dataset_description` field with `Field(max_length=500)` + `field_validator` to `AnalysisOutput` |
| `app/routers/analysis.py` | Accept `dataset_description: str = Form("")` in `run_analysis`, set on analysis after `run()`. Add POST `regenerate_insights` endpoint. |
| `app/services/insights.py` | Update `_build_prompt` — domain grounding in system prompt, read `analysis.dataset_description` for conditional user prompt context |
| `app/templates/partials/dataset_preview.html` | Add textarea before submit button |
| `app/templates/partials/cluster_insights.html` | Always-visible textarea + `hx-post` Regenerate button with `hx-include` |
| `tests/test_insights.py` | Update prompt tests, add description flow tests |

**NOT modified:** `app/services/analysis_engine.py` (ML pipeline stays clean), `app/templates/partials/analysis_results.html` (initial load stays GET).

### Implementation Steps

#### Phase A: Schema + Prompt + Config Form

- [x] Add `dataset_description` field to `AnalysisOutput` in `app/models/schemas.py`:

```python
dataset_description: str = Field(default="", max_length=500)

@field_validator("dataset_description")
@classmethod
def sanitize_description(cls, v: str) -> str:
    return v.strip()
```

- [x] Accept `dataset_description: str = Form("")` in `run_analysis()` route in `app/routers/analysis.py`
- [x] Set description on analysis object after `run()` returns (NOT passed through `analysis_engine.run()`):

```python
analysis = await loop.run_in_executor(None, lambda: analysis_engine.run(...))
analysis.dataset_description = dataset_description
```

- [x] Add domain grounding instructions to system prompt in `_build_prompt()` in `app/services/insights.py` (after existing "Be precise and professional" line):
  - "First, infer the domain of this dataset from its name and column names."
  - "Labels MUST use domain-specific vocabulary — not generic analytical terms."
  - Good/bad example: "For a flower dataset: GOOD: 'Large-petaled flowers'. BAD: 'High-value group'."
- [x] Add conditional context to user prompt in `_build_prompt()`: if `analysis.dataset_description`, append `"Dataset context: {analysis.dataset_description}"` — no signature change needed, reads from the object
- [x] Add textarea to `app/templates/partials/dataset_preview.html` between the categorical columns fieldset and the submit button:

```html
<label for="dataset_description">Dataset Description (optional)</label>
<textarea name="dataset_description" id="dataset_description"
          rows="2" maxlength="500"
          placeholder="Describe your data to improve cluster labels (e.g. 'monthly sales by region')"></textarea>
```

- [x] Tests for Phase A:
  - Update `test_build_prompt_includes_cluster_profiles` — verify domain grounding text in system prompt
  - Add `test_build_prompt_domain_grounding_instructions` — verify system prompt contains domain grounding instructions and few-shot example
  - Add `test_build_prompt_includes_dataset_description` — verify "Dataset context:" appears in **user** prompt (not system) when description provided
  - Add `test_build_prompt_no_description` — verify no "Dataset context:" line when description is empty
  - Add `test_build_prompt_whitespace_only_description` — verify whitespace-only description treated as empty after validator strips it
  - Update `sample_analysis` fixture to include `dataset_description` field

#### Phase B: POST Regenerate + Insights Textarea

- [x] Keep existing `get_insights` as `@router.get` for initial load (reads `analysis.dataset_description` from stored `AnalysisOutput`)
- [x] Add new `@router.post` endpoint `regenerate_insights` on the same path `/analysis/{analysis_id}/insights`:

```python
@router.post("/analysis/{analysis_id}/insights")
async def regenerate_insights(
    request: Request,
    analysis_id: str,
    dataset_description: str = Form(""),
):
    entry = request.app.state.pending_analyses.get(analysis_id)
    if not entry:
        return HTMLResponse("")
    analysis = entry["analysis"]
    analysis.dataset_description = dataset_description  # update stored description
    sections = await generate_insights(analysis)
    # ... render template same as get_insights
```

- [x] Update `app/templates/partials/cluster_insights.html` — replace current Regenerate button with always-visible textarea + `hx-post`:

```html
<div style="margin-top: 1rem;">
    <label for="dataset_description">Dataset description (improves labels)</label>
    <textarea name="dataset_description" id="dataset_description"
              rows="2" maxlength="500"
              placeholder="e.g. 'monthly sales by region'"
    >{{ dataset_description or '' }}</textarea>
    <button class="outline secondary"
            hx-post="/api/analysis/{{ analysis_id }}/insights"
            hx-target="#cluster-insights"
            hx-swap="innerHTML"
            hx-include="[name='dataset_description']">
        Regenerate
    </button>
</div>
```

- [x] Pass `dataset_description` from route context to template in both `get_insights` and `regenerate_insights`:

```python
"dataset_description": analysis.dataset_description,
```

- [x] Tests for Phase B:
  - Add `test_regenerate_endpoint_accepts_description` — POST to insights endpoint with description param, verify stored description is updated
  - Update `test_generate_insights_calls_anthropic` — set `dataset_description` on `sample_analysis` fixture

## Acceptance Criteria

- [ ] System prompt includes domain grounding instructions and few-shot good/bad example
- [ ] User prompt conditionally includes "Dataset context: {description}" when description is non-empty
- [ ] Analysis config form has a textarea for optional dataset description
- [ ] Description flows through: form → route → set on AnalysisOutput → `_build_prompt()` reads from object
- [ ] Regenerate button sends POST with description via `hx-include`
- [ ] Insights panel shows always-visible textarea pre-filled with current description
- [ ] Pydantic `Field(max_length=500)` + `field_validator` strips whitespace
- [ ] All existing tests pass, new tests cover description flow and prompt changes
- [ ] Empty/whitespace-only description produces no change to current behavior (backward compatible)
- [ ] `analysis_engine.py` is NOT modified (ML pipeline stays clean)
- [ ] No JavaScript added — pure HTMX with `hx-include`

## Review Feedback Applied

| Reviewer | Feedback | Resolution |
|----------|----------|------------|
| All 3 | Don't thread through `analysis_engine.run()` | Set on `AnalysisOutput` in route handler after `run()` returns |
| All 3 | Don't add separate params to `generate_insights`/`_build_prompt` | Read `analysis.dataset_description` from the object directly |
| All 3 | Kill expandable edit UI | Always-visible textarea, no JavaScript toggle |
| All 3 | Keep initial load as GET | `analysis_results.html` unchanged |
| All 3 | Collapse 6 phases to 2 | Phase A (schema+prompt+form) + Phase B (POST regenerate+insights textarea) |
| Kieran | Use `Field(max_length=500)` + `field_validator` | Pydantic validation instead of `[:500]` truncation |
| Kieran | Two endpoints: GET + POST on same path | `get_insights` (GET) + `regenerate_insights` (POST) |
| Kieran | Missing tests for whitespace, boundary, placement | Added to Phase A/B test lists |
| Simplicity | Use `hx-include` for textarea in POST | Idiomatic HTMX, zero JavaScript |

## References

- Brainstorm: `docs/brainstorms/2026-02-09-cluster-label-relevance-brainstorm.md`
- Current prompt: `app/services/insights.py` `_build_prompt()`
- Route: `app/routers/analysis.py` `run_analysis()`, `get_insights()`
- Schema: `app/models/schemas.py` `AnalysisOutput`
- Config form: `app/templates/partials/dataset_preview.html`
- Insights template: `app/templates/partials/cluster_insights.html`
- Tests: `tests/test_insights.py`
