---
title: "fix: Ensure LLM insights describe all clusters"
type: fix
date: 2026-02-08
ticket: 21
brainstorm: docs/brainstorms/2026-02-08-insights-cluster-coverage-brainstorm.md
---

# fix: Ensure LLM insights describe all clusters

The LLM insights panel sometimes skips clusters in its Cluster Characteristics section. Two root causes: `max_tokens=500` can truncate before all clusters are covered, and the prompt says "for each cluster" without enforcing it. Fix both, and add observability logging for incomplete coverage.

**Scope reduction:** The original plan had 3 items. Review dropped the retry mechanism (Change 3) as over-engineered — Changes 1 and 2 address both root causes directly. See [Review Feedback](#review-feedback) for rationale.

## 1. Increase and scale max_tokens

**Current:** `max_tokens=500` hardcoded in `_call_anthropic()` (line 169). Ollama has no max_tokens set.

**Change:** Scale tokens based on cluster count. Base of 300 for overview + quality, plus ~150 per cluster. Derive cluster count from `cluster_profiles` (not `n_clusters`) to correctly include DBSCAN noise profiles.

### Files

- `app/services/insights.py:_call_anthropic()` — Accept `max_tokens` param instead of hardcoded 500

```python
async def _call_anthropic(system: str, user: str, max_tokens: int = 1024) -> str:
    # ... existing code ...
    json={
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        # ...
    },
```

- `app/services/insights.py:_call_ollama()` — Add `max_tokens` param, pass as `max_tokens` in OpenAI-compatible API

```python
async def _call_ollama(system: str, user: str, max_tokens: int = 1024) -> str:
    # ... existing code ...
    json={
        "model": model,
        "temperature": 0.3,
        "max_tokens": max_tokens,
        # ...
    },
```

- `app/services/insights.py:generate_insights()` — Compute `max_tokens` from `cluster_profiles` length, pass to provider. Add a warning log when coverage looks incomplete.

```python
n_profiles = len(analysis.cluster_profiles)
max_tokens = 300 + 150 * max(n_profiles, 1)

if settings.llm_provider == "ollama":
    raw = await _call_ollama(system_prompt, user_prompt, max_tokens)
else:
    raw = await _call_anthropic(system_prompt, user_prompt, max_tokens)

sections = split_sections(raw)

# Observability: warn if coverage looks incomplete
if sections.get("clusters", "").lower().count("cluster") < n_profiles:
    logger.warning("Insights may not cover all %d clusters", n_profiles)

return sections
```

## 2. Restructure the prompt for explicit cluster enumeration

**Current:** System prompt says "For each cluster, give it an intuitive label" — too vague, LLM can skip clusters.

**Change:** Add explicit cluster count and list cluster IDs in the system prompt. Handle singular/plural grammar.

### Files

- `app/services/insights.py:_build_prompt()` — Make paragraph 2 instruction reference the exact cluster count and IDs

```python
# Build list of cluster IDs for the prompt
cluster_id_labels = [str(p.cluster_id) for p in analysis.cluster_profiles]
cluster_id_list = ", ".join(cluster_id_labels)
n = len(analysis.cluster_profiles)

if n == 1:
    cluster_instruction = f"Describe the single cluster (Cluster {cluster_id_list})."
else:
    cluster_instruction = (
        f"You MUST describe ALL {n} clusters (Cluster {cluster_id_list})."
    )

system = (
    "You are a data analyst writing a concise report. "
    "Write exactly three paragraphs separated by a line containing only '---':\n\n"
    "Paragraph 1 — Overview: Summarize the dataset, algorithm used, and number of clusters found.\n\n"
    f"Paragraph 2 — Cluster Characteristics: {cluster_instruction} "
    "For each cluster, give it an intuitive label based on its distinguishing features "
    "(e.g. 'high-income urban professionals', 'budget-conscious young renters'). "
    "Explain what makes each cluster unique by interpreting the feature values and z-deviations. "
    "A positive z-deviation means the cluster is above average for that feature; negative means below. "
    "Describe the real-world meaning of these patterns — don't just list numbers.\n\n"
    "Paragraph 3 — Anomalies & Quality: Interpret the silhouette score "
    "(below 0.25 = poor, 0.25-0.5 = fair, 0.5-0.75 = good, above 0.75 = excellent). "
    "Comment on anomaly count and what might make those points unusual.\n\n"
    "Use specific numbers. Be precise and professional. "
    "Do not use markdown headings or bullet points — just plain paragraphs separated by ---"
)
```

## Acceptance Criteria

- [x] `max_tokens` scales with cluster profile count (base 300 + 150 per profile)
- [x] Both `_call_anthropic` and `_call_ollama` accept `max_tokens` parameter
- [x] Token budget derived from `len(cluster_profiles)`, not `n_clusters`
- [x] System prompt explicitly states cluster count and lists all cluster IDs
- [x] Singular/plural grammar handled ("the single cluster" vs "ALL N clusters")
- [x] Warning logged when clusters section looks incomplete
- [x] All existing insights tests pass
- [x] New tests for prompt enumeration and max_tokens scaling

## Tests

### Files

- `tests/test_insights.py` — Add to existing test file

```python
def test_build_prompt_enumerates_clusters(sample_analysis):
    """System prompt explicitly states cluster count and IDs."""
    system, _ = _build_prompt(sample_analysis)
    assert "ALL 3 clusters" in system
    assert "Cluster 0, 1, 2" in system


def test_build_prompt_singular_cluster():
    """System prompt uses singular grammar for one cluster."""
    analysis = AnalysisOutput(
        id="x", title="x", dataset_source="x", dataset_id="x",
        dataset_name="x", num_rows=10, num_columns=1, column_names=["a"],
        algorithm="kmeans", n_clusters=1,
        cluster_profiles=[
            ClusterProfile(cluster_id=0, size=10, percentage=100.0, top_features=[]),
        ],
        cluster_labels=[0] * 10,
        feature_names=["a"],
        encoding_info=[],
    )
    system, _ = _build_prompt(analysis)
    assert "the single cluster" in system
    assert "Cluster 0" in system


@pytest.mark.asyncio
async def test_anthropic_called_with_scaled_max_tokens(sample_analysis):
    """generate_insights passes scaled max_tokens to Anthropic API."""
    llm_text = "Overview.\n---\nCluster 0. Cluster 1. Cluster 2.\n---\nQuality."
    mock_response = httpx.Response(
        200,
        json={"content": [{"text": llm_text}]},
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )

    with (
        patch("app.services.insights.settings") as mock_settings,
        patch("app.services.insights.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_settings.insights_enabled = True
        mock_settings.anthropic_api_key = "sk-test"
        mock_settings.llm_provider = "anthropic"
        mock_settings.llm_model = ""

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await generate_insights(sample_analysis)

        # 3 cluster profiles: 300 + 150*3 = 750
        call_kwargs = mock_client.post.call_args
        request_body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert request_body["max_tokens"] == 750
```

## Edge Cases

- **DBSCAN noise cluster (-1):** The noise cluster profile is included in `analysis.cluster_profiles` so it will be listed in the prompt. Token budget accounts for it.
- **Single cluster:** Token budget = 300 + 150 = 450. Prompt says "the single cluster (Cluster 0)".
- **Zero clusters (DBSCAN all-noise):** `max(n_profiles, 1)` floors the token calculation at 450.

## Review Feedback

Changes from multi-agent review (DHH, Kieran, Simplicity):

### Dropped items

1. **Post-generation validation + retry (original Change 3)** — All three reviewers independently recommended removal. The retry mechanism doubles API latency and cost for a speculative failure mode that Changes 1 and 2 directly address. The regex validation against free-form LLM text is inherently fragile ("Cluster 0" vs "the first group"). If the improved prompt and scaled tokens don't fix the problem, a single retry won't either. Replaced with a `logger.warning` for observability — if warnings fire frequently in production, retry logic can be added then.

### Fixes applied

2. **`n_clusters` vs `len(cluster_profiles)` inconsistency** — Kieran flagged that `n_clusters` may not include DBSCAN noise cluster (-1) but `cluster_profiles` will. All calculations now derive from `len(analysis.cluster_profiles)` as single source of truth.

3. **Ollama `max_completion_tokens` field name** — Kieran flagged that Ollama's OpenAI-compatible endpoint uses `max_tokens`, not `max_completion_tokens`. Corrected.

4. **"ALL 1 clusters" grammar** — Kieran flagged poor grammar for single-cluster case. Added singular/plural conditional.

5. **`test_max_tokens_scales_with_clusters` was a no-op** — All three reviewers noted it tested arithmetic (`300 + 150*3 == 750`), not code. Replaced with `test_anthropic_called_with_scaled_max_tokens` that inspects the actual request payload.

6. **`cluster_ids` name reused with different types** — Renamed to `cluster_id_labels` in `_build_prompt` to avoid confusion with `list[int]` usage elsewhere.

## References

- `app/services/insights.py:64-116` — Current `_build_prompt()`
- `app/services/insights.py:19-38` — Current `generate_insights()`
- `app/services/insights.py:156-178` — Current `_call_anthropic()` with hardcoded `max_tokens=500`
- `app/services/insights.py:134-153` — Current `_call_ollama()` with no max_tokens
- `app/services/insights.py:41-61` — `split_sections()`
- `tests/test_insights.py` — Existing test patterns (mock httpx, patch settings)
- `docs/brainstorms/2026-02-08-insights-cluster-coverage-brainstorm.md` — Design decisions
