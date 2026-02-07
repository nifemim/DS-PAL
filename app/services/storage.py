"""CRUD operations for saved analyses."""
import json
import uuid
import logging
from typing import List, Optional

from app.database import get_db
from app.models.schemas import SavedAnalysis, ChartData, AnalysisOutput

logger = logging.getLogger(__name__)


async def save_analysis(
    analysis: AnalysisOutput,
    charts: List[ChartData],
) -> str:
    """Save an analysis and its charts to the database. Returns the analysis ID."""
    db = await get_db()
    try:
        analysis_config = json.dumps({
            "algorithm": analysis.algorithm,
            "params": analysis.params,
            "columns": analysis.feature_names,
            "encoding_info": analysis.encoding_info,
        })
        analysis_result = json.dumps({
            "n_clusters": analysis.n_clusters,
            "silhouette_score": analysis.silhouette_score,
            "cluster_profiles": [p.model_dump() for p in analysis.cluster_profiles],
            "cluster_labels": analysis.cluster_labels,
            "anomaly_labels": analysis.anomaly_labels,
            "column_stats": analysis.column_stats,
        })
        column_names = json.dumps(analysis.column_names)

        await db.execute(
            """INSERT INTO analyses
               (id, title, dataset_source, dataset_id, dataset_name, dataset_url,
                num_rows, num_columns, column_names, analysis_config, analysis_result)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                analysis.id,
                analysis.title,
                analysis.dataset_source,
                analysis.dataset_id,
                analysis.dataset_name,
                analysis.dataset_url,
                analysis.num_rows,
                analysis.num_columns,
                column_names,
                analysis_config,
                analysis_result,
            ),
        )

        for i, chart in enumerate(charts):
            chart_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO visualizations
                   (id, analysis_id, chart_type, title, plotly_json, display_order)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (chart_id, analysis.id, chart.chart_type, chart.title, chart.plotly_json, i),
            )

        await db.commit()
        logger.info("Saved analysis %s with %d charts", analysis.id, len(charts))
        return analysis.id
    finally:
        await db.close()


async def get_analysis(analysis_id: str) -> Optional[SavedAnalysis]:
    """Get a saved analysis by ID, including its charts."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        chart_cursor = await db.execute(
            """SELECT chart_type, title, plotly_json
               FROM visualizations
               WHERE analysis_id = ?
               ORDER BY display_order""",
            (analysis_id,),
        )
        chart_rows = await chart_cursor.fetchall()

        charts = [
            ChartData(
                chart_type=cr["chart_type"],
                title=cr["title"],
                html="",
                plotly_json=cr["plotly_json"],
            )
            for cr in chart_rows
        ]

        return SavedAnalysis(
            id=row["id"],
            title=row["title"],
            dataset_source=row["dataset_source"],
            dataset_id=row["dataset_id"],
            dataset_name=row["dataset_name"],
            dataset_url=row["dataset_url"] or "",
            num_rows=row["num_rows"],
            num_columns=row["num_columns"],
            column_names=json.loads(row["column_names"]) if row["column_names"] else [],
            analysis_config=json.loads(row["analysis_config"]),
            analysis_result=json.loads(row["analysis_result"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            charts=charts,
        )
    finally:
        await db.close()


async def list_analyses() -> List[SavedAnalysis]:
    """List all saved analyses (without chart data)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM analyses ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()

        return [
            SavedAnalysis(
                id=row["id"],
                title=row["title"],
                dataset_source=row["dataset_source"],
                dataset_id=row["dataset_id"],
                dataset_name=row["dataset_name"],
                dataset_url=row["dataset_url"] or "",
                num_rows=row["num_rows"],
                num_columns=row["num_columns"],
                column_names=json.loads(row["column_names"]) if row["column_names"] else [],
                analysis_config=json.loads(row["analysis_config"]),
                analysis_result=json.loads(row["analysis_result"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
    finally:
        await db.close()


async def delete_analysis(analysis_id: str) -> bool:
    """Delete an analysis and its charts. Returns True if deleted."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM analyses WHERE id = ?", (analysis_id,)
        )
        await db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Deleted analysis %s", analysis_id)
        return deleted
    finally:
        await db.close()


async def save_search_history(query: str, result_count: int) -> None:
    """Record a search query."""
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO search_history (query, result_count) VALUES (?, ?)",
            (query, result_count),
        )
        await db.commit()
    finally:
        await db.close()
