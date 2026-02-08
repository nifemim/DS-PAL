---
title: "Async LLM insights panel with provider abstraction and graceful degradation"
category: architecture-patterns
module: analysis-engine
tags: [llm, htmx, async, anthropic, ollama, graceful-degradation, insights]
symptoms:
  - "Need to add LLM-generated content without blocking page load"
  - "Want optional LLM features that work with or without API keys"
  - "Need to support multiple LLM providers"
date_solved: 2026-02-08
ticket: "#5"
---

## Problem

Analysis results needed a plain-language narrative panel explaining clustering findings — cluster sizes, distinguishing features, and actionable insights. This required calling an LLM API, which is slow (2-10s), optional (users may not have API keys), and needs to support multiple providers (cloud Anthropic or local Ollama).

The challenge: add an LLM-powered feature that doesn't block the page, doesn't crash without config, and works with different backends.

## Solution

### 1. Async HTMX loading — don't block the page

The insights panel loads independently via HTMX `hx-trigger="load"`, so analysis results render immediately while the LLM generates in the background:

```html
<!-- app/templates/partials/analysis_results.html -->
{% if insights_enabled %}
<article id="cluster-insights"
         hx-get="/api/analysis/{{ analysis.id }}/insights"
         hx-trigger="load"
         hx-swap="innerHTML">
    <p aria-busy="true">Generating insights...</p>
</article>
{% endif %}
```

The `{% if insights_enabled %}` check means the entire element is absent when no LLM is configured — zero footprint.

### 2. Provider abstraction — single interface, multiple backends

```python
# app/services/insights.py
async def generate_insights(analysis):
    if not settings.insights_enabled:
        return None
    system, user = _build_prompt(analysis)
    if settings.llm_provider == "anthropic":
        raw = await _call_anthropic(system, user)
    elif settings.llm_provider == "ollama":
        raw = await _call_ollama(system, user)
    else:
        return None
    return split_sections(raw)
```

Each provider function handles its own API format:
- **Anthropic**: `POST https://api.anthropic.com/v1/messages` with `x-api-key` header
- **Ollama**: `POST {base_url}/v1/chat/completions` (OpenAI-compatible endpoint)

Both use `temperature=0.3` for consistent analytical tone and `max_tokens=500`.

### 3. Graceful degradation — feature disappears cleanly

```python
# app/config.py
@property
def insights_enabled(self) -> bool:
    if self.llm_provider == "anthropic":
        return bool(self.anthropic_api_key)
    if self.llm_provider == "ollama":
        return True  # assumes local instance running
    return False
```

Three-level degradation:
1. **No provider configured** → `insights_enabled = False` → template block never renders
2. **Provider set but call fails** → `generate_insights()` returns `None` → "Insights unavailable" with Retry button
3. **Provider works** → Full narrative panel with Regenerate button

### 4. Structured LLM output parsing with fallback

The prompt instructs the LLM to separate three sections with `---` delimiters:

```python
def split_sections(text):
    parts = text.split("---")
    if len(parts) >= 3:
        return {"overview": parts[0], "clusters": parts[1], "quality": parts[2]}
    # Fallback: split on double-newlines
    parts = text.split("\n\n")
    # ... distribute into sections
```

This handles LLM output variability — structured when possible, graceful fallback when not.

### 5. Feature name mapping — readable prompts

Encoded column names (`city_NY`, `category_encoded`) are mapped back to original names before sending to the LLM:

```python
def _map_feature_names(analysis):
    mapping = {}
    for enc in analysis.encoding_info:
        for col in enc.new_columns:
            mapping[col] = enc.original_column
    return mapping
```

This ensures the LLM writes "city" not "city_NY" in its narrative.

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| HTMX async load vs inline | LLM calls take 2-10s; don't block results |
| `insights_enabled` property | Single source of truth for feature availability |
| Provider functions not classes | Only two providers, YAGNI on abstraction |
| Temperature 0.3 | Analyst tone needs consistency, not creativity |
| 60s timeout | Generous for LLM; prevents infinite hangs |
| Section splitting with fallback | LLMs don't always follow formatting instructions |

## Prevention

When adding optional LLM-powered features to web apps:

1. **Always load async** — never block the main content render for an LLM call
2. **Config-gated rendering** — the feature should be invisible (not broken) without config
3. **Three degradation levels** — no config, config but error, working
4. **Map internal names to human names** before prompting — the LLM output is only as good as its input
5. **Parse LLM output defensively** — always have a fallback for malformed responses

## Related

- `app/services/insights.py` — full insights service
- `app/templates/partials/cluster_insights.html` — insights template
- `app/routers/analysis.py:96-123` — insights API endpoint
- `app/config.py:19-31` — LLM configuration
