"""Tests for dataset search."""
import pytest
from unittest.mock import AsyncMock, patch

from app.models.schemas import DatasetResult
from app.services.dataset_search import search_all
from app.services.search_ranker import rank_results


def _mock_results(source: str, count: int = 2):
    return [
        DatasetResult(
            source=source,
            dataset_id=f"{source}-{i}",
            name=f"Test Dataset {i}",
            description="A test dataset",
            url=f"https://example.com/{source}/{i}",
        )
        for i in range(count)
    ]


@pytest.fixture
def mock_providers():
    """Mock all providers to avoid real API calls."""
    with patch("app.services.dataset_search.PROVIDERS") as mock:
        providers = []
        for name in ["data.gov", "kaggle", "huggingface", "openml", "aws"]:
            p = AsyncMock()
            p.name = name
            p.search = AsyncMock(return_value=_mock_results(name))
            providers.append(p)
        mock.__iter__ = lambda self: iter(providers)
        mock.__len__ = lambda self: len(providers)
        # Make it work with zip and list comprehension
        yield providers


async def test_search_all_merges_results(mock_providers):
    with patch("app.services.dataset_search.PROVIDERS", mock_providers):
        results, providers = await search_all("test query")
    assert len(results) == 10  # 2 from each of 5 providers
    assert len(providers) == 5


async def test_search_all_handles_provider_failure(mock_providers):
    mock_providers[1].search = AsyncMock(side_effect=Exception("API down"))
    with patch("app.services.dataset_search.PROVIDERS", mock_providers):
        results, providers = await search_all("test query")
    # Should still get results from the other 4 providers
    assert len(results) == 8
    assert "kaggle" not in providers


async def test_search_all_empty_results(mock_providers):
    for p in mock_providers:
        p.search = AsyncMock(return_value=[])
    with patch("app.services.dataset_search.PROVIDERS", mock_providers):
        results, providers = await search_all("nonexistent dataset")
    assert len(results) == 0
    assert len(providers) == 0


# --- rank_results tests ---


def _make_result(name, source="test", description="", tags=None):
    return DatasetResult(
        source=source,
        dataset_id=f"{source}-{name}",
        name=name,
        description=description,
        url="https://example.com",
        tags=tags or [],
    )


class TestRankResults:
    def test_title_match_ranked_higher(self):
        results = [
            _make_result("Unrelated Data"),
            _make_result("Air Quality California"),
            _make_result("Some Other Dataset"),
        ]
        ranked = rank_results("air quality", results)
        assert ranked[0].name == "Air Quality California"

    def test_description_match_boosts_score(self):
        results = [
            _make_result("Dataset A", description="nothing relevant here"),
            _make_result("Dataset B", description="air quality monitoring data"),
        ]
        ranked = rank_results("air quality", results)
        assert ranked[0].name == "Dataset B"

    def test_tag_match_boosts_score(self):
        results = [
            _make_result("Dataset A", tags=["unrelated"]),
            _make_result("Dataset B", tags=["climate", "air quality"]),
        ]
        ranked = rank_results("air quality", results)
        assert ranked[0].name == "Dataset B"

    def test_dedup_removes_near_identical_names(self):
        results = [
            _make_result("Air Quality Dataset", source="kaggle"),
            _make_result("Air Quality Dataset", source="huggingface"),
        ]
        ranked = rank_results("air quality", results)
        assert len(ranked) == 1

    def test_dedup_keeps_distinct_datasets(self):
        results = [
            _make_result("Air Quality California"),
            _make_result("Water Quality Report"),
        ]
        ranked = rank_results("quality", results)
        assert len(ranked) == 2

    def test_empty_results(self):
        assert rank_results("anything", []) == []

    def test_single_result(self):
        results = [_make_result("Only One")]
        ranked = rank_results("one", results)
        assert len(ranked) == 1
        assert ranked[0].name == "Only One"

    def test_handles_no_tags_or_description(self):
        results = [_make_result("Bare Dataset")]
        ranked = rank_results("bare", results)
        assert len(ranked) == 1

    def test_typo_still_matches(self):
        results = [
            _make_result("California Air Quality"),
            _make_result("Random Numbers"),
        ]
        ranked = rank_results("califronia air qualty", results)
        # Fuzzy matching should still rank the air quality dataset higher
        assert ranked[0].name == "California Air Quality"
