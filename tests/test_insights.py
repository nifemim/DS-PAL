"""Tests for the LLM insights service."""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.schemas import AnalysisOutput, ClusterProfile
from app.services.insights import (
    _build_prompt,
    _map_feature_names,
    _merge_profiles,
    _parse_response,
    generate_insights,
)


@pytest.fixture
def sample_analysis():
    """Minimal AnalysisOutput for testing."""
    return AnalysisOutput(
        id="test-123",
        title="Test Analysis",
        dataset_source="test",
        dataset_id="ds-1",
        dataset_name="Sales Data",
        num_rows=100,
        num_columns=5,
        column_names=["age", "income", "city", "category", "score"],
        algorithm="kmeans",
        n_clusters=3,
        silhouette_score=0.65,
        cluster_profiles=[
            ClusterProfile(
                cluster_id=0,
                size=40,
                percentage=40.0,
                top_features=[
                    {"feature": "age", "cluster_mean": 55.0, "overall_mean": 40.0, "z_deviation": 2.1},
                    {"feature": "city_NY", "cluster_mean": 0.8, "overall_mean": 0.3, "z_deviation": 1.5},
                ],
            ),
            ClusterProfile(
                cluster_id=1,
                size=35,
                percentage=35.0,
                top_features=[
                    {"feature": "income", "cluster_mean": 90000, "overall_mean": 60000, "z_deviation": 1.8},
                ],
            ),
            ClusterProfile(
                cluster_id=2,
                size=25,
                percentage=25.0,
                top_features=[
                    {"feature": "category_Home", "cluster_mean": 0.9, "overall_mean": 0.2, "z_deviation": 2.5},
                ],
            ),
        ],
        cluster_labels=[0] * 40 + [1] * 35 + [2] * 25,
        anomaly_labels=[0] * 95 + [1] * 5,
        feature_names=["age", "income", "city_NY", "city_LA", "category_Home", "score"],
        encoding_info=[
            {
                "original_column": "city",
                "encoding_type": "one-hot",
                "new_columns": ["city_NY", "city_LA"],
                "cardinality": 3,
            },
            {
                "original_column": "category",
                "encoding_type": "one-hot",
                "new_columns": ["category_Home"],
                "cardinality": 2,
            },
        ],
    )


def test_build_prompt_includes_cluster_profiles(sample_analysis):
    system, user = _build_prompt(sample_analysis)
    assert "Cluster 0" in user
    assert "40 samples" in user
    assert "Cluster 1" in user
    assert "Cluster 2" in user


def test_build_prompt_domain_grounding_instructions(sample_analysis):
    """System prompt includes domain grounding instructions and few-shot example."""
    system, _ = _build_prompt(sample_analysis)
    assert "infer the domain" in system
    assert "domain-specific vocabulary" in system
    assert "Large-petaled flowers" in system
    assert "High-value group" in system


def test_build_prompt_includes_dataset_description(sample_analysis):
    """User prompt includes description when provided."""
    sample_analysis.dataset_description = "Monthly retail sales by region"
    _, user = _build_prompt(sample_analysis)
    assert "Dataset context: Monthly retail sales by region" in user


def test_build_prompt_no_description(sample_analysis):
    """User prompt has no 'Dataset context' line when description is empty."""
    sample_analysis.dataset_description = ""
    _, user = _build_prompt(sample_analysis)
    assert "Dataset context:" not in user


def test_build_prompt_whitespace_only_description():
    """Whitespace-only description is treated as empty after validator strips it."""
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
        dataset_description="   ",
    )
    assert analysis.dataset_description == ""
    _, user = _build_prompt(analysis)
    assert "Dataset context:" not in user


def test_build_prompt_maps_encoded_features(sample_analysis):
    _, user = _build_prompt(sample_analysis)
    # One-hot encoded "city_NY" should appear as "city"
    assert "- city: cluster mean=" in user
    # One-hot encoded "category_Home" should appear as "category"
    assert "- category: cluster mean=" in user


def test_build_prompt_includes_anomaly_count(sample_analysis):
    _, user = _build_prompt(sample_analysis)
    assert "5" in user
    assert "5.0%" in user


def test_map_feature_names_one_hot(sample_analysis):
    mapping = _map_feature_names(sample_analysis)
    assert mapping["city_NY"] == "city"
    assert mapping["city_LA"] == "city"
    assert mapping["category_Home"] == "category"


def test_map_feature_names_label():
    analysis = AnalysisOutput(
        id="x",
        title="x",
        dataset_source="x",
        dataset_id="x",
        dataset_name="x",
        num_rows=10,
        num_columns=1,
        column_names=["region"],
        algorithm="kmeans",
        n_clusters=2,
        cluster_profiles=[],
        cluster_labels=[],
        feature_names=["region"],
        encoding_info=[
            {
                "original_column": "region",
                "encoding_type": "label",
                "new_columns": ["region"],
                "cardinality": 10,
            },
        ],
    )
    mapping = _map_feature_names(analysis)
    assert mapping["region"] == "region"


@pytest.mark.asyncio
async def test_generate_insights_returns_none_when_disabled(sample_analysis):
    with patch("app.services.insights.settings") as mock_settings:
        mock_settings.insights_enabled = False
        result = await generate_insights(sample_analysis)
        assert result is None


def _make_llm_json(clusters):
    """Build a valid JSON LLM response string."""
    return json.dumps({
        "overview": "The Sales Data dataset was analyzed using K-Means with 3 clusters.",
        "clusters": clusters,
        "quality": "The silhouette score of 0.65 indicates good cluster separation.",
    })


@pytest.mark.asyncio
async def test_generate_insights_calls_anthropic(sample_analysis):
    llm_json = _make_llm_json([
        {"id": 0, "label": "Older urbanites", "description": "High age, concentrated in NY."},
        {"id": 1, "label": "High earners", "description": "Above-average income."},
        {"id": 2, "label": "Home buyers", "description": "Strong home category preference."},
    ])
    mock_response = httpx.Response(
        200,
        json={"content": [{"text": llm_json}]},
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

        result = await generate_insights(sample_analysis)
        assert result["overview"] == "The Sales Data dataset was analyzed using K-Means with 3 clusters."
        assert result["quality"] == "The silhouette score of 0.65 indicates good cluster separation."
        assert len(result["clusters"]) == 3
        assert result["clusters"][0]["label"] == "Older urbanites"
        assert result["clusters"][0]["size"] == 40
        assert result["clusters"][0]["percentage"] == 40.0
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_generate_insights_returns_none_on_failure(sample_analysis):
    with (
        patch("app.services.insights.settings") as mock_settings,
        patch("app.services.insights.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_settings.insights_enabled = True
        mock_settings.anthropic_api_key = "sk-test"
        mock_settings.llm_provider = "anthropic"
        mock_settings.llm_model = ""

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
            response=httpx.Response(500),
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await generate_insights(sample_analysis)
        assert result is None


@pytest.mark.asyncio
async def test_generate_insights_returns_none_on_invalid_json(sample_analysis):
    """Returns None when LLM produces non-JSON output."""
    mock_response = httpx.Response(
        200,
        json={"content": [{"text": "Just a paragraph of text, not JSON."}]},
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

        result = await generate_insights(sample_analysis)
        assert result is None


def test_build_prompt_requests_json(sample_analysis):
    """System prompt requests JSON output with cluster IDs."""
    system, _ = _build_prompt(sample_analysis)
    assert "JSON" in system
    assert "EXACTLY 3 entries" in system
    assert "IDs: 0, 1, 2" in system


def test_build_prompt_singular_cluster():
    """System prompt handles single cluster correctly."""
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
    assert "EXACTLY 1 entries" in system
    assert "IDs: 0" in system


@pytest.mark.asyncio
async def test_anthropic_called_with_scaled_max_tokens(sample_analysis):
    """generate_insights passes scaled max_tokens to Anthropic API."""
    llm_json = _make_llm_json([
        {"id": 0, "label": "A", "description": "X."},
        {"id": 1, "label": "B", "description": "Y."},
        {"id": 2, "label": "C", "description": "Z."},
    ])
    mock_response = httpx.Response(
        200,
        json={"content": [{"text": llm_json}]},
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

    def test_strips_code_fences_no_language(self):
        """Handles code fences without a language tag."""
        raw = '```\n{"overview": "x", "clusters": [], "quality": "y"}\n```'
        result = _parse_response(raw)
        assert result is not None

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
