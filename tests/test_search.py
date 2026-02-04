"""Tests for dataset search."""
import pytest
from unittest.mock import AsyncMock, patch

from app.models.schemas import DatasetResult
from app.services.dataset_search import search_all


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
        for name in ["data.gov", "kaggle", "uci", "huggingface"]:
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
        results = await search_all("test query")
    assert len(results) == 8  # 2 from each of 4 providers


async def test_search_all_handles_provider_failure(mock_providers):
    mock_providers[1].search = AsyncMock(side_effect=Exception("API down"))
    with patch("app.services.dataset_search.PROVIDERS", mock_providers):
        results = await search_all("test query")
    # Should still get results from the other 3 providers
    assert len(results) == 6


async def test_search_all_empty_results(mock_providers):
    for p in mock_providers:
        p.search = AsyncMock(return_value=[])
    with patch("app.services.dataset_search.PROVIDERS", mock_providers):
        results = await search_all("nonexistent dataset")
    assert len(results) == 0
