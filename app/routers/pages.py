"""Full HTML page routes."""
import logging
from fastapi import APIRouter, Request
from app.main import templates
from app.services.dataset_loader import download_dataset, load_dataframe, build_preview

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/saved")
async def saved_page(request: Request):
    return templates.TemplateResponse("saved.html", {"request": request})


@router.get("/analysis/{analysis_id}")
async def analysis_page(request: Request, analysis_id: str):
    return templates.TemplateResponse(
        "analysis.html", {"request": request, "analysis_id": analysis_id}
    )


@router.get("/dataset/{source}/{dataset_id:path}")
async def dataset_page(
    request: Request, source: str, dataset_id: str, name: str = "", url: str = ""
):
    """Dedicated page for dataset preview and analysis configuration."""
    try:
        file_path = await download_dataset(source, dataset_id, url)
        df = load_dataframe(file_path)
        preview = build_preview(df, source, dataset_id, name, url)

        return templates.TemplateResponse(
            "dataset.html", {"request": request, "preview": preview}
        )
    except Exception as e:
        logger.error("Dataset page failed for %s/%s: %s", source, dataset_id, e)
        return templates.TemplateResponse(
            "dataset.html",
            {"request": request, "preview": None, "error": str(e)},
        )
