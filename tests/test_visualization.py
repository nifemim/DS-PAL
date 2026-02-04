"""Tests for visualization generation."""
import json
import pytest
import pandas as pd
from sklearn.datasets import load_iris

from app.services.analysis_engine import run
from app.services.visualization import (
    scatter_2d,
    scatter_3d,
    cluster_sizes,
    feature_boxplots,
    correlation_heatmap,
    silhouette_plot,
    parallel_coordinates,
    anomaly_overlay,
    generate_all,
)


@pytest.fixture
def analysis_output():
    """Run analysis on Iris to get a real AnalysisOutput."""
    data = load_iris()
    df = pd.DataFrame(data.data, columns=data.feature_names)
    return run(df, "Iris", "test", "iris", algorithm="kmeans", n_clusters=3)


def test_scatter_2d(analysis_output):
    chart = scatter_2d(analysis_output)
    assert chart.chart_type == "scatter_2d"
    assert chart.html
    assert chart.plotly_json
    data = json.loads(chart.plotly_json)
    assert "data" in data
    assert len(data["data"]) == 3  # 3 clusters


def test_scatter_3d(analysis_output):
    chart = scatter_3d(analysis_output)
    assert chart.chart_type == "scatter_3d"
    assert chart.html


def test_cluster_sizes(analysis_output):
    chart = cluster_sizes(analysis_output)
    assert chart.chart_type == "cluster_sizes"
    assert chart.html


def test_feature_boxplots(analysis_output):
    chart = feature_boxplots(analysis_output)
    assert chart.chart_type == "feature_boxplots"
    assert chart.html


def test_correlation_heatmap(analysis_output):
    chart = correlation_heatmap(analysis_output)
    assert chart.chart_type == "correlation_heatmap"
    assert chart.html
    data = json.loads(chart.plotly_json)
    assert data["data"][0]["type"] == "heatmap"


def test_silhouette_plot(analysis_output):
    chart = silhouette_plot(analysis_output)
    assert chart.chart_type == "silhouette"
    assert chart.html


def test_parallel_coordinates(analysis_output):
    chart = parallel_coordinates(analysis_output)
    assert chart.chart_type == "parallel_coordinates"
    assert chart.html


def test_anomaly_overlay(analysis_output):
    chart = anomaly_overlay(analysis_output)
    assert chart.chart_type == "anomaly_overlay"
    assert chart.html


def test_generate_all(analysis_output):
    charts = generate_all(analysis_output)
    assert len(charts) == 8
    chart_types = {c.chart_type for c in charts}
    assert "scatter_2d" in chart_types
    assert "scatter_3d" in chart_types
    assert "cluster_sizes" in chart_types
    assert "correlation_heatmap" in chart_types
    assert "anomaly_overlay" in chart_types

    for chart in charts:
        assert chart.html
        assert chart.plotly_json
        # Verify JSON is valid
        json.loads(chart.plotly_json)
