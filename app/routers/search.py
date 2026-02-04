"""Dataset search and preview API routes."""
import logging
from fastapi import APIRouter, Request, Form
from app.main import templates
from app.services.dataset_search import search_all
from app.services.dataset_loader import download_dataset, load_dataframe, build_preview
from app.services.storage import save_search_history

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search"])


@router.post("/search")
async def search_datasets(request: Request, query: str = Form(...)):
    """Search for datasets across all providers. Returns HTMX partial."""
    query = query.strip()
    if len(query) < 2:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": "Please enter at least 2 characters."},
        )

    try:
        results = await search_all(query)
        await save_search_history(query, len(results))

        return templates.TemplateResponse(
            "partials/search_results.html",
            {"request": request, "query": query, "results": results},
        )
    except Exception as e:
        logger.error("Search failed: %s", e)
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": f"Search failed: {str(e)}"},
        )


@router.post("/dataset/preview")
async def preview_dataset(
    request: Request,
    source: str = Form(...),
    dataset_id: str = Form(...),
    name: str = Form(""),
    url: str = Form(""),
):
    """Download and preview a dataset. Returns HTMX partial with config form."""
    try:
        file_path = await download_dataset(source, dataset_id, url)
        df = load_dataframe(file_path)
        preview = build_preview(df, source, dataset_id, name, url)

        if len(preview.numeric_columns) < 2:
            return templates.TemplateResponse(
                "partials/error.html",
                {
                    "request": request,
                    "message": "This dataset needs at least 2 numeric columns for clustering analysis. "
                               f"Found: {len(preview.numeric_columns)} numeric column(s).",
                },
            )

        return templates.TemplateResponse(
            "partials/dataset_preview.html",
            {"request": request, "preview": preview},
        )
    except Exception as e:
        logger.error("Preview failed for %s/%s: %s", source, dataset_id, e)
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "message": f"Failed to load dataset: {str(e)}"},
        )
