"""ML analysis pipeline: preprocess, cluster, profile, detect anomalies."""
import logging
import math
import uuid
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from app.models.schemas import AnalysisOutput, ClusterProfile

logger = logging.getLogger(__name__)


def preprocess(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """Select numeric columns, handle missing values, scale.

    Returns (original_numeric_df, scaled_df, feature_names).
    """
    if columns:
        numeric_df = df[columns].select_dtypes(include=["number"])
    else:
        numeric_df = df.select_dtypes(include=["number"])

    feature_names = numeric_df.columns.tolist()
    if len(feature_names) < 2:
        raise ValueError(
            f"Need at least 2 numeric columns for analysis, found {len(feature_names)}"
        )

    # Drop columns with >50% NaN
    threshold = len(numeric_df) * 0.5
    numeric_df = numeric_df.dropna(axis=1, thresh=int(threshold))
    feature_names = numeric_df.columns.tolist()

    if len(feature_names) < 2:
        raise ValueError("After dropping columns with >50% missing values, fewer than 2 remain")

    # Drop rows that are entirely NaN, then impute remaining NaNs with median
    numeric_df = numeric_df.dropna(how="all")
    for col in feature_names:
        median_val = numeric_df[col].median()
        numeric_df[col] = numeric_df[col].fillna(median_val)

    # Scale
    scaler = StandardScaler()
    scaled_array = scaler.fit_transform(numeric_df)
    scaled_df = pd.DataFrame(scaled_array, columns=feature_names, index=numeric_df.index)

    return numeric_df, scaled_df, feature_names


def reduce_dimensions(
    scaled_df: pd.DataFrame,
) -> Tuple[np.ndarray, np.ndarray]:
    """PCA to 2D and 3D for visualization."""
    n_features = scaled_df.shape[1]
    values = scaled_df.values

    pca_2d = PCA(n_components=min(2, n_features))
    coords_2d = pca_2d.fit_transform(values)

    pca_3d = PCA(n_components=min(3, n_features))
    coords_3d = pca_3d.fit_transform(values)

    return coords_2d, coords_3d


def find_optimal_k(scaled_df: pd.DataFrame) -> int:
    """Find optimal number of clusters via silhouette score sweep."""
    n = len(scaled_df)
    max_k = min(10, int(math.sqrt(n)))
    max_k = max(max_k, 3)  # At least try up to k=3

    best_k = 2
    best_score = -1.0

    for k in range(2, max_k + 1):
        try:
            km = KMeans(n_clusters=k, n_init=10, random_state=42)
            labels = km.fit_predict(scaled_df.values)
            if len(set(labels)) < 2:
                continue
            score = silhouette_score(scaled_df.values, labels)
            if score > best_score:
                best_score = score
                best_k = k
        except Exception:
            continue

    logger.info("Optimal k=%d (silhouette=%.3f)", best_k, best_score)
    return best_k


def cluster(
    scaled_df: pd.DataFrame,
    algorithm: str = "kmeans",
    n_clusters: Optional[int] = None,
) -> Tuple[np.ndarray, int, Optional[float], Dict[str, Any]]:
    """Run clustering. Returns (labels, n_clusters, silhouette, params)."""
    values = scaled_df.values

    if algorithm == "kmeans":
        if n_clusters is None:
            n_clusters = find_optimal_k(scaled_df)
        model = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
        labels = model.fit_predict(values)
        params = {"n_clusters": n_clusters, "n_init": 10}

    elif algorithm == "dbscan":
        model = DBSCAN(eps=0.5, min_samples=max(5, len(values) // 100))
        labels = model.fit_predict(values)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        params = {"eps": 0.5, "min_samples": model.min_samples}

    elif algorithm == "hierarchical":
        if n_clusters is None:
            n_clusters = find_optimal_k(scaled_df)
        model = AgglomerativeClustering(n_clusters=n_clusters)
        labels = model.fit_predict(values)
        params = {"n_clusters": n_clusters, "linkage": "ward"}

    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    # Compute silhouette if we have valid clusters
    unique_labels = set(labels)
    unique_labels.discard(-1)
    sil_score = None
    if len(unique_labels) >= 2:
        # Only use non-noise points for silhouette
        mask = labels != -1
        if mask.sum() > len(unique_labels):
            sil_score = float(silhouette_score(values[mask], labels[mask]))

    logger.info(
        "%s produced %d clusters (silhouette=%.3f)",
        algorithm, n_clusters, sil_score or 0,
    )
    return labels, n_clusters, sil_score, params


def profile_clusters(
    numeric_df: pd.DataFrame,
    scaled_df: pd.DataFrame,
    labels: np.ndarray,
    feature_names: List[str],
) -> List[ClusterProfile]:
    """Generate per-cluster profiles."""
    profiles = []
    unique_labels = sorted(set(labels))
    total = len(labels)

    for cluster_id in unique_labels:
        mask = labels == cluster_id
        size = int(mask.sum())
        percentage = round(size / total * 100, 1)

        # Centroid in original space
        cluster_data = numeric_df.loc[mask]
        centroid = {}
        for col in feature_names:
            centroid[col] = round(float(cluster_data[col].mean()), 4)

        # Top distinguishing features: z-score deviation from overall mean
        cluster_scaled = scaled_df.loc[mask]
        overall_mean = scaled_df.mean()
        cluster_mean = cluster_scaled.mean()
        deviation = (cluster_mean - overall_mean).abs().sort_values(ascending=False)

        top_features = []
        for feat in deviation.head(5).index:
            top_features.append({
                "feature": feat,
                "cluster_mean": round(float(cluster_data[feat].mean()), 4),
                "overall_mean": round(float(numeric_df[feat].mean()), 4),
                "z_deviation": round(float(deviation[feat]), 4),
            })

        profiles.append(ClusterProfile(
            cluster_id=int(cluster_id),
            size=size,
            percentage=percentage,
            centroid=centroid,
            top_features=top_features,
        ))

    return profiles


def detect_anomalies(
    scaled_df: pd.DataFrame,
    contamination: float = 0.05,
) -> Tuple[np.ndarray, np.ndarray]:
    """Detect anomalies using Isolation Forest. Returns (labels, scores)."""
    model = IsolationForest(contamination=contamination, random_state=42)
    labels = model.fit_predict(scaled_df.values)
    scores = model.decision_function(scaled_df.values)
    # Convert labels: -1 (anomaly) → 1, 1 (normal) → 0
    anomaly_labels = (labels == -1).astype(int)
    n_anomalies = int(anomaly_labels.sum())
    logger.info("Found %d anomalies (%.1f%%)", n_anomalies, n_anomalies / len(labels) * 100)
    return anomaly_labels, scores


def compute_stats(
    numeric_df: pd.DataFrame,
    feature_names: List[str],
) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, Any]]]:
    """Compute correlation matrix and per-column statistics."""
    # Correlation matrix
    corr = numeric_df[feature_names].corr()
    corr_dict = {}
    for col in corr.columns:
        corr_dict[col] = {
            row: round(float(corr.loc[row, col]), 4)
            for row in corr.index
        }

    # Per-column stats
    column_stats = {}
    for col in feature_names:
        series = numeric_df[col]
        column_stats[col] = {
            "mean": round(float(series.mean()), 4),
            "std": round(float(series.std()), 4),
            "min": round(float(series.min()), 4),
            "max": round(float(series.max()), 4),
            "median": round(float(series.median()), 4),
            "q25": round(float(series.quantile(0.25)), 4),
            "q75": round(float(series.quantile(0.75)), 4),
        }

    return corr_dict, column_stats


def run(
    df: pd.DataFrame,
    dataset_name: str,
    dataset_source: str,
    dataset_id: str,
    dataset_url: str = "",
    algorithm: str = "kmeans",
    n_clusters: Optional[int] = None,
    columns: Optional[List[str]] = None,
    contamination: float = 0.05,
) -> AnalysisOutput:
    """Run the full analysis pipeline."""
    analysis_id = str(uuid.uuid4())

    # 1. Preprocess
    numeric_df, scaled_df, feature_names = preprocess(df, columns)
    logger.info("Preprocessed: %d rows x %d features", len(numeric_df), len(feature_names))

    # 2. PCA
    coords_2d, coords_3d = reduce_dimensions(scaled_df)

    # 3. Cluster
    labels, n_clust, sil_score, params = cluster(scaled_df, algorithm, n_clusters)

    # 4. Profile clusters
    profiles = profile_clusters(numeric_df, scaled_df, labels, feature_names)

    # 5. Anomaly detection
    anomaly_labels, anomaly_scores = detect_anomalies(scaled_df, contamination)

    # 6. Statistics
    corr_matrix, col_stats = compute_stats(numeric_df, feature_names)

    title = f"{algorithm.upper()} Analysis of {dataset_name}"

    return AnalysisOutput(
        id=analysis_id,
        title=title,
        dataset_source=dataset_source,
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        dataset_url=dataset_url,
        num_rows=len(numeric_df),
        num_columns=len(feature_names),
        column_names=df.columns.tolist(),
        algorithm=algorithm,
        params=params,
        n_clusters=n_clust,
        silhouette_score=sil_score,
        cluster_profiles=profiles,
        cluster_labels=labels.tolist(),
        pca_2d=coords_2d.tolist(),
        pca_3d=coords_3d.tolist(),
        anomaly_labels=anomaly_labels.tolist(),
        anomaly_scores=anomaly_scores.tolist(),
        correlation_matrix=corr_matrix,
        column_stats=col_stats,
        feature_names=feature_names,
    )
