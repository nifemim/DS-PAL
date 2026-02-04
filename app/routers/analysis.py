"""Analysis API routes."""
import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Request, Form

from app.main import templates
from app.services.dataset_loader import download_dataset, load_dataframe
from app.services import analysis_engine
from app.services.visualization import generate_all

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analysis"])


@router.post("/analyze")
async def run_analysis(
    request: Request,
    source: str = Form(...),
    dataset_id: str = Form(...),
    name: str = Form(""),
    url: str = Form(""),
    algorithm: str = Form("kmeans"),
    n_clusters: Optional[int] = Form(None),
    columns: List[str] = Form([]),
    contamination: float = Form(0.05),
):
    """Run ML analysis on a dataset. Returns HTMX partial with results."""
    try:
        # Download/load dataset
        file_path = await download_dataset(source, dataset_id, url)
        df = load_dataframe(file_path)

        # Run analysis in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        analysis = await loop.run_in_executor(
            None,
            lambda: analysis_engine.run(
                df=df,
                dataset_name=name or dataset_id,
                dataset_source=source,
                dataset_id=dataset_id,
                dataset_url=url,
                algorithm=algorithm,
                n_clusters=n_clusters if n_clusters and n_clusters >= 2 else None,
                columns=columns if columns else None,
                contamination=contamination,
            ),
        )

        # Generate visualizations
        charts = await loop.run_in_executor(None, lambda: generate_all(analysis))

        # Store in pending analyses for save-later flow
        app = request.app
        app.state.pending_analyses[analysis.id] = {
            "analysis": analysis,
            "charts": charts,
        }

        # Evict old entries (TTL-based, 1 hour)
        _evict_old_pending(app)

        return templates.TemplateResponse(
            "partials/analysis_results.html",
            {
                "request": request,
                "analysis": analysis,
                "charts": charts,
            },
        )

    except ValueError as e:
        logger.warning("Analysis validation error: %s", e)
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": str(e)},
        )
    except Exception as e:
        logger.error("Analysis failed: %s", e, exc_info=True)
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": f"Analysis failed: {str(e)}"},
        )


def _evict_old_pending(app):
    """Remove pending analyses older than 1 hour."""
    import time
    now = time.time()
    to_remove = []
    for aid, data in app.state.pending_analyses.items():
        created = data.get("created_at", now)
        if now - created > 3600:
            to_remove.append(aid)
    for aid in to_remove:
        del app.state.pending_analyses[aid]
