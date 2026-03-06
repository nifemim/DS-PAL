"""Analysis API routes."""
import asyncio
import logging
import time
import uuid
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


async def _run_analysis_task(app, analysis_id: str, params: dict):
    """Background task: download, analyze, generate charts."""
    try:
        file_path = await download_dataset(params["source"], params["dataset_id"], params["url"])
        df = load_dataframe(file_path)

        loop = asyncio.get_event_loop()
        analysis = await loop.run_in_executor(
            None,
            lambda: analysis_engine.run(
                df=df,
                dataset_name=params["name"] or params["dataset_id"],
                dataset_source=params["source"],
                dataset_id=params["dataset_id"],
                dataset_url=params["url"],
                algorithm=params["algorithm"],
                n_clusters=params["n_clusters"],
                columns=params["columns"],
                categorical_columns=params["categorical_columns"],
                contamination=params["contamination"],
            ),
        )

        analysis.dataset_description = params.get("dataset_description", "")
        charts = await loop.run_in_executor(None, lambda: generate_all(analysis))

        # Replace the pending entry with completed results
        app.state.pending_analyses[analysis_id] = {
            "analysis": analysis,
            "charts": charts,
            "created_at": time.time(),
            "status": "done",
        }
        logger.info("Analysis %s completed", analysis_id)

    except Exception as e:
        logger.error("Analysis %s failed: %s", analysis_id, e, exc_info=True)
        app.state.pending_analyses[analysis_id] = {
            "status": "error",
            "error": str(e)[:200],
            "created_at": time.time(),
            "source": params["source"],
            "dataset_id": params["dataset_id"],
            "name": params["name"],
            "url": params["url"],
        }


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
    """Start analysis in background and redirect to loading page immediately."""
    analysis_id = str(uuid.uuid4())
    app = request.app

    # Store as "running" so the detail endpoint knows it's in progress
    app.state.pending_analyses[analysis_id] = {
        "status": "running",
        "dataset_name": name or dataset_id,
        "algorithm": algorithm,
        "created_at": time.time(),
    }

    _evict_old_pending(app)

    # Kick off analysis in background (store ref to prevent GC)
    task = asyncio.create_task(_run_analysis_task(app, analysis_id, {
        "source": source,
        "dataset_id": dataset_id,
        "name": name,
        "url": url,
        "algorithm": algorithm,
        "n_clusters": n_clusters if n_clusters and n_clusters >= 2 else None,
        "columns": columns,
        "categorical_columns": categorical_columns if categorical_columns else None,
        "contamination": contamination,
        "dataset_description": dataset_description,
    }))
    app.state.pending_analyses[analysis_id]["task"] = task

    return RedirectResponse(f"/analysis/{analysis_id}", status_code=303)


@router.get("/analysis/{analysis_id}/detail")
async def analysis_detail(request: Request, analysis_id: str):
    """Unified detail endpoint: checks pending first, then saved."""
    pending = request.app.state.pending_analyses.get(analysis_id)

    if pending:
        status = pending.get("status", "done")

        # Still running — return loading partial that auto-polls
        if status == "running":
            return templates.TemplateResponse(
                "partials/analysis_loading.html",
                {
                    "request": request,
                    "analysis_id": analysis_id,
                    "dataset_name": pending.get("dataset_name", ""),
                    "algorithm": pending.get("algorithm", ""),
                },
            )

        # Failed — show error
        if status == "error":
            error_msg = pending.get("error", "Analysis failed")
            return templates.TemplateResponse(
                "partials/error.html",
                {"request": request, "message": f"Analysis failed: {error_msg}"},
            )

        # Done — render results (no polling element, so polling stops)
        return templates.TemplateResponse(
            "partials/analysis_results.html",
            {
                "request": request,
                "analysis": pending["analysis"],
                "analysis_id": analysis_id,
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
