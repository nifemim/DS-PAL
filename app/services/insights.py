"""LLM-powered cluster insights narrative."""
from __future__ import annotations

import json
import logging
import re

import httpx

from app.config import settings
from app.models.schemas import AnalysisOutput

logger = logging.getLogger(__name__)

_DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-latest"
_DEFAULT_OLLAMA_MODEL = "llama3.2"
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_TIMEOUT = 60


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

        sections["clusters"] = _merge_profiles(
            sections["clusters"], analysis.cluster_profiles
        )

        return sections
    except Exception:
        logger.exception("LLM insights call failed")
        return None


def _parse_response(raw: str) -> dict | None:
    """Parse structured JSON from LLM response.

    Returns dict with keys 'overview', 'clusters', 'quality',
    or None if parsing fails.
    """
    text = re.sub(r"^```\w*\n?", "", raw.strip())
    text = re.sub(r"\n?```$", "", text).strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

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


def _build_prompt(analysis: AnalysisOutput) -> tuple[str, str]:
    """Build system and user prompts from analysis data."""
    feature_map = _map_feature_names(analysis)

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
        "Use specific numbers. Be precise and professional.\n\n"
        "IMPORTANT: First, infer the domain of this dataset from its name and column names. "
        "Labels MUST use domain-specific vocabulary — not generic analytical terms. "
        "For example, for a flower dataset: GOOD: 'Large-petaled flowers'. BAD: 'High-value group'."
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

    if analysis.dataset_description:
        user += f"\n\nDataset context: {analysis.dataset_description}"

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
