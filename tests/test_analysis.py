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
    EncodingResult,
    PreprocessResult,
)
from app.services.visualization import feature_distributions, generate_all


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
    prep = preprocess(iris_df)
    assert isinstance(prep, PreprocessResult)
    assert len(prep.feature_names) == 4
    assert prep.numeric_df.shape == iris_df.shape
    assert prep.scaled_df.shape == iris_df.shape
    assert prep.encoding_info == []
    # Scaled should have ~0 mean and ~1 std
    assert abs(prep.scaled_df.mean().mean()) < 0.01
    assert abs(prep.scaled_df.std().mean() - 1.0) < 0.1


def test_preprocess_with_columns(iris_df):
    cols = iris_df.columns[:2].tolist()
    prep = preprocess(iris_df, columns=cols)
    assert len(prep.feature_names) == 2
    assert prep.numeric_df.shape[1] == 2


def test_preprocess_too_few_columns(iris_df):
    with pytest.raises(ValueError, match="at least 2"):
        preprocess(iris_df, columns=[iris_df.columns[0]])


def test_reduce_dimensions(iris_df):
    prep = preprocess(iris_df)
    coords_2d, coords_3d = reduce_dimensions(prep.scaled_df)
    assert coords_2d.shape == (150, 2)
    assert coords_3d.shape == (150, 3)


def test_find_optimal_k(iris_df):
    prep = preprocess(iris_df)
    k = find_optimal_k(prep.scaled_df)
    assert 2 <= k <= 10


def test_cluster_kmeans(iris_df):
    prep = preprocess(iris_df)
    labels, n_clusters, sil, params = cluster(prep.scaled_df, "kmeans", n_clusters=3)
    assert n_clusters == 3
    assert len(labels) == 150
    assert len(set(labels)) == 3
    assert sil is not None
    assert sil > 0.4


def test_cluster_dbscan(iris_df):
    prep = preprocess(iris_df)
    labels, n_clusters, sil, params = cluster(prep.scaled_df, "dbscan")
    assert n_clusters >= 0
    assert len(labels) == 150


def test_cluster_hierarchical(iris_df):
    prep = preprocess(iris_df)
    labels, n_clusters, sil, params = cluster(prep.scaled_df, "hierarchical", n_clusters=3)
    assert n_clusters == 3
    assert len(labels) == 150


def test_profile_clusters(iris_df):
    prep = preprocess(iris_df)
    labels, _, _, _ = cluster(prep.scaled_df, "kmeans", n_clusters=3)
    profiles = profile_clusters(prep.numeric_df, prep.scaled_df, labels, prep.feature_names)
    assert len(profiles) == 3
    total_size = sum(p.size for p in profiles)
    assert total_size == 150
    for p in profiles:
        assert p.percentage > 0
        assert len(p.centroid) == 4
        assert len(p.top_features) > 0


def test_detect_anomalies(iris_df):
    prep = preprocess(iris_df)
    anom_labels, scores = detect_anomalies(prep.scaled_df, contamination=0.05)
    assert len(anom_labels) == 150
    assert len(scores) == 150
    n_anomalies = anom_labels.sum()
    # ~5% contamination on 150 samples = ~7-8 anomalies
    assert 1 <= n_anomalies <= 20


def test_compute_stats(iris_df):
    prep = preprocess(iris_df)
    corr, stats = compute_stats(prep.numeric_df, prep.feature_names)
    assert len(corr) == 4
    assert len(stats) == 4
    for feat in prep.feature_names:
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
    # New fields
    assert result.original_column_count == 4
    assert isinstance(result.missing_values, dict)
    assert isinstance(result.dropped_columns, list)


# --- Categorical encoding tests ---


def test_encode_categoricals_one_hot():
    """Low-cardinality column produces expected dummy columns."""
    df = pd.DataFrame({
        "color": ["red", "blue", "green", "red", "blue", "green", "red", "blue", "green", "red"],
    })
    enc_result = encode_categoricals(df, ["color"])
    assert isinstance(enc_result, EncodingResult)
    assert len(enc_result.encoding_info) == 1
    assert enc_result.encoding_info[0]["encoding_type"] == "one-hot"
    assert enc_result.encoding_info[0]["original_column"] == "color"
    # 3 unique - drop_first = 2 columns
    assert enc_result.encoded_df.shape[1] == 2
    assert enc_result.encoded_df.shape[0] == 10


def test_encode_categoricals_label():
    """High-cardinality column produces single integer column."""
    values = [f"cat_{i}" for i in range(15)]
    df = pd.DataFrame({"category": values * 2})
    enc_result = encode_categoricals(df, ["category"])
    assert len(enc_result.encoding_info) == 1
    assert enc_result.encoding_info[0]["encoding_type"] == "label"
    assert enc_result.encoded_df.shape[1] == 1
    # Label encoded values should be integers
    assert enc_result.encoded_df["category"].dtype in [np.int64, np.int32, int]


def test_encode_categoricals_auto_select():
    """Correct method chosen per cardinality."""
    high_card_values = [f"val_{i}" for i in range(15)]
    df = pd.DataFrame({
        "low_card": ["a", "b", "c"] * 20,
        "high_card": (high_card_values * 4)[:60],
    })
    enc_result = encode_categoricals(df, ["low_card", "high_card"])
    info_map = {i["original_column"]: i for i in enc_result.encoding_info}
    assert info_map["low_card"]["encoding_type"] == "one-hot"
    assert info_map["high_card"]["encoding_type"] == "label"


def test_encode_boolean_columns():
    """Booleans cast to 0/1."""
    df = pd.DataFrame({
        "flag": [True, False, True, False, True, False, True, False, True, False],
    })
    enc_result = encode_categoricals(df, ["flag"])
    assert len(enc_result.encoding_info) == 1
    assert enc_result.encoding_info[0]["encoding_type"] == "boolean"
    assert set(enc_result.encoded_df["flag"].unique()) <= {0, 1}


def test_encode_nan_handling():
    """NaN imputed as 'MISSING' category."""
    df = pd.DataFrame({
        "color": ["red", "blue", None, "red", "blue", None, "red", "blue", None, "red"],
    })
    enc_result = encode_categoricals(df, ["color"])
    assert len(enc_result.encoding_info) == 1
    # Should not have any NaN in the result
    assert not enc_result.encoded_df.isna().any().any()


def test_encode_id_like_excluded():
    """High cardinality ratio columns excluded."""
    df = pd.DataFrame({
        "id": [f"user_{i}" for i in range(100)],
        "category": ["a", "b"] * 50,
    })
    enc_result = encode_categoricals(df, ["id", "category"])
    # Only category should be encoded, id should be excluded
    info_cols = [i["original_column"] for i in enc_result.encoding_info]
    assert "id" not in info_cols
    assert "category" in info_cols
    # id should appear in skipped_columns
    skipped_cols = [s["column"] for s in enc_result.skipped_columns]
    assert "id" in skipped_cols


def test_encode_single_value_excluded():
    """Constant columns excluded."""
    df = pd.DataFrame({
        "const": ["same"] * 20,
        "varied": ["a", "b", "c", "d"] * 5,
    })
    enc_result = encode_categoricals(df, ["const", "varied"])
    info_cols = [i["original_column"] for i in enc_result.encoding_info]
    assert "const" not in info_cols
    assert "varied" in info_cols
    # const should appear in skipped_columns
    skipped_cols = [s["column"] for s in enc_result.skipped_columns]
    assert "const" in skipped_cols


def test_encode_numeric_as_string():
    """Object columns with numeric values coerced to float."""
    df = pd.DataFrame({
        "price": ["10.5", "20.3", "15.0", "30.1", "25.5", "18.0", "22.2", "33.3", "44.4", "55.5"] * 5,
    })
    enc_result = encode_categoricals(df, ["price"])
    assert len(enc_result.encoding_info) == 1
    assert enc_result.encoding_info[0]["encoding_type"] == "numeric-coerce"
    assert pd.api.types.is_numeric_dtype(enc_result.encoded_df["price"])


def test_preprocess_with_categoricals(mixed_df):
    """Full preprocess pipeline with mixed types."""
    prep = preprocess(
        mixed_df, columns=["age", "income"], categorical_columns=["city", "gender"]
    )
    # Should have numeric cols + encoded categorical cols
    assert "age" in prep.feature_names
    assert "income" in prep.feature_names
    assert len(prep.feature_names) > 2  # categoricals added
    assert len(prep.encoding_info) > 0
    assert not prep.scaled_df.isna().any().any()


def test_preprocess_all_categorical():
    """Dataset with zero selected numeric columns but categoricals."""
    df = pd.DataFrame({
        "a": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "color": ["red", "blue", "green"] * 3 + ["red"],
        "size": ["S", "M", "L"] * 3 + ["S"],
    })
    # Select no numeric columns but provide categoricals
    prep = preprocess(
        df, columns=[], categorical_columns=["color", "size"]
    )
    assert len(prep.feature_names) >= 2
    assert len(prep.encoding_info) == 2


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
    enc_result = encode_categoricals(df, ["cat_a", "cat_b"], cardinality_threshold=100, max_total_features=100)
    # At least one should be downgraded to label
    types = [i["encoding_type"] for i in enc_result.encoding_info]
    assert "label" in types
    assert enc_result.encoded_df.shape[1] <= 100


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
        enc_result = encode_categoricals(df, ["category"])
        assert len(enc_result.encoding_info) == 1
        assert "label_mapping" in enc_result.encoding_info[0]
        assert isinstance(enc_result.encoding_info[0]["label_mapping"], list)
        assert len(enc_result.encoding_info[0]["label_mapping"]) == 15


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
        prep = preprocess(iris_df)
        labels, n_clusters, sil, params = cluster(prep.scaled_df, "dbscan")
        # eps should be data-dependent, not always 0.5
        assert "eps" in params
        assert isinstance(params["eps"], float)


# --- New: PreprocessResult and EncodingResult dataclass tests ---


class TestPreprocessResult:
    """Tests for PreprocessResult dataclass."""

    def test_preprocess_returns_dataclass(self, iris_df):
        """preprocess() returns PreprocessResult with named fields."""
        prep = preprocess(iris_df)
        assert isinstance(prep, PreprocessResult)
        assert hasattr(prep, "numeric_df")
        assert hasattr(prep, "scaled_df")
        assert hasattr(prep, "feature_names")
        assert hasattr(prep, "encoding_info")
        assert hasattr(prep, "dropped_columns")

    def test_dropped_columns_reported(self):
        """PreprocessResult includes dropped column info for >50% NaN columns."""
        df = pd.DataFrame({
            "good": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "mostly_nan": [1.0, None, None, None, None, None, None, None, None, None],
            "also_good": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0],
        })
        prep = preprocess(df)
        dropped_names = [d["column"] for d in prep.dropped_columns]
        assert "mostly_nan" in dropped_names

    def test_encoding_result_skipped_columns(self):
        """EncodingResult includes skipped_columns for ID-like and constant columns."""
        df = pd.DataFrame({
            "id": [f"user_{i}" for i in range(100)],
            "const": ["same"] * 100,
            "category": ["a", "b"] * 50,
        })
        enc_result = encode_categoricals(df, ["id", "const", "category"])
        assert isinstance(enc_result, EncodingResult)
        skipped_names = [s["column"] for s in enc_result.skipped_columns]
        assert "id" in skipped_names
        assert "const" in skipped_names
        assert "category" not in skipped_names


class TestMissingValues:
    """Tests for missing_values computation in run()."""

    def test_missing_values_computed(self):
        """run() populates missing_values field from pre-imputation DataFrame."""
        df = pd.DataFrame({
            "a": [1.0, 2.0, None, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "b": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0],
        })
        result = run(df, dataset_name="test", dataset_source="test", dataset_id="test")
        assert "a" in result.missing_values
        assert result.missing_values["a"] == 1
        assert "b" not in result.missing_values

    def test_no_missing_values(self, iris_df):
        """Iris dataset has no missing values — dict should be empty."""
        result = run(iris_df, dataset_name="Iris", dataset_source="test", dataset_id="iris")
        assert result.missing_values == {}

    def test_original_column_count(self, iris_df):
        """run() sets original_column_count to number of columns in raw DataFrame."""
        result = run(iris_df, dataset_name="Iris", dataset_source="test", dataset_id="iris")
        assert result.original_column_count == 4


class TestFeatureDistributions:
    """Tests for the feature_distributions chart generator."""

    def test_feature_distributions_generated(self, iris_df):
        """New chart type included in generate_all output."""
        result = run(iris_df, dataset_name="Iris", dataset_source="test", dataset_id="iris")
        charts = generate_all(result)
        chart_types = [c.chart_type for c in charts]
        assert "feature_distributions" in chart_types

    def test_feature_distributions_chart(self, iris_df):
        """feature_distributions produces a valid ChartData."""
        result = run(iris_df, dataset_name="Iris", dataset_source="test", dataset_id="iris")
        chart = feature_distributions(result)
        assert chart.chart_type == "feature_distributions"
        assert chart.title == "Feature Distributions"
        assert len(chart.html) > 0
        assert len(chart.plotly_json) > 0

    def test_feature_distributions_empty_stats(self):
        """feature_distributions handles missing column_stats gracefully."""
        from app.models.schemas import AnalysisOutput
        # Minimal AnalysisOutput with empty column_stats
        analysis = AnalysisOutput(
            id="test",
            title="Test",
            dataset_source="test",
            dataset_id="test",
            dataset_name="Test",
            num_rows=10,
            num_columns=2,
            column_names=["a", "b"],
            algorithm="kmeans",
            n_clusters=2,
            cluster_profiles=[],
            cluster_labels=[0] * 10,
            feature_names=["a", "b"],
            column_stats={},
        )
        chart = feature_distributions(analysis)
        assert chart.chart_type == "feature_distributions"

    def test_generate_all_produces_9_charts(self, iris_df):
        """generate_all produces 9 charts (8 existing + feature_distributions)."""
        result = run(iris_df, dataset_name="Iris", dataset_source="test", dataset_id="iris")
        charts = generate_all(result)
        assert len(charts) == 9
