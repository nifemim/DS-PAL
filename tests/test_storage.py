"""Tests for storage service."""
import pytest
from app.models.schemas import AnalysisOutput, ClusterProfile, ChartData
from app.services.storage import (
    save_analysis,
    get_analysis,
    list_analyses,
    delete_analysis,
    save_search_history,
)


def _make_analysis(id: str = "test-1") -> AnalysisOutput:
    return AnalysisOutput(
        id=id,
        title="Test Analysis",
        dataset_source="test",
        dataset_id="ds-1",
        dataset_name="Test Dataset",
        dataset_url="https://example.com",
        num_rows=100,
        num_columns=5,
        column_names=["a", "b", "c", "d", "e"],
        algorithm="kmeans",
        params={"n_clusters": 3},
        n_clusters=3,
        silhouette_score=0.65,
        cluster_profiles=[
            ClusterProfile(cluster_id=0, size=30, percentage=30.0),
            ClusterProfile(cluster_id=1, size=35, percentage=35.0),
            ClusterProfile(cluster_id=2, size=35, percentage=35.0),
        ],
        cluster_labels=[0] * 30 + [1] * 35 + [2] * 35,
        feature_names=["a", "b", "c"],
    )


def _make_charts() -> list[ChartData]:
    return [
        ChartData(
            chart_type="scatter_2d",
            title="2D Cluster Scatter",
            html="<div>chart1</div>",
            plotly_json='{"data": [], "layout": {}}',
        ),
        ChartData(
            chart_type="bar",
            title="Cluster Sizes",
            html="<div>chart2</div>",
            plotly_json='{"data": [], "layout": {}}',
        ),
    ]


@pytest.mark.asyncio
async def test_save_and_get_analysis():
    analysis = _make_analysis()
    charts = _make_charts()

    saved_id = await save_analysis(analysis, charts)
    assert saved_id == "test-1"

    loaded = await get_analysis("test-1")
    assert loaded is not None
    assert loaded.id == "test-1"
    assert loaded.title == "Test Analysis"
    assert loaded.dataset_source == "test"
    assert loaded.num_rows == 100
    assert len(loaded.column_names) == 5
    assert len(loaded.charts) == 2
    assert loaded.charts[0].chart_type == "scatter_2d"
    assert loaded.charts[1].chart_type == "bar"


@pytest.mark.asyncio
async def test_get_nonexistent_analysis():
    result = await get_analysis("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_analyses():
    analysis1 = _make_analysis("list-1")
    analysis2 = _make_analysis("list-2")
    analysis2.title = "Second Analysis"

    await save_analysis(analysis1, [])
    await save_analysis(analysis2, [])

    results = await list_analyses()
    assert len(results) >= 2
    titles = [r.title for r in results]
    assert "Test Analysis" in titles
    assert "Second Analysis" in titles


@pytest.mark.asyncio
async def test_delete_analysis():
    analysis = _make_analysis("del-1")
    await save_analysis(analysis, _make_charts())

    deleted = await delete_analysis("del-1")
    assert deleted is True

    loaded = await get_analysis("del-1")
    assert loaded is None


@pytest.mark.asyncio
async def test_delete_nonexistent():
    deleted = await delete_analysis("nonexistent")
    assert deleted is False


@pytest.mark.asyncio
async def test_save_search_history():
    await save_search_history("air quality", 15)
    # Just verify it doesn't raise
