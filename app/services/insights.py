"""LLM-powered cluster insights narrative."""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.models.schemas import AnalysisOutput

logger = logging.getLogger(__name__)

_DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-latest"
_DEFAULT_OLLAMA_MODEL = "llama3.2"
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_TIMEOUT = 60


async def generate_insights(analysis: AnalysisOutput) -> dict[str, str] | None:
    """Generate a plain-language narrative for clustering results.

    Returns a dict with keys 'overview', 'clusters', 'quality',
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
        sections = split_sections(raw)
        if sections.get("clusters", "").lower().count("cluster") < n_profiles:
            logger.warning("Insights may not cover all %d clusters", n_profiles)
        return sections
    except Exception:
        logger.exception("LLM insights call failed")
        return None


def split_sections(text: str) -> dict[str, str]:
    """Split LLM response into three named sections.

    Tries '---' separator first, falls back to double-newline paragraph splitting.
    """
    # Try explicit --- separator
    parts = [p.strip() for p in text.split("---") if p.strip()]
    if len(parts) >= 3:
        return {
            "overview": parts[0],
            "clusters": parts[1],
            "quality": parts[2],
        }

    # Fallback: split on double newlines (paragraphs)
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    return {
        "overview": parts[0] if len(parts) > 0 else "",
        "clusters": parts[1] if len(parts) > 1 else "",
        "quality": parts[2] if len(parts) > 2 else "",
    }


def _build_prompt(analysis: AnalysisOutput) -> tuple[str, str]:
    """Build system and user prompts from analysis data."""
    feature_map = _map_feature_names(analysis)

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

    # Build cluster summaries with full feature detail
    cluster_lines = []
    for p in analysis.cluster_profiles:
        features_detail = []
        for f in p.top_features[:5]:
            name = feature_map.get(f["feature"], f["feature"])
            z = f["z_deviation"]
            direction = "above" if z > 0 else "below"
            features_detail.append(
                f"  - {name}: cluster mean={f['cluster_mean']}, "
                f"overall mean={f['overall_mean']}, "
                f"z={z} ({direction} average)"
            )
        cluster_lines.append(
            f"Cluster {p.cluster_id}: {p.size} samples ({p.percentage}%)\n"
            + "\n".join(features_detail)
        )

    anomaly_count = sum(1 for a in analysis.anomaly_labels if a == 1)
    anomaly_pct = (anomaly_count / analysis.num_rows * 100) if analysis.num_rows else 0

    user = (
        f"Dataset: {analysis.dataset_name}\n"
        f"Algorithm: {analysis.algorithm}\n"
        f"Clusters: {analysis.n_clusters}\n"
        f"Rows: {analysis.num_rows}, Features: {len(analysis.feature_names)}\n"
        f"Silhouette score: {analysis.silhouette_score}\n\n"
        f"Cluster profiles:\n" + "\n".join(cluster_lines) + "\n\n"
        f"Anomalies: {anomaly_count} ({anomaly_pct:.1f}% of data)"
    )

    return system, user


def _map_feature_names(analysis: AnalysisOutput) -> dict[str, str]:
    """Map encoded feature names back to original column names."""
    mapping: dict[str, str] = {}
    for enc in analysis.encoding_info:
        original = enc["original_column"]
        for new_col in enc["new_columns"]:
            if enc["encoding_type"] == "one-hot":
                # e.g. "category_Home" -> "category"
                mapping[new_col] = original
            else:
                # label, boolean, numeric-coerce: name unchanged
                mapping[new_col] = original
    return mapping


async def _call_ollama(system: str, user: str, max_tokens: int = 1024) -> str:
    """Call a local Ollama instance (OpenAI-compatible API)."""
    model = settings.llm_model or _DEFAULT_OLLAMA_MODEL
    url = f"{settings.ollama_base_url}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            url,
            json={
                "model": model,
                "temperature": 0.3,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        if resp.status_code != 200:
            logger.error("Ollama API error %s: %s", resp.status_code, resp.text)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _call_anthropic(system: str, user: str, max_tokens: int = 1024) -> str:
    """Call the Anthropic Messages API."""
    model = settings.llm_model or _DEFAULT_ANTHROPIC_MODEL
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _ANTHROPIC_URL,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 0.3,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        if resp.status_code != 200:
            logger.error("Anthropic API error %s: %s", resp.status_code, resp.text)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
