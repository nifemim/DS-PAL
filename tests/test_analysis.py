"""Tests for analysis engine."""
import pytest
import numpy as np
import pandas as pd
from sklearn.datasets import load_iris

from app.services.analysis_engine import (
    preprocess,
    reduce_dimensions,
    find_optimal_k,
    cluster,
    profile_clusters,
    detect_anomalies,
    compute_stats,
    run,
)


@pytest.fixture
def iris_df():
    """Load Iris dataset as DataFrame."""
    data = load_iris()
    df = pd.DataFrame(data.data, columns=data.feature_names)
    return df


def test_preprocess(iris_df):
    numeric_df, scaled_df, features = preprocess(iris_df)
    assert len(features) == 4
    assert numeric_df.shape == iris_df.shape
    assert scaled_df.shape == iris_df.shape
    # Scaled should have ~0 mean and ~1 std
    assert abs(scaled_df.mean().mean()) < 0.01
    assert abs(scaled_df.std().mean() - 1.0) < 0.1


def test_preprocess_with_columns(iris_df):
    cols = iris_df.columns[:2].tolist()
    numeric_df, scaled_df, features = preprocess(iris_df, columns=cols)
    assert len(features) == 2
    assert numeric_df.shape[1] == 2


def test_preprocess_too_few_columns(iris_df):
    with pytest.raises(ValueError, match="at least 2"):
        preprocess(iris_df, columns=[iris_df.columns[0]])


def test_reduce_dimensions(iris_df):
    _, scaled_df, _ = preprocess(iris_df)
    coords_2d, coords_3d = reduce_dimensions(scaled_df)
    assert coords_2d.shape == (150, 2)
    assert coords_3d.shape == (150, 3)


def test_find_optimal_k(iris_df):
    _, scaled_df, _ = preprocess(iris_df)
    k = find_optimal_k(scaled_df)
    assert 2 <= k <= 10


def test_cluster_kmeans(iris_df):
    _, scaled_df, _ = preprocess(iris_df)
    labels, n_clusters, sil, params = cluster(scaled_df, "kmeans", n_clusters=3)
    assert n_clusters == 3
    assert len(labels) == 150
    assert len(set(labels)) == 3
    assert sil is not None
    assert sil > 0.4


def test_cluster_dbscan(iris_df):
    _, scaled_df, _ = preprocess(iris_df)
    labels, n_clusters, sil, params = cluster(scaled_df, "dbscan")
    assert n_clusters >= 0
    assert len(labels) == 150


def test_cluster_hierarchical(iris_df):
    _, scaled_df, _ = preprocess(iris_df)
    labels, n_clusters, sil, params = cluster(scaled_df, "hierarchical", n_clusters=3)
    assert n_clusters == 3
    assert len(labels) == 150


def test_profile_clusters(iris_df):
    numeric_df, scaled_df, features = preprocess(iris_df)
    labels, _, _, _ = cluster(scaled_df, "kmeans", n_clusters=3)
    profiles = profile_clusters(numeric_df, scaled_df, labels, features)
    assert len(profiles) == 3
    total_size = sum(p.size for p in profiles)
    assert total_size == 150
    for p in profiles:
        assert p.percentage > 0
        assert len(p.centroid) == 4
        assert len(p.top_features) > 0


def test_detect_anomalies(iris_df):
    _, scaled_df, _ = preprocess(iris_df)
    anom_labels, scores = detect_anomalies(scaled_df, contamination=0.05)
    assert len(anom_labels) == 150
    assert len(scores) == 150
    n_anomalies = anom_labels.sum()
    # ~5% contamination on 150 samples = ~7-8 anomalies
    assert 1 <= n_anomalies <= 20


def test_compute_stats(iris_df):
    numeric_df, _, features = preprocess(iris_df)
    corr, stats = compute_stats(numeric_df, features)
    assert len(corr) == 4
    assert len(stats) == 4
    for feat in features:
        assert "mean" in stats[feat]
        assert "std" in stats[feat]
        assert feat in corr[feat]
        assert corr[feat][feat] == 1.0


def test_run_full_pipeline(iris_df):
    result = run(
        iris_df,
        dataset_name="Iris",
        dataset_source="test",
        dataset_id="iris",
        algorithm="kmeans",
        n_clusters=3,
    )
    assert result.n_clusters == 3
    assert result.silhouette_score is not None
    assert result.silhouette_score > 0.4
    assert len(result.cluster_profiles) == 3
    assert len(result.cluster_labels) == 150
    assert len(result.pca_2d) == 150
    assert len(result.pca_3d) == 150
    assert len(result.anomaly_labels) == 150
    assert len(result.feature_names) == 4
    assert result.algorithm == "kmeans"
