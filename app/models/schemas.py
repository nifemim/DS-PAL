"""Pydantic request/response models."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- Search ---

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=200)


class DatasetResult(BaseModel):
    source: str
    dataset_id: str
    name: str
    description: str = ""
    url: str = ""
    size: str = ""
    format: str = ""
    tags: List[str] = []


class SearchResponse(BaseModel):
    query: str
    results: List[DatasetResult] = []
    result_count: int = 0


# --- Dataset Preview ---

class PreviewRequest(BaseModel):
    source: str
    dataset_id: str
    name: str = ""
    url: str = ""


class ColumnInfo(BaseModel):
    name: str
    dtype: str
    non_null_count: int
    null_count: int
    sample_values: List[Any] = []
    cardinality: Optional[int] = None
    suggested_encoding: Optional[str] = None  # "one-hot", "label", "boolean", "numeric-coerce", or None
    is_id_like: bool = False


class DatasetPreview(BaseModel):
    source: str
    dataset_id: str
    name: str
    url: str = ""
    num_rows: int
    num_columns: int
    columns: List[ColumnInfo]
    numeric_columns: List[str]
    categorical_columns: List[str] = []
    sample_rows: List[Dict[str, Any]]


# --- Analysis ---

class AnalysisRequest(BaseModel):
    source: str
    dataset_id: str
    name: str = ""
    url: str = ""
    algorithm: str = Field(default="kmeans", pattern="^(kmeans|dbscan|hierarchical)$")
    n_clusters: Optional[int] = None
    columns: List[str] = []
    contamination: float = Field(default=0.05, ge=0.01, le=0.5)


class ClusterProfile(BaseModel):
    cluster_id: int
    size: int
    percentage: float
    centroid: Dict[str, Any] = {}
    top_features: List[Dict[str, Any]] = []


class AnalysisOutput(BaseModel):
    id: str
    title: str
    dataset_source: str
    dataset_id: str
    dataset_name: str
    dataset_url: str = ""
    num_rows: int
    num_columns: int
    column_names: List[str]
    algorithm: str
    params: Dict[str, Any] = {}
    n_clusters: int
    silhouette_score: Optional[float] = None
    cluster_profiles: List[ClusterProfile]
    cluster_labels: List[int]
    pca_2d: List[List[float]] = []
    pca_3d: List[List[float]] = []
    anomaly_labels: List[int] = []
    anomaly_scores: List[float] = []
    correlation_matrix: Dict[str, Dict[str, float]] = {}
    column_stats: Dict[str, Dict[str, Any]] = {}
    feature_names: List[str] = []
    encoding_info: List[Dict[str, Any]] = []


# --- Visualization ---

class ChartData(BaseModel):
    chart_type: str
    title: str
    html: str
    plotly_json: str


# --- Saved Analysis ---

class SavedAnalysis(BaseModel):
    id: str
    title: str
    dataset_source: str
    dataset_id: str
    dataset_name: str
    dataset_url: str = ""
    num_rows: Optional[int] = None
    num_columns: Optional[int] = None
    column_names: List[str] = []
    analysis_config: Dict[str, Any] = {}
    analysis_result: Dict[str, Any] = {}
    created_at: str = ""
    updated_at: str = ""
    charts: List[ChartData] = []


# --- Tickets ---

class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    SOLVED = "solved"
    WONT_FIX = "wont_fix"


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    priority: TicketPriority = TicketPriority.MEDIUM
    tags: List[str] = []


class TicketUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    tags: Optional[List[str]] = None
    resolution: Optional[str] = None


class Ticket(BaseModel):
    id: int
    title: str
    description: str = ""
    status: TicketStatus = TicketStatus.OPEN
    priority: TicketPriority = TicketPriority.MEDIUM
    tags: List[str] = []
    resolution: str = ""
    created_at: str = ""
    updated_at: str = ""
    solved_at: Optional[str] = None


class TicketStats(BaseModel):
    total: int = 0
    by_status: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}
