"""Plotly visualization generation — 9 chart types."""
import json
import logging
import math
from typing import List

from app.models.schemas import AnalysisOutput, ChartData

logger = logging.getLogger(__name__)


def _get_imports():
    """Lazy-load heavy plotting dependencies."""
    import numpy as np
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    return np, go, px, make_subplots


def _to_chart(fig, chart_type: str, title: str) -> ChartData:
    """Convert a Plotly figure to ChartData."""
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=40, r=40, t=50, b=40),
    )
    html = fig.to_html(include_plotlyjs=False, full_html=False)
    plotly_json = fig.to_json()
    return ChartData(
        chart_type=chart_type,
        title=title,
        html=html,
        plotly_json=plotly_json,
    )


def scatter_2d(analysis: AnalysisOutput) -> ChartData:
    """2D PCA cluster scatter plot."""
    np, go, px, _ = _get_imports()
    coords = np.array(analysis.pca_2d)
    labels = np.array(analysis.cluster_labels)

    fig = go.Figure()
    for cluster_id in sorted(set(labels)):
        mask = labels == cluster_id
        name = f"Cluster {cluster_id}" if cluster_id >= 0 else "Noise"
        fig.add_trace(go.Scatter(
            x=coords[mask, 0].tolist(),
            y=coords[mask, 1].tolist(),
            mode="markers",
            name=name,
            marker=dict(size=6, opacity=0.7),
        ))

    fig.update_layout(
        title="Cluster Scatter (PCA 2D)",
        xaxis_title="PC1",
        yaxis_title="PC2",
        height=400,
    )
    return _to_chart(fig, "scatter_2d", "2D Cluster Scatter (PCA)")


def scatter_3d(analysis: AnalysisOutput) -> ChartData:
    """3D PCA cluster scatter plot."""
    np, go, px, _ = _get_imports()
    coords = np.array(analysis.pca_3d)
    labels = np.array(analysis.cluster_labels)

    fig = go.Figure()
    for cluster_id in sorted(set(labels)):
        mask = labels == cluster_id
        name = f"Cluster {cluster_id}" if cluster_id >= 0 else "Noise"
        fig.add_trace(go.Scatter3d(
            x=coords[mask, 0].tolist(),
            y=coords[mask, 1].tolist(),
            z=coords[mask, 2].tolist() if coords.shape[1] >= 3 else [0] * mask.sum(),
            mode="markers",
            name=name,
            marker=dict(size=4, opacity=0.7),
        ))

    fig.update_layout(
        title="Cluster Scatter (PCA 3D)",
        scene=dict(xaxis_title="PC1", yaxis_title="PC2", zaxis_title="PC3"),
        height=400,
    )
    return _to_chart(fig, "scatter_3d", "3D Cluster Scatter (PCA)")


def cluster_sizes(analysis: AnalysisOutput) -> ChartData:
    """Bar chart of cluster sizes."""
    _, go, px, _ = _get_imports()
    COLORS = px.colors.qualitative.Set2
    profiles = analysis.cluster_profiles
    ids = [f"Cluster {p.cluster_id}" for p in profiles]
    sizes = [p.size for p in profiles]
    pcts = [f"{p.percentage}%" for p in profiles]

    fig = go.Figure(go.Bar(
        x=ids,
        y=sizes,
        text=pcts,
        textposition="outside",
        marker_color=COLORS[:len(ids)],
    ))
    fig.update_layout(
        title="Cluster Sizes",
        xaxis_title="Cluster",
        yaxis_title="Number of Samples",
    )
    return _to_chart(fig, "cluster_sizes", "Cluster Size Distribution")


def feature_boxplots(analysis: AnalysisOutput) -> ChartData:
    """Box plots of features per cluster."""
    _, go, px, make_subplots = _get_imports()
    COLORS = px.colors.qualitative.Set2
    labels = analysis.cluster_labels
    features = analysis.feature_names
    profiles = analysis.cluster_profiles

    # Use top features from first profile to limit charts
    top_features = features[:6]  # Limit to 6 features

    n_features = len(top_features)
    fig = make_subplots(
        rows=1, cols=n_features,
        subplot_titles=top_features,
        shared_yaxes=False,
    )

    # Reconstruct data from cluster profiles centroids and stats
    for i, feat in enumerate(top_features, 1):
        for profile in profiles:
            if feat in profile.centroid:
                fig.add_trace(
                    go.Box(
                        y=[profile.centroid[feat]],
                        name=f"C{profile.cluster_id}",
                        marker_color=COLORS[profile.cluster_id % len(COLORS)],
                        showlegend=(i == 1),
                    ),
                    row=1, col=i,
                )

    fig.update_layout(title="Feature Values by Cluster", height=400)
    return _to_chart(fig, "feature_boxplots", "Feature Box Plots per Cluster")


def correlation_heatmap(analysis: AnalysisOutput) -> ChartData:
    """Correlation matrix heatmap."""
    _, go, _, _ = _get_imports()
    corr = analysis.correlation_matrix
    features = list(corr.keys())
    values = [[corr[f1].get(f2, 0) for f2 in features] for f1 in features]

    fig = go.Figure(go.Heatmap(
        z=values,
        x=features,
        y=features,
        colorscale="RdBu_r",
        zmin=-1,
        zmax=1,
        text=[[f"{v:.2f}" for v in row] for row in values],
        texttemplate="%{text}",
    ))
    fig.update_layout(title="Feature Correlation Matrix", height=500)
    return _to_chart(fig, "correlation_heatmap", "Correlation Heatmap")


def silhouette_plot(analysis: AnalysisOutput) -> ChartData:
    """Silhouette score visualization — show score per cluster as bar chart."""
    _, go, px, _ = _get_imports()
    COLORS = px.colors.qualitative.Set2
    profiles = analysis.cluster_profiles
    sil = analysis.silhouette_score

    ids = [f"Cluster {p.cluster_id}" for p in profiles]
    sizes = [p.size for p in profiles]

    fig = go.Figure()

    # Show cluster sizes as bars with overall silhouette as annotation
    fig.add_trace(go.Bar(
        x=ids,
        y=sizes,
        marker_color=COLORS[:len(ids)],
        name="Cluster Size",
    ))

    sil_text = f"Overall Silhouette Score: {sil:.3f}" if sil is not None else "Silhouette: N/A"
    fig.update_layout(
        title=f"Clustering Quality — {sil_text}",
        xaxis_title="Cluster",
        yaxis_title="Size",
        height=400,
    )
    return _to_chart(fig, "silhouette", "Clustering Quality")


def parallel_coordinates(analysis: AnalysisOutput) -> ChartData:
    """Parallel coordinates plot showing cluster separation across features."""
    _, go, _, _ = _get_imports()
    profiles = analysis.cluster_profiles
    features = analysis.feature_names[:8]  # Limit features for readability

    dimensions = []
    for feat in features:
        values = [p.centroid.get(feat, 0) for p in profiles]
        dimensions.append(dict(
            label=feat,
            values=values,
        ))

    cluster_ids = [p.cluster_id for p in profiles]

    fig = go.Figure(go.Parcoords(
        line=dict(
            color=cluster_ids,
            colorscale="Viridis",
            showscale=True,
            cmin=min(cluster_ids),
            cmax=max(cluster_ids),
        ),
        dimensions=dimensions,
    ))
    fig.update_layout(title="Parallel Coordinates (Cluster Centroids)", height=400)
    return _to_chart(fig, "parallel_coordinates", "Parallel Coordinates")


def anomaly_overlay(analysis: AnalysisOutput) -> ChartData:
    """2D scatter with anomalies highlighted."""
    np, go, _, _ = _get_imports()
    coords = np.array(analysis.pca_2d)
    anomalies = np.array(analysis.anomaly_labels)

    normal_mask = anomalies == 0
    anomaly_mask = anomalies == 1

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=coords[normal_mask, 0].tolist(),
        y=coords[normal_mask, 1].tolist(),
        mode="markers",
        name="Normal",
        marker=dict(size=5, color="steelblue", opacity=0.5),
    ))
    fig.add_trace(go.Scatter(
        x=coords[anomaly_mask, 0].tolist(),
        y=coords[anomaly_mask, 1].tolist(),
        mode="markers",
        name="Anomaly",
        marker=dict(size=8, color="red", symbol="x", opacity=0.8),
    ))

    n_anom = int(anomaly_mask.sum())
    fig.update_layout(
        title=f"Anomaly Detection ({n_anom} anomalies found)",
        xaxis_title="PC1",
        yaxis_title="PC2",
        height=400,
    )
    return _to_chart(fig, "anomaly_overlay", "Anomaly Detection Overlay")


def feature_distributions(analysis: AnalysisOutput) -> ChartData:
    """Per-column distribution box plots from summary stats (max 12 columns)."""
    _, go, _, make_subplots = _get_imports()
    features = analysis.feature_names[:12]
    n = len(features)
    cols = min(n, 3)
    rows = math.ceil(n / cols)

    fig = make_subplots(rows=rows, cols=cols, subplot_titles=features)
    for i, feat in enumerate(features):
        r, c = divmod(i, cols)
        stats = analysis.column_stats.get(feat, {})
        if not stats:
            continue
        fig.add_trace(
            go.Box(
                lowerfence=[stats["min"]],
                q1=[stats["q25"]],
                median=[stats["median"]],
                q3=[stats["q75"]],
                upperfence=[stats["max"]],
                mean=[stats["mean"]],
                name=feat,
                showlegend=False,
            ),
            row=r + 1, col=c + 1,
        )

    fig.update_layout(title="Feature Distributions", height=min(250 * rows, 900))
    return _to_chart(fig, "feature_distributions", "Feature Distributions")


def generate_all(analysis: AnalysisOutput) -> List[ChartData]:
    """Generate all 9 chart types from an analysis output."""
    charts = []
    generators = [
        scatter_2d,
        scatter_3d,
        cluster_sizes,
        feature_boxplots,
        correlation_heatmap,
        silhouette_plot,
        parallel_coordinates,
        anomaly_overlay,
        feature_distributions,
    ]

    for gen in generators:
        try:
            chart = gen(analysis)
            charts.append(chart)
        except Exception as e:
            logger.warning("Failed to generate %s chart: %s", gen.__name__, e)

    logger.info("Generated %d charts", len(charts))
    return charts
