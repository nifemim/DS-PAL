"""Saved analyses API routes."""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.main import templates
from app.services.storage import (
    save_analysis,
    get_analysis,
    list_analyses,
    delete_analysis,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["saved"])


@router.post("/analysis/{analysis_id}/save")
async def save(request: Request, analysis_id: str):
    """Save a pending analysis to the database."""
    pending = request.app.state.pending_analyses.get(analysis_id)
    if not pending:
        return HTMLResponse(
            '<div class="error-message">Analysis not found or expired. Please run the analysis again.</div>'
        )

    try:
        await save_analysis(pending["analysis"], pending["charts"])
        # Remove from pending
        del request.app.state.pending_analyses[analysis_id]

        return HTMLResponse(
            '<div class="success-message">'
            'Analysis saved successfully! '
            '<a href="/saved">View saved analyses</a>'
            '</div>'
        )
    except Exception as e:
        logger.error("Failed to save analysis: %s", e)
        return HTMLResponse(
            f'<div class="error-message">Failed to save: {str(e)}</div>'
        )


@router.get("/saved")
async def list_saved(request: Request):
    """List all saved analyses. Returns HTMX partial."""
    analyses = await list_analyses()
    return templates.TemplateResponse(
        "partials/saved_list.html",
        {"request": request, "analyses": analyses},
    )


@router.get("/saved/{analysis_id}")
async def get_saved(request: Request, analysis_id: str):
    """Get a saved analysis with charts. Returns HTMX partial."""
    analysis = await get_analysis(analysis_id)
    if not analysis:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": "Analysis not found."},
        )

    return templates.TemplateResponse(
        "partials/analysis_detail.html",
        {"request": request, "analysis": analysis},
    )


@router.delete("/saved/{analysis_id}")
async def delete_saved(request: Request, analysis_id: str):
    """Delete a saved analysis."""
    deleted = await delete_analysis(analysis_id)
    if deleted:
        return HTMLResponse(
            '<div class="success-message">Analysis deleted.</div>'
        )
    return HTMLResponse(
        '<div class="error-message">Analysis not found.</div>'
    )
