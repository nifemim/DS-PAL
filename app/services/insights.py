"""LLM-powered cluster insights narrative."""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.models.schemas import AnalysisOutput

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_TIMEOUT = 30


async def generate_insights(analysis: AnalysisOutput) -> str | None:
    """Generate a plain-language narrative for clustering results.

    Returns None if LLM is disabled or the call fails.
    """
    if not settings.insights_enabled:
        return None

    system_prompt, user_prompt = _build_prompt(analysis)

    try:
        return await _call_anthropic(system_prompt, user_prompt)
    except Exception:
        logger.exception("LLM insights call failed")
        return None


def _build_prompt(analysis: AnalysisOutput) -> tuple[str, str]:
    """Build system and user prompts from analysis data."""
    feature_map = _map_feature_names(analysis)

    system = (
        "You are a data analyst writing a concise report. "
        "Write a 200-300 word narrative in three paragraphs: "
        "1) Overview of the dataset and clustering approach, "
        "2) Key characteristics that distinguish each cluster, "
        "3) Clustering quality assessment and notable anomalies. "
        "Use specific numbers. Be precise and professional. "
        "Do not use markdown headings or bullet points — just plain paragraphs."
    )

    # Build cluster summaries
    cluster_lines = []
    for p in analysis.cluster_profiles:
        top = []
        for f in p.top_features[:5]:
            name = feature_map.get(f["feature"], f["feature"])
            top.append(f"{name} (z={f['z_deviation']})")
        cluster_lines.append(
            f"Cluster {p.cluster_id}: {p.size} samples ({p.percentage}%), "
            f"top features: {', '.join(top)}"
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


async def _call_anthropic(system: str, user: str) -> str:
    """Call the Anthropic Messages API."""
    model = settings.llm_model or _DEFAULT_MODEL
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
                "max_tokens": 500,
                "temperature": 0.3,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
