---
title: "feat: Structured cluster insights table with JSON LLM output"
type: feat
date: 2026-02-08
ticket: 23
brainstorm: docs/brainstorms/2026-02-08-cluster-characteristics-table-brainstorm.md
---

# feat: Structured cluster insights table with JSON LLM output

Replace the free-form LLM paragraph with a structured table. The LLM returns JSON instead of `---`-separated prose, enabling reliable per-cluster labels and descriptions rendered in a scannable table.

**Scope reduction:** The original plan included a retry mechanism. All three reviewers independently recommended removal — the JSON prompt is explicit enough that if the LLM fails to produce valid JSON, retrying with the same prompt won't help. See [Review Feedback](#review-feedback) for details.

## 1. Change `_build_prompt()` to request JSON

**Current:** System prompt requests 3 paragraphs separated by `---`.

**Change:** Request a JSON object with `overview` (string), `clusters` (array of `{id, label, description}`), and `quality` (string). Keep the same analytical instructions but wrap in JSON format.

### Files

- `app/services/insights.py:_build_prompt()` — Rewrite system prompt to request JSON

```python
cluster_id_labels = [str(p.cluster_id) for p in analysis.cluster_profiles]
cluster_id_list = ", ".join(cluster_id_labels)
n = len(analysis.cluster_profiles)

system = (
    "You are a data analyst writing a concise report. "
    "Respond with ONLY a valid JSON object (no markdown, no code fences) with this exact structure:\n\n"
    '{"overview": "...", "clusters": [{"id": 0, "label": "...", "description": "..."}], "quality": "..."}\n\n'
    "Fields:\n"
    "- overview: 1-2 sentences summarizing the dataset, algorithm, and number of clusters.\n"
    f"- clusters: An array with EXACTLY {n} entries, one for each cluster "
    f"(IDs: {cluster_id_list}). "
    "Each entry has 'id' (integer), 'label' (2-4 word intuitive name like "
    "'high-income urbanites'), and 'description' (1 sentence explaining what "
    "makes this cluster unique, interpreting feature values and z-deviations).\n"
    "- quality: 1-2 sentences interpreting the silhouette score "
    "(below 0.25 = poor, 0.25-0.5 = fair, 0.5-0.75 = good, above 0.75 = excellent) "
    "and commenting on anomalies.\n\n"
    "Use specific numbers. Be precise and professional."
)
```

## 2. Replace `split_sections()` with JSON parsing

**Current:** `split_sections()` splits on `---` into 3 string sections.

**Change:** Parse JSON response. Validate required fields exist and have correct types. Return structured dict with `clusters` as a list of dicts instead of a string. Remove `split_sections()` and its import in `tests/test_insights.py`.

### Files

- `app/services/insights.py` — Replace `split_sections()` with `_parse_response()`

```python
import json
import re

def _parse_response(raw: str) -> dict | None:
    """Parse structured JSON from LLM response.

    Returns dict with keys 'overview', 'clusters', 'quality',
    or None if parsing fails.
    """
    # Strip markdown code fences if present
    text = re.sub(r"^```\w*\n?", "", raw.strip())
    text = re.sub(r"\n?```$", "", text).strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    # Validate required fields and types
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("overview"), str):
        return None
    if not isinstance(data.get("clusters"), list):
        return None
    if not isinstance(data.get("quality"), str):
        return None

    return {
        "overview": data["overview"],
        "clusters": [
            {
                "id": c["id"],
                "label": c["label"],
                "description": c["description"],
            }
            for c in data["clusters"]
            if isinstance(c, dict)
            and "id" in c and "label" in c and "description" in c
        ],
        "quality": data["quality"],
    }
```

## 3. Update `generate_insights()` with JSON parsing and profile merge

**Current:** Calls LLM, passes result to `split_sections()`, returns `dict[str, str]`.

**Change:** Call LLM, parse JSON with `_parse_response()`. On parse failure, return None (no retry). Return type changes to `dict[str, str | list]` (clusters is now a list). Merge cluster profiles (size/percentage) into the response for the template.

### Files

- `app/services/insights.py:generate_insights()` — Add JSON parsing and profile merge

```python
async def generate_insights(analysis: AnalysisOutput) -> dict | None:
    """Generate structured insights for clustering results.

    Returns a dict with 'overview' (str), 'clusters' (list of dicts
    with id, label, description, size, percentage), 'quality' (str),
    or None if LLM is disabled or the call fails.
    """
    if not settings.insights_enabled:
        return None

    system_prompt, user_prompt = _build_prompt(analysis)
    n_profiles = len(analysis.cluster_profiles)
    max_tokens = 300 + 150 * max(n_profiles, 1)

    try:
        if settings.llm_provider == "ollama":
            raw = await _call_ollama(system_prompt, user_prompt, max_tokens)
        else:
            raw = await _call_anthropic(system_prompt, user_prompt, max_tokens)

        sections = _parse_response(raw)
        if sections is None:
            logger.warning("LLM returned invalid JSON")
            return None

        # Merge cluster profile data (size, percentage) into LLM clusters
        sections["clusters"] = _merge_profiles(
            sections["clusters"], analysis.cluster_profiles
        )

        return sections
    except Exception:
        logger.exception("LLM insights call failed")
        return None
```

- `app/services/insights.py` — Add `_merge_profiles()` function

```python
def _merge_profiles(
    llm_clusters: list[dict],
    profiles: list,
) -> list[dict]:
    """Merge LLM cluster labels/descriptions with profile size data.

    Produces one row per profile. If the LLM missed a cluster,
    a fallback row is generated.
    """
    llm_by_id = {c["id"]: c for c in llm_clusters}
    merged = []
    for p in profiles:
        cid = p.cluster_id
        llm = llm_by_id.get(cid, {})
        merged.append({
            "id": cid,
            "label": llm.get("label") or f"Cluster {cid}",
            "description": llm.get("description") or "No description available.",
            "size": p.size,
            "percentage": p.percentage,
        })
    return merged
```

## 4. Update `cluster_insights.html` template

**Current:** Renders three `<p>` tags for overview, clusters (prose), quality.

**Change:** Render overview and quality as paragraphs. Render clusters as a table with columns: Cluster, Label, Size, Description.

### Files

- `app/templates/partials/cluster_insights.html` — Rewrite template

```html
{% if sections %}
<p>{{ sections.overview }}</p>

<table>
    <thead>
        <tr>
            <th>Cluster</th>
            <th>Label</th>
            <th>Size</th>
            <th>Description</th>
        </tr>
    </thead>
    <tbody>
        {% for c in sections.clusters %}
        <tr>
            <td>{% if c.id == -1 %}Noise{% else %}{{ c.id }}{% endif %}</td>
            <td><strong>{{ c.label }}</strong></td>
            <td>{{ c.size }} ({{ c.percentage }}%)</td>
            <td>{{ c.description }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>

<p>{{ sections.quality }}</p>

<div style="margin-top: 1rem;">
    <button class="outline secondary"
            hx-get="/api/analysis/{{ analysis_id }}/insights"
            hx-target="#cluster-insights"
            hx-swap="innerHTML">
        Regenerate
    </button>
</div>
{% else %}
<p>Insights unavailable.</p>
<button class="outline secondary"
        hx-get="/api/analysis/{{ analysis_id }}/insights"
        hx-target="#cluster-insights"
        hx-swap="innerHTML">
    Retry
</button>
{% endif %}
```

## 5. Collapse cluster profiles section in `analysis_results.html`

**Current:** Lines 52-87 render a "Cluster Profiles" `<details open>` section with per-cluster Feature/Mean/Deviation tables.

**Change:** Remove the `open` attribute so the section is collapsed by default. The LLM table provides the high-level view; the detailed feature stats remain available for users who want to drill down.

### Files

- `app/templates/partials/analysis_results.html:53` — Change `<details open>` to `<details>`

## 6. Pass cluster_profiles to the insights template

**Current:** The insights endpoint passes only `sections` and `analysis_id` to the template.

**Change:** No change needed — the `_merge_profiles()` function embeds size/percentage directly into `sections["clusters"]` before returning, so the template has all the data it needs.

## Acceptance Criteria

- [x] LLM prompt requests JSON with `{overview, clusters: [{id, label, description}], quality}`
- [x] `_parse_response()` parses JSON, strips code fences with regex, validates required fields and types
- [x] Returns None (shows "Insights unavailable") on parse failure — no retry
- [x] `_merge_profiles()` joins LLM clusters with profile size data by cluster_id
- [x] Missing clusters get fallback label ("Cluster N") and description ("No description available.")
- [x] Extra LLM clusters (not in profiles) are ignored
- [x] Template renders table with Cluster, Label, Size, Description columns
- [x] DBSCAN noise cluster (-1) displays as "Noise" in Cluster column
- [x] Overview and Quality render as paragraphs above/below the table
- [x] Cluster profiles section collapsed by default (remove `open` attribute)
- [x] `split_sections()` removed from `insights.py` and its import removed from `tests/test_insights.py`
- [x] Regenerate button works (re-fetches via HTMX)
- [x] All existing tests updated for new return format
- [x] New tests for `_parse_response()`, `_merge_profiles()`, and template rendering

## Tests

### Files

- `tests/test_insights.py` — Update existing tests, add new ones

```python
import json

from app.models.schemas import ClusterProfile
from app.services.insights import _parse_response, _merge_profiles


class TestParseResponse:
    """Tests for JSON parsing of LLM response."""

    def test_valid_json(self):
        """Parses well-formed JSON response."""
        raw = json.dumps({
            "overview": "The dataset...",
            "clusters": [{"id": 0, "label": "Big", "description": "Large cluster."}],
            "quality": "Good separation.",
        })
        result = _parse_response(raw)
        assert result is not None
        assert result["overview"] == "The dataset..."
        assert len(result["clusters"]) == 1
        assert result["clusters"][0]["label"] == "Big"

    def test_strips_code_fences(self):
        """Handles markdown code fences around JSON."""
        raw = '```json\n{"overview": "x", "clusters": [], "quality": "y"}\n```'
        result = _parse_response(raw)
        assert result is not None
        assert result["overview"] == "x"

    def test_invalid_json_returns_none(self):
        """Returns None for non-JSON text."""
        assert _parse_response("Just a paragraph of text.") is None

    def test_missing_required_field_returns_none(self):
        """Returns None when required fields are missing."""
        assert _parse_response('{"overview": "x"}') is None

    def test_clusters_not_a_list_returns_none(self):
        """Returns None when clusters is not an array."""
        raw = '{"overview": "x", "clusters": "not a list", "quality": "y"}'
        assert _parse_response(raw) is None

    def test_overview_not_a_string_returns_none(self):
        """Returns None when overview is not a string."""
        raw = '{"overview": 123, "clusters": [], "quality": "y"}'
        assert _parse_response(raw) is None

    def test_skips_malformed_cluster_entries(self):
        """Cluster entries missing required keys are dropped."""
        raw = json.dumps({
            "overview": "x",
            "clusters": [
                {"id": 0, "label": "Good", "description": "Fine."},
                {"id": 1},  # missing label and description
            ],
            "quality": "y",
        })
        result = _parse_response(raw)
        assert len(result["clusters"]) == 1
        assert result["clusters"][0]["id"] == 0


class TestMergeProfiles:
    """Tests for merging LLM clusters with profile data."""

    def _make_profile(self, cluster_id, size, percentage):
        return ClusterProfile(
            cluster_id=cluster_id,
            size=size,
            percentage=percentage,
            top_features=[],
        )

    def test_merge_matching_ids(self):
        """LLM clusters matched to profiles by id."""
        llm = [{"id": 0, "label": "Big", "description": "Large."}]
        profiles = [self._make_profile(0, 50, 50.0)]
        result = _merge_profiles(llm, profiles)
        assert result[0]["label"] == "Big"
        assert result[0]["size"] == 50
        assert result[0]["percentage"] == 50.0

    def test_missing_llm_cluster_gets_fallback(self):
        """Profile without LLM match gets fallback label and description."""
        llm = []
        profiles = [self._make_profile(0, 50, 50.0)]
        result = _merge_profiles(llm, profiles)
        assert result[0]["label"] == "Cluster 0"
        assert result[0]["description"] == "No description available."

    def test_extra_llm_cluster_ignored(self):
        """LLM cluster not in profiles is dropped."""
        llm = [
            {"id": 0, "label": "A", "description": "X."},
            {"id": 99, "label": "Ghost", "description": "Y."},
        ]
        profiles = [self._make_profile(0, 50, 50.0)]
        result = _merge_profiles(llm, profiles)
        assert len(result) == 1
        assert result[0]["id"] == 0

    def test_preserves_profile_order(self):
        """Output follows profile order, not LLM order."""
        llm = [
            {"id": 2, "label": "Second", "description": "B."},
            {"id": 0, "label": "First", "description": "A."},
        ]
        profiles = [
            self._make_profile(0, 30, 30.0),
            self._make_profile(2, 70, 70.0),
        ]
        result = _merge_profiles(llm, profiles)
        assert result[0]["label"] == "First"
        assert result[1]["label"] == "Second"
```

Update existing tests:
- `test_generate_insights_calls_anthropic` — Update mock LLM response to return JSON, update assertion to check structured dict with merged profiles
- `test_build_prompt_enumerates_clusters` — Update to check for JSON instruction in system prompt
- `test_build_prompt_singular_cluster` — Same update
- `test_split_sections_*` — Remove (function no longer exists)
- Remove `split_sections` from import statement in test file

## Edge Cases

- **DBSCAN noise cluster (-1):** Displays "Noise" in Cluster column. LLM is instructed to include it.
- **JSON with code fences:** `_parse_response()` strips fences via regex before parsing (common LLM behavior).
- **Partial JSON (valid but incomplete):** Missing `clusters` field → returns None → "Insights unavailable".
- **Empty clusters array:** Valid JSON but `clusters: []` → merge produces fallback rows for all profiles.
- **Duplicate LLM cluster IDs:** `llm_by_id` dict keeps last one; doesn't crash.
- **Malformed cluster entries:** Entries missing `id`, `label`, or `description` are silently dropped; `_merge_profiles()` provides fallbacks for any profiles not matched.

## Review Feedback

Changes from multi-agent review (DHH, Kieran, Simplicity):

### Dropped items

1. **Retry mechanism (original Change 3 included retry logic)** — All three reviewers independently recommended removal. Same rationale as ticket #21: the JSON prompt is explicit. If the LLM fails to produce valid JSON on the first try, retrying with the same prompt is unlikely to succeed. Removed ~15 LOC of retry + duplicate dispatch logic. A `logger.warning` provides observability.

### Fixes applied

2. **Keep cluster profiles section collapsed instead of removing** — DHH and Kieran both flagged this as a data fidelity regression. The detailed Feature/Mean/Deviation tables show raw numbers that the LLM summary doesn't cover. Changed from "remove section" to "remove `open` attribute" so it collapses by default but remains accessible.

3. **Use regex for code fence stripping** — Kieran flagged that the manual string splitting approach is fragile (e.g., fences without a language tag, fences with extra whitespace). Replaced with `re.sub()` for robustness.

4. **Don't silently coerce values in `_parse_response()`** — DHH and Kieran flagged that `str(data.get("overview", ""))` masks bad LLM output. Changed to strict `isinstance` checks — if a field has the wrong type, return None and let the fallback UI show "Insights unavailable".

5. **Skip malformed cluster entries instead of coercing** — Cluster entries missing `id`, `label`, or `description` are now dropped from the parsed list. `_merge_profiles()` handles the gap with fallback labels.

6. **Flesh out test stubs** — Kieran flagged that `TestMergeProfiles` had empty method bodies. Added full test implementations with a `_make_profile()` helper.

7. **Explicitly call out `split_sections` removal** — Kieran noted the plan should clearly state that `split_sections()` is deleted and its import removed from the test file. Added to Change 2 description and acceptance criteria.

## References

- `app/services/insights.py:69-132` — Current `_build_prompt()` and prompt text
- `app/services/insights.py:19-43` — Current `generate_insights()`
- `app/services/insights.py:46-66` — Current `split_sections()` (to be replaced)
- `app/templates/partials/cluster_insights.html` — Current 3-paragraph template
- `app/templates/partials/analysis_results.html:52-87` — Current cluster profiles section (to be collapsed)
- `app/routers/analysis.py:96-123` — Insights endpoint (passes analysis + sections to template)
- `tests/test_insights.py` — Existing test patterns
- `docs/brainstorms/2026-02-08-cluster-characteristics-table-brainstorm.md` — Design decisions
