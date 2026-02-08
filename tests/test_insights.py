"""Tests for the LLM insights service."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.schemas import AnalysisOutput, ClusterProfile
from app.services.insights import (
    _build_prompt,
    _map_feature_names,
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


def test_build_prompt_maps_encoded_features(sample_analysis):
    _, user = _build_prompt(sample_analysis)
    # One-hot encoded "city_NY" should appear as "city"
    assert "city (z=" in user
    # One-hot encoded "category_Home" should appear as "category"
    assert "category (z=" in user


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


@pytest.mark.asyncio
async def test_generate_insights_calls_anthropic(sample_analysis):
    mock_response = httpx.Response(
        200,
        json={"content": [{"text": "This analysis reveals three distinct clusters."}]},
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
        assert result == "This analysis reveals three distinct clusters."
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
