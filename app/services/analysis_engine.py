"""ML analysis pipeline: preprocess, cluster, profile, detect anomalies."""
import logging
import math
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple

from app.models.schemas import AnalysisOutput, ClusterProfile, DroppedColumn

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EncodingResult:
    """Result of categorical encoding."""
    encoded_df: object  # pd.DataFrame
    encoding_info: list
    skipped_columns: list


@dataclass(frozen=True)
class PreprocessResult:
    """Result of the full preprocessing pipeline."""
    numeric_df: object  # pd.DataFrame
    scaled_df: object  # pd.DataFrame
    feature_names: list
    encoding_info: list
    dropped_columns: list


def encode_categoricals(
    df,
    categorical_columns: List[str],
    cardinality_threshold: int = 10,
    max_total_features: int = 100,
) -> EncodingResult:
    """Encode categorical columns. Returns EncodingResult with encoded DataFrame, metadata, and skipped columns."""
    import pandas as pd
    from sklearn.preprocessing import LabelEncoder
    if not categorical_columns:
        return EncodingResult(encoded_df=pd.DataFrame(index=df.index), encoding_info=[], skipped_columns=[])

    encoding_info = []
    encoded_parts = []
    skipped_columns = []

    # Filter to columns that actually exist in the DataFrame
    cat_cols = [c for c in categorical_columns if c in df.columns]
    if not cat_cols:
        return EncodingResult(encoded_df=pd.DataFrame(index=df.index), encoding_info=[], skipped_columns=[])

    cat_df = df[cat_cols].copy()

    # Drop columns with >50% NaN
    threshold = len(cat_df) * 0.5
    valid_cols = [c for c in cat_df.columns if cat_df[c].count() >= threshold]
    cat_df = cat_df[valid_cols]

    # Process each column
    one_hot_candidates = []  # (col_name, cardinality)

    for col in cat_df.columns:
        series = cat_df[col]
        dtype = series.dtype
        non_null = series.dropna()
        nunique = int(non_null.nunique())

        # Skip single-value columns
        if nunique <= 1:
            logger.info("Skipping constant column: %s", col)
            skipped_columns.append({"column": col, "reason": "Single value"})
            continue

        # Skip ID-like columns (cardinality ratio > 0.9)
        cardinality_ratio = nunique / len(df) if len(df) > 0 else 0
        if cardinality_ratio > 0.9:
            logger.info("Skipping ID-like column: %s (ratio=%.2f)", col, cardinality_ratio)
            skipped_columns.append({"column": col, "reason": f"ID-like ({nunique} unique values)"})
            continue

        # Boolean columns: cast to int
        if dtype == bool or (dtype == object and set(non_null.unique()) <= {True, False}):
            encoded = series.map({True: 1, False: 0, "True": 1, "False": 0}).fillna(0).astype(int)
            encoded_parts.append(encoded.to_frame())
            encoding_info.append({
                "original_column": col,
                "encoding_type": "boolean",
                "new_columns": [col],
                "cardinality": 2,
            })
            continue

        # Datetime columns: extract temporal components
        is_datetime = pd.api.types.is_datetime64_any_dtype(dtype)
        if not is_datetime and dtype == object and len(non_null) > 0:
            parsed = pd.to_datetime(non_null, errors="coerce")
            if parsed.notna().sum() / len(non_null) > 0.5:
                is_datetime = True
                series = pd.to_datetime(series, errors="coerce")

        if is_datetime:
            parts = pd.DataFrame(index=series.index)
            dt = series.dt
            parts[f"{col}_month"] = dt.month.fillna(0).astype(int)
            parts[f"{col}_day_of_week"] = dt.dayofweek.fillna(0).astype(int)
            if dt.hour.sum() > 0:  # Only include hour if times are present
                parts[f"{col}_hour"] = dt.hour.fillna(0).astype(int)
            encoded_parts.append(parts)
            encoding_info.append({
                "original_column": col,
                "encoding_type": "datetime",
                "new_columns": parts.columns.tolist(),
                "cardinality": nunique,
            })
            continue

        # Numeric-as-string: coerce to float
        if dtype == object:
            coerced = pd.to_numeric(non_null, errors="coerce")
            numeric_ratio = coerced.notna().sum() / len(non_null) if len(non_null) > 0 else 0
            if numeric_ratio > 0.8:
                encoded = pd.to_numeric(series, errors="coerce")
                median_val = encoded.median()
                encoded = encoded.fillna(median_val)
                encoded_parts.append(encoded.to_frame())
                encoding_info.append({
                    "original_column": col,
                    "encoding_type": "numeric-coerce",
                    "new_columns": [col],
                    "cardinality": nunique,
                })
                continue

        # Impute NaN with "MISSING" sentinel
        series = series.fillna("MISSING")

        # Decide encoding method
        if nunique <= cardinality_threshold:
            one_hot_candidates.append((col, nunique, series))
        else:
            # Label encoding
            le = LabelEncoder()
            encoded = pd.Series(le.fit_transform(series.astype(str)), index=series.index, name=col)
            encoded_parts.append(encoded.to_frame())
            encoding_info.append({
                "original_column": col,
                "encoding_type": "label",
                "new_columns": [col],
                "cardinality": nunique,
                "label_mapping": list(le.classes_),
            })

    # Process one-hot candidates, respecting the feature cap
    # Count features so far
    current_features = sum(part.shape[1] for part in encoded_parts)

    # Sort one-hot candidates by cardinality descending (downgrade highest first if needed)
    one_hot_candidates.sort(key=lambda x: x[1], reverse=True)

    for col, nunique, series in one_hot_candidates:
        # Estimate new columns from one-hot: nunique - 1 (drop_first)
        new_cols = nunique - 1
        if current_features + new_cols > max_total_features:
            # Fall back to label encoding
            logger.info("Downgrading %s from one-hot to label (would exceed %d features)", col, max_total_features)
            le = LabelEncoder()
            encoded = pd.Series(le.fit_transform(series.astype(str)), index=series.index, name=col)
            encoded_parts.append(encoded.to_frame())
            encoding_info.append({
                "original_column": col,
                "encoding_type": "label",
                "new_columns": [col],
                "cardinality": nunique,
                "label_mapping": list(le.classes_),
            })
            current_features += 1
        else:
            dummies = pd.get_dummies(series.astype(str), prefix=col, drop_first=True).astype(int)
            encoded_parts.append(dummies)
            encoding_info.append({
                "original_column": col,
                "encoding_type": "one-hot",
                "new_columns": dummies.columns.tolist(),
                "cardinality": nunique,
            })
            current_features += dummies.shape[1]

    if not encoded_parts:
        return EncodingResult(encoded_df=pd.DataFrame(index=df.index), encoding_info=encoding_info, skipped_columns=skipped_columns)

    result = pd.concat(encoded_parts, axis=1)
    return EncodingResult(encoded_df=result, encoding_info=encoding_info, skipped_columns=skipped_columns)


def preprocess(
    df,
    columns: Optional[List[str]] = None,
    categorical_columns: Optional[List[str]] = None,
) -> PreprocessResult:
    """Select numeric columns, encode categoricals, handle missing values, scale.

    Returns PreprocessResult with numeric_df, scaled_df, feature_names, encoding_info, dropped_columns.
    """
    import pandas as pd
    from sklearn.preprocessing import StandardScaler
    dropped_columns: List[Dict[str, str]] = []

    # Numeric pipeline
    if columns is not None:
        numeric_df = df[columns].select_dtypes(include=["number"]) if columns else pd.DataFrame(index=df.index)
    else:
        numeric_df = df.select_dtypes(include=["number"])

    # Drop columns with >90% NaN
    threshold = len(numeric_df) * 0.1
    for col in numeric_df.columns:
        if numeric_df[col].count() < threshold:
            dropped_columns.append({"column": col, "reason": "Over 90% missing values"})
    numeric_df = numeric_df.dropna(axis=1, thresh=int(threshold))

    # Drop rows that are entirely NaN, then impute remaining NaNs with median
    if not numeric_df.columns.empty:
        numeric_df = numeric_df.dropna(how="all")
    numeric_features = numeric_df.columns.tolist()
    for col in numeric_features:
        median_val = numeric_df[col].median()
        numeric_df[col] = numeric_df[col].fillna(median_val)

    # Categorical pipeline
    encoding_info: List[Dict[str, Any]] = []
    if categorical_columns:
        enc_result = encode_categoricals(df.loc[numeric_df.index], categorical_columns)
        encoding_info = enc_result.encoding_info
        dropped_columns.extend(enc_result.skipped_columns)
        if not enc_result.encoded_df.empty:
            combined_df = pd.concat([numeric_df, enc_result.encoded_df], axis=1)
        else:
            combined_df = numeric_df
    else:
        combined_df = numeric_df

    # Drop zero-variance columns post-encoding
    variances = combined_df.var()
    zero_var_cols = variances[variances == 0].index.tolist()
    if zero_var_cols:
        logger.info("Dropping zero-variance columns: %s", zero_var_cols)
        for col in zero_var_cols:
            dropped_columns.append({"column": col, "reason": "Zero variance"})
        combined_df = combined_df.drop(columns=zero_var_cols)

    feature_names = combined_df.columns.tolist()
    if len(feature_names) < 2:
        dropped_desc = ", ".join(f"{d['column']} ({d['reason']})" for d in dropped_columns)
        hint = f" Dropped: {dropped_desc}." if dropped_columns else ""
        raise ValueError(
            f"Need at least 2 features for analysis, found {len(feature_names)}.{hint} "
            f"Try selecting more columns or a different dataset."
        )

    # Scale
    scaler = StandardScaler()
    scaled_array = scaler.fit_transform(combined_df)
    scaled_df = pd.DataFrame(scaled_array, columns=feature_names, index=combined_df.index)

    return PreprocessResult(
        numeric_df=combined_df,
        scaled_df=scaled_df,
        feature_names=feature_names,
        encoding_info=encoding_info,
        dropped_columns=dropped_columns,
    )


def reduce_dimensions(
    scaled_df,
) -> Tuple:
    """PCA to 2D and 3D for visualization."""
    import numpy as np
    from sklearn.decomposition import PCA
    n_features = scaled_df.shape[1]
    values = scaled_df.values

    pca_2d = PCA(n_components=min(2, n_features))
    coords_2d = pca_2d.fit_transform(values)

    pca_3d = PCA(n_components=min(3, n_features))
    coords_3d = pca_3d.fit_transform(values)

    return coords_2d, coords_3d


def find_optimal_k(scaled_df) -> int:
    """Find optimal number of clusters via silhouette score sweep."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
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


def _auto_eps(scaled_data, min_samples: int) -> float:
    """Auto-select DBSCAN eps using median k-nearest-neighbor distance."""
    import numpy as np
    from sklearn.neighbors import NearestNeighbors

    k = min(min_samples, len(scaled_data) - 1)
    nn = NearestNeighbors(n_neighbors=k)
    nn.fit(scaled_data)
    distances, _ = nn.kneighbors(scaled_data)
    eps = float(np.median(distances[:, -1]))
    eps = max(eps, 0.01)
    logger.info("Auto-selected DBSCAN eps=%.4f (median %d-NN distance)", eps, k)
    return eps


def cluster(
    scaled_df,
    algorithm: str = "kmeans",
    n_clusters: Optional[int] = None,
) -> Tuple:
    """Run clustering. Returns (labels, n_clusters, silhouette, params)."""
    from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
    from sklearn.metrics import silhouette_score
    values = scaled_df.values

    if algorithm == "kmeans":
        if n_clusters is None:
            n_clusters = find_optimal_k(scaled_df)
        model = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
        labels = model.fit_predict(values)
        params = {"n_clusters": n_clusters, "n_init": 10}

    elif algorithm == "dbscan":
        min_samples = max(5, len(values) // 100)
        eps = _auto_eps(values, min_samples)
        model = DBSCAN(eps=eps, min_samples=min_samples)
        labels = model.fit_predict(values)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        params = {"eps": round(eps, 4), "min_samples": min_samples}

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
    numeric_df,
    scaled_df,
    labels,
    feature_names: List[str],
    encoding_info: Optional[List[Dict[str, Any]]] = None,
) -> List[ClusterProfile]:
    """Generate per-cluster profiles."""
    # Build lookup: {encoded_column_name: ["cat_a", "cat_b", ...]}
    label_maps = {}
    for enc in (encoding_info or []):
        if enc["encoding_type"] == "label" and "label_mapping" in enc:
            label_maps[enc["original_column"]] = enc["label_mapping"]

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
            raw_mean = round(float(cluster_data[col].mean()), 4)
            if col in label_maps:
                mapping = label_maps[col]
                idx = max(0, min(round(raw_mean), len(mapping) - 1))
                centroid[col] = mapping[idx]
            else:
                centroid[col] = raw_mean

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
    scaled_df,
    contamination: float = 0.05,
) -> Tuple:
    """Detect anomalies using Isolation Forest. Returns (labels, scores)."""
    import numpy as np
    from sklearn.ensemble import IsolationForest
    model = IsolationForest(contamination=contamination, random_state=42)
    labels = model.fit_predict(scaled_df.values)
    scores = model.decision_function(scaled_df.values)
    # Convert labels: -1 (anomaly) → 1, 1 (normal) → 0
    anomaly_labels = (labels == -1).astype(int)
    n_anomalies = int(anomaly_labels.sum())
    logger.info("Found %d anomalies (%.1f%%)", n_anomalies, n_anomalies / len(labels) * 100)
    return anomaly_labels, scores


def compute_stats(
    numeric_df,
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
    df,
    dataset_name: str,
    dataset_source: str,
    dataset_id: str,
    dataset_url: str = "",
    algorithm: str = "kmeans",
    n_clusters: Optional[int] = None,
    columns: Optional[List[str]] = None,
    categorical_columns: Optional[List[str]] = None,
    contamination: float = 0.05,
) -> AnalysisOutput:
    """Run the full analysis pipeline."""
    analysis_id = str(uuid.uuid4())

    # Compute missing values BEFORE preprocessing
    missing_values = {
        col: count
        for col in df.columns
        if (count := int(df[col].isna().sum())) > 0
    }
    original_column_count = len(df.columns)

    # 1. Preprocess
    prep = preprocess(df, columns, categorical_columns)
    logger.info("Preprocessed: %d rows x %d features", len(prep.numeric_df), len(prep.feature_names))

    # 2. PCA
    coords_2d, coords_3d = reduce_dimensions(prep.scaled_df)

    # 3. Cluster
    labels, n_clust, sil_score, params = cluster(prep.scaled_df, algorithm, n_clusters)

    # 4. Profile clusters
    profiles = profile_clusters(prep.numeric_df, prep.scaled_df, labels, prep.feature_names, prep.encoding_info)

    # 5. Anomaly detection
    anomaly_labels, anomaly_scores = detect_anomalies(prep.scaled_df, contamination)

    # 6. Statistics
    corr_matrix, col_stats = compute_stats(prep.numeric_df, prep.feature_names)

    title = f"{algorithm.upper()} Analysis of {dataset_name}"

    return AnalysisOutput(
        id=analysis_id,
        title=title,
        dataset_source=dataset_source,
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        dataset_url=dataset_url,
        num_rows=len(prep.numeric_df),
        num_columns=len(prep.feature_names),
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
        feature_names=prep.feature_names,
        encoding_info=prep.encoding_info,
        missing_values=missing_values,
        dropped_columns=[
            DroppedColumn(column=d["column"], reason=d["reason"])
            for d in prep.dropped_columns
        ],
        original_column_count=original_column_count,
    )
