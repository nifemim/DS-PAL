"""Analysis API routes."""
import asyncio
import logging
import time
from typing import List, Optional

from urllib.parse import quote

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import settings
from app.main import templates
from app.services.dataset_loader import download_dataset, load_dataframe
from app.services import analysis_engine
from app.services.visualization import generate_all
from app.services.insights import generate_insights
from app.services.storage import get_analysis

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
    categorical_columns: List[str] = Form([]),
    contamination: float = Form(0.05),
    dataset_description: str = Form(""),
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
                columns=columns,
                categorical_columns=categorical_columns if categorical_columns else None,
                contamination=contamination,
            ),
        )

        # Attach user-provided description (used by LLM prompt, not ML pipeline)
        analysis.dataset_description = dataset_description

        # Generate visualizations
        charts = await loop.run_in_executor(None, lambda: generate_all(analysis))

        # Store in pending analyses for save-later flow
        app = request.app
        app.state.pending_analyses[analysis.id] = {
            "analysis": analysis,
            "charts": charts,
            "created_at": time.time(),
        }

        # Evict old entries (TTL-based, 1 hour)
        _evict_old_pending(app)

        return RedirectResponse(f"/analysis/{analysis.id}", status_code=303)

    except Exception as e:
        logger.error("Analysis failed: %s", e, exc_info=True)
        error_msg = quote(str(e)[:200])
        return RedirectResponse(
            f"/dataset/{source}/{dataset_id}?name={quote(name)}&url={quote(url)}&error={error_msg}",
            status_code=303,
        )


@router.get("/analysis/{analysis_id}/detail")
async def analysis_detail(request: Request, analysis_id: str):
    """Unified detail endpoint: checks pending first, then saved."""
    # Check pending first
    pending = request.app.state.pending_analyses.get(analysis_id)
    if pending:
        return templates.TemplateResponse(
            "partials/analysis_results.html",
            {
                "request": request,
                "analysis": pending["analysis"],
                "charts": pending["charts"],
                "insights_enabled": settings.insights_enabled,
            },
        )

    # Fall back to saved
    saved = await get_analysis(analysis_id)
    if saved:
        return templates.TemplateResponse(
            "partials/analysis_detail.html",
            {"request": request, "analysis": saved},
        )

    return templates.TemplateResponse(
        "partials/error.html",
        {"request": request, "message": "Analysis not found or expired."},
    )


@router.get("/analysis/{analysis_id}/insights")
async def get_insights(request: Request, analysis_id: str):
    """Generate LLM insights for an analysis (initial load). Returns HTMX partial."""
    entry = request.app.state.pending_analyses.get(analysis_id)
    if not entry:
        return HTMLResponse("")

    analysis = entry["analysis"]
    return await _render_insights(request, analysis_id, analysis)


@router.post("/analysis/{analysis_id}/insights")
async def regenerate_insights(
    request: Request,
    analysis_id: str,
    dataset_description: str = Form(""),
):
    """Regenerate LLM insights with an updated description. Returns HTMX partial."""
    entry = request.app.state.pending_analyses.get(analysis_id)
    if not entry:
        return HTMLResponse("")

    analysis = entry["analysis"]
    analysis.dataset_description = dataset_description
    return await _render_insights(request, analysis_id, analysis)


async def _render_insights(request: Request, analysis_id: str, analysis):
    """Shared logic for rendering the insights partial."""
    sections = await generate_insights(analysis)

    return templates.TemplateResponse(
        "partials/cluster_insights.html",
        {
            "request": request,
            "analysis_id": analysis_id,
            "sections": sections,
            "dataset_description": analysis.dataset_description,
        },
    )


def _evict_old_pending(app):
    """Remove pending analyses older than 1 hour."""
    now = time.time()
    to_remove = []
    for aid, data in app.state.pending_analyses.items():
        created = data.get("created_at", now)
        if now - created > 3600:
            to_remove.append(aid)
    for aid in to_remove:
        del app.state.pending_analyses[aid]
