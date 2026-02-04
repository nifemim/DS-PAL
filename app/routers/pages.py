"""Full HTML page routes."""
from fastapi import APIRouter, Request
from app.main import templates

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
