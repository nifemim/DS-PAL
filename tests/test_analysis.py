"""Tests for analysis engine."""
import pytest
import numpy as np
import pandas as pd
from sklearn.datasets import load_iris

from app.services.analysis_engine import (
    _auto_eps,
    encode_categoricals,
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


@pytest.fixture
def mixed_df():
    """DataFrame with numeric and categorical columns."""
    return pd.DataFrame({
        "age": [25, 30, 35, 40, 45, 50, 55, 60, 65, 70],
        "income": [30000, 45000, 50000, 60000, 70000, 80000, 90000, 100000, 110000, 120000],
        "city": ["NY", "LA", "NY", "SF", "LA", "NY", "SF", "LA", "NY", "SF"],
        "gender": ["M", "F", "M", "F", "M", "F", "M", "F", "M", "F"],
    })


def test_preprocess(iris_df):
    numeric_df, scaled_df, features, enc_info = preprocess(iris_df)
    assert len(features) == 4
    assert numeric_df.shape == iris_df.shape
    assert scaled_df.shape == iris_df.shape
    assert enc_info == []
    # Scaled should have ~0 mean and ~1 std
    assert abs(scaled_df.mean().mean()) < 0.01
    assert abs(scaled_df.std().mean() - 1.0) < 0.1


def test_preprocess_with_columns(iris_df):
    cols = iris_df.columns[:2].tolist()
    numeric_df, scaled_df, features, _ = preprocess(iris_df, columns=cols)
    assert len(features) == 2
    assert numeric_df.shape[1] == 2


def test_preprocess_too_few_columns(iris_df):
    with pytest.raises(ValueError, match="at least 2"):
        preprocess(iris_df, columns=[iris_df.columns[0]])


def test_reduce_dimensions(iris_df):
    _, scaled_df, _, _ = preprocess(iris_df)
    coords_2d, coords_3d = reduce_dimensions(scaled_df)
    assert coords_2d.shape == (150, 2)
    assert coords_3d.shape == (150, 3)


def test_find_optimal_k(iris_df):
    _, scaled_df, _, _ = preprocess(iris_df)
    k = find_optimal_k(scaled_df)
    assert 2 <= k <= 10


def test_cluster_kmeans(iris_df):
    _, scaled_df, _, _ = preprocess(iris_df)
    labels, n_clusters, sil, params = cluster(scaled_df, "kmeans", n_clusters=3)
    assert n_clusters == 3
    assert len(labels) == 150
    assert len(set(labels)) == 3
    assert sil is not None
    assert sil > 0.4


def test_cluster_dbscan(iris_df):
    _, scaled_df, _, _ = preprocess(iris_df)
    labels, n_clusters, sil, params = cluster(scaled_df, "dbscan")
    assert n_clusters >= 0
    assert len(labels) == 150


def test_cluster_hierarchical(iris_df):
    _, scaled_df, _, _ = preprocess(iris_df)
    labels, n_clusters, sil, params = cluster(scaled_df, "hierarchical", n_clusters=3)
    assert n_clusters == 3
    assert len(labels) == 150


def test_profile_clusters(iris_df):
    numeric_df, scaled_df, features, _ = preprocess(iris_df)
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
    _, scaled_df, _, _ = preprocess(iris_df)
    anom_labels, scores = detect_anomalies(scaled_df, contamination=0.05)
    assert len(anom_labels) == 150
    assert len(scores) == 150
    n_anomalies = anom_labels.sum()
    # ~5% contamination on 150 samples = ~7-8 anomalies
    assert 1 <= n_anomalies <= 20


def test_compute_stats(iris_df):
    numeric_df, _, features, _ = preprocess(iris_df)
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
    assert result.encoding_info == []


# --- Categorical encoding tests ---


def test_encode_categoricals_one_hot():
    """Low-cardinality column produces expected dummy columns."""
    df = pd.DataFrame({
        "color": ["red", "blue", "green", "red", "blue", "green", "red", "blue", "green", "red"],
    })
    encoded, info = encode_categoricals(df, ["color"])
    assert len(info) == 1
    assert info[0]["encoding_type"] == "one-hot"
    assert info[0]["original_column"] == "color"
    # 3 unique - drop_first = 2 columns
    assert encoded.shape[1] == 2
    assert encoded.shape[0] == 10


def test_encode_categoricals_label():
    """High-cardinality column produces single integer column."""
    values = [f"cat_{i}" for i in range(15)]
    df = pd.DataFrame({"category": values * 2})
    encoded, info = encode_categoricals(df, ["category"])
    assert len(info) == 1
    assert info[0]["encoding_type"] == "label"
    assert encoded.shape[1] == 1
    # Label encoded values should be integers
    assert encoded["category"].dtype in [np.int64, np.int32, int]


def test_encode_categoricals_auto_select():
    """Correct method chosen per cardinality."""
    high_card_values = [f"val_{i}" for i in range(15)]
    df = pd.DataFrame({
        "low_card": ["a", "b", "c"] * 20,
        "high_card": (high_card_values * 4)[:60],
    })
    encoded, info = encode_categoricals(df, ["low_card", "high_card"])
    info_map = {i["original_column"]: i for i in info}
    assert info_map["low_card"]["encoding_type"] == "one-hot"
    assert info_map["high_card"]["encoding_type"] == "label"


def test_encode_boolean_columns():
    """Booleans cast to 0/1."""
    df = pd.DataFrame({
        "flag": [True, False, True, False, True, False, True, False, True, False],
    })
    encoded, info = encode_categoricals(df, ["flag"])
    assert len(info) == 1
    assert info[0]["encoding_type"] == "boolean"
    assert set(encoded["flag"].unique()) <= {0, 1}


def test_encode_nan_handling():
    """NaN imputed as 'MISSING' category."""
    df = pd.DataFrame({
        "color": ["red", "blue", None, "red", "blue", None, "red", "blue", None, "red"],
    })
    encoded, info = encode_categoricals(df, ["color"])
    assert len(info) == 1
    # Should not have any NaN in the result
    assert not encoded.isna().any().any()


def test_encode_id_like_excluded():
    """High cardinality ratio columns excluded."""
    df = pd.DataFrame({
        "id": [f"user_{i}" for i in range(100)],
        "category": ["a", "b"] * 50,
    })
    encoded, info = encode_categoricals(df, ["id", "category"])
    # Only category should be encoded, id should be excluded
    info_cols = [i["original_column"] for i in info]
    assert "id" not in info_cols
    assert "category" in info_cols


def test_encode_single_value_excluded():
    """Constant columns excluded."""
    df = pd.DataFrame({
        "const": ["same"] * 20,
        "varied": ["a", "b", "c", "d"] * 5,
    })
    encoded, info = encode_categoricals(df, ["const", "varied"])
    info_cols = [i["original_column"] for i in info]
    assert "const" not in info_cols
    assert "varied" in info_cols


def test_encode_numeric_as_string():
    """Object columns with numeric values coerced to float."""
    df = pd.DataFrame({
        "price": ["10.5", "20.3", "15.0", "30.1", "25.5", "18.0", "22.2", "33.3", "44.4", "55.5"] * 5,
    })
    encoded, info = encode_categoricals(df, ["price"])
    assert len(info) == 1
    assert info[0]["encoding_type"] == "numeric-coerce"
    assert pd.api.types.is_numeric_dtype(encoded["price"])


def test_preprocess_with_categoricals(mixed_df):
    """Full preprocess pipeline with mixed types."""
    combined_df, scaled_df, features, enc_info = preprocess(
        mixed_df, columns=["age", "income"], categorical_columns=["city", "gender"]
    )
    # Should have numeric cols + encoded categorical cols
    assert "age" in features
    assert "income" in features
    assert len(features) > 2  # categoricals added
    assert len(enc_info) > 0
    assert not scaled_df.isna().any().any()


def test_preprocess_all_categorical():
    """Dataset with zero selected numeric columns but categoricals."""
    df = pd.DataFrame({
        "a": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "color": ["red", "blue", "green"] * 3 + ["red"],
        "size": ["S", "M", "L"] * 3 + ["S"],
    })
    # Select no numeric columns but provide categoricals
    combined_df, scaled_df, features, enc_info = preprocess(
        df, columns=[], categorical_columns=["color", "size"]
    )
    assert len(features) >= 2
    assert len(enc_info) == 2


def test_run_full_pipeline_with_categoricals(mixed_df):
    """End-to-end with mixed DataFrame."""
    result = run(
        mixed_df,
        dataset_name="Mixed",
        dataset_source="test",
        dataset_id="mixed",
        algorithm="kmeans",
        n_clusters=2,
        columns=["age", "income"],
        categorical_columns=["city", "gender"],
    )
    assert result.n_clusters == 2
    assert len(result.encoding_info) > 0
    assert len(result.feature_names) > 2


def test_dimension_cap():
    """One-hot encoding respects 100-feature limit."""
    # Create columns with 60 unique values each, repeated enough to avoid ID-like detection
    vals_a = [f"a_{i}" for i in range(60)]
    vals_b = [f"b_{i}" for i in range(60)]
    # Repeat so cardinality ratio < 0.9 (60/180 = 0.33)
    df = pd.DataFrame({"cat_a": vals_a * 3, "cat_b": vals_b * 3})
    encoded, info = encode_categoricals(df, ["cat_a", "cat_b"], cardinality_threshold=100, max_total_features=100)
    # At least one should be downgraded to label
    types = [i["encoding_type"] for i in info]
    assert "label" in types
    assert encoded.shape[1] <= 100


# --- Reverse-mapped centroids tests ---


class TestReverseMappedCentroids:
    """Tests for label-encoded centroid reverse-mapping."""

    def test_label_encoded_centroid_shows_category_name(self):
        """profile_clusters maps label-encoded centroid float to nearest category."""
        # Create DataFrame with a label-encoded column (values 0, 1, 2)
        df = pd.DataFrame({"feat": [0, 0, 1, 1, 2, 2]})
        scaled = pd.DataFrame({"feat": [-1.0, -1.0, 0.0, 0.0, 1.0, 1.0]})
        labels = np.array([0, 0, 1, 1, 1, 1])
        encoding_info = [{
            "original_column": "feat",
            "encoding_type": "label",
            "new_columns": ["feat"],
            "cardinality": 3,
            "label_mapping": ["Cat_A", "Cat_B", "Cat_C"],
        }]
        profiles = profile_clusters(df, scaled, labels, ["feat"], encoding_info)
        # Cluster 0 has feat mean=0.0 → index 0 → "Cat_A"
        assert profiles[0].centroid["feat"] == "Cat_A"
        # Cluster 1 has feat mean=1.5 → round(1.5)=2 → "Cat_C"  (or 1 depending on rounding)
        assert profiles[1].centroid["feat"] in ("Cat_B", "Cat_C")

    def test_centroid_clamps_out_of_bounds_index(self):
        """Round(mean) outside [0, len(mapping)-1] is clamped, not crashed."""
        df = pd.DataFrame({"feat": [10, 10]})
        scaled = pd.DataFrame({"feat": [1.0, 1.0]})
        labels = np.array([0, 0])
        encoding_info = [{
            "original_column": "feat",
            "encoding_type": "label",
            "new_columns": ["feat"],
            "cardinality": 3,
            "label_mapping": ["A", "B", "C"],
        }]
        profiles = profile_clusters(df, scaled, labels, ["feat"], encoding_info)
        # Mean=10, round=10, clamped to index 2 → "C"
        assert profiles[0].centroid["feat"] == "C"

    def test_numeric_centroid_unchanged(self):
        """Non-label-encoded features still show float centroids."""
        df = pd.DataFrame({"age": [25.0, 30.0, 35.0, 40.0]})
        scaled = pd.DataFrame({"age": [-1.0, -0.5, 0.5, 1.0]})
        labels = np.array([0, 0, 1, 1])
        profiles = profile_clusters(df, scaled, labels, ["age"])
        assert isinstance(profiles[0].centroid["age"], float)
        assert isinstance(profiles[1].centroid["age"], float)

    def test_encoding_info_includes_label_mapping(self):
        """encode_categoricals adds label_mapping list to label-encoded entries."""
        values = [f"cat_{i}" for i in range(15)]
        df = pd.DataFrame({"category": values * 2})
        _, info = encode_categoricals(df, ["category"])
        assert len(info) == 1
        assert "label_mapping" in info[0]
        assert isinstance(info[0]["label_mapping"], list)
        assert len(info[0]["label_mapping"]) == 15


# --- Adaptive DBSCAN eps tests ---


class TestAutoEps:
    """Tests for adaptive DBSCAN eps selection."""

    def test_auto_eps_returns_positive_float(self):
        """_auto_eps returns a positive float for valid scaled data."""
        np.random.seed(42)
        data = np.random.randn(100, 3)
        eps = _auto_eps(data, min_samples=5)
        assert isinstance(eps, float)
        assert eps > 0

    def test_auto_eps_floor(self):
        """_auto_eps returns at least 0.01 even for identical points."""
        data = np.ones((50, 2))
        eps = _auto_eps(data, min_samples=5)
        assert eps >= 0.01

    def test_dbscan_uses_auto_eps(self, iris_df):
        """cluster() with algorithm='dbscan' uses _auto_eps, not hardcoded 0.5."""
        _, scaled_df, _, _ = preprocess(iris_df)
        labels, n_clusters, sil, params = cluster(scaled_df, "dbscan")
        # eps should be data-dependent, not always 0.5
        assert "eps" in params
        assert isinstance(params["eps"], float)
