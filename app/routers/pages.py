"""Full HTML page routes."""
import json
import logging
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.main import templates
from app.services.dataset_loader import (
    build_preview,
    detect_sheets,
    download_dataset,
    join_sheets,
    load_dataframe,
    save_joined_csv,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "max_file_size_mb": settings.max_file_size_mb},
    )


@router.get("/saved")
async def saved_page(request: Request):
    return templates.TemplateResponse("saved.html", {"request": request})


@router.get("/analysis/{analysis_id}")
async def analysis_page(request: Request, analysis_id: str):
    return templates.TemplateResponse(
        "analysis.html", {"request": request, "analysis_id": analysis_id}
    )


# --- Multi-sheet Excel routes (must be registered before the wildcard dataset route) ---


@router.get("/dataset/upload/{upload_id}/sheets")
async def select_sheets_page(request: Request, upload_id: str, name: str = ""):
    """Sheet selection page for multi-sheet Excel files."""
    file_path = await download_dataset("upload", upload_id, "")
    sheets = detect_sheets(file_path)
    return templates.TemplateResponse(
        "select_sheets.html",
        {"request": request, "upload_id": upload_id, "name": name, "sheets": sheets},
    )


@router.post("/dataset/upload/{upload_id}/sheets")
async def process_sheet_selection(request: Request, upload_id: str):
    """Process sheet selection: single sheet -> preview, multiple -> join config."""
    form = await request.form()
    name = form.get("name", "")
    selected = form.getlist("sheets")

    if not selected:
        return RedirectResponse(
            url=f"/dataset/upload/{upload_id}/sheets?name={quote(name)}",
            status_code=303,
        )

    if len(selected) == 1:
        return RedirectResponse(
            url=f"/dataset/upload/{upload_id}?name={quote(name)}&sheet={quote(selected[0])}",
            status_code=303,
        )

    # Multiple sheets — detect shared columns for join config
    file_path = await download_dataset("upload", upload_id, "")
    all_sheets = detect_sheets(file_path)
    selected_sheets = [s for s in all_sheets if s["name"] in selected]

    # Find shared columns between consecutive pairs
    pairs = []
    for i in range(len(selected_sheets) - 1):
        left_cols = set(selected_sheets[i]["columns"])
        right_cols = set(selected_sheets[i + 1]["columns"])
        shared = sorted(left_cols & right_cols)
        pairs.append({
            "left": selected_sheets[i]["name"],
            "right": selected_sheets[i + 1]["name"],
            "shared_columns": shared,
        })

    return templates.TemplateResponse(
        "join_config.html",
        {
            "request": request,
            "upload_id": upload_id,
            "name": name,
            "selected_sheets": selected_sheets,
            "pairs": pairs,
        },
    )


@router.post("/dataset/upload/{upload_id}/join")
async def execute_join(request: Request, upload_id: str):
    """Execute join, show preview, or save and redirect to dataset page."""
    form = await request.form()
    name = form.get("name", "")
    action = form.get("action", "preview")

    sheet_configs = _parse_join_form(form)

    file_path = await download_dataset("upload", upload_id, "")
    joined_df = join_sheets(file_path, sheet_configs)

    if action == "preview":
        preview_rows = joined_df.head(5).to_dict(orient="records")
        return templates.TemplateResponse(
            "join_preview.html",
            {
                "request": request,
                "upload_id": upload_id,
                "name": name,
                "num_rows": len(joined_df),
                "num_columns": len(joined_df.columns),
                "columns": joined_df.columns.tolist(),
                "sample_rows": preview_rows,
                "sheet_configs_json": json.dumps(sheet_configs),
            },
        )

    # action == "confirm" — save joined CSV and redirect
    save_joined_csv(joined_df, upload_id)
    return RedirectResponse(
        url=f"/dataset/upload/{upload_id}?name={quote(name)}&joined=1",
        status_code=303,
    )


# --- Wildcard dataset route ---


@router.get("/dataset/{source}/{dataset_id:path}")
async def dataset_page(
    request: Request,
    source: str,
    dataset_id: str,
    name: str = "",
    url: str = "",
    sheet: str = "",
    joined: str = "",
):
    """Dedicated page for dataset preview and analysis configuration."""
    try:
        file_path = await download_dataset(source, dataset_id, url)

        if joined:
            joined_path = file_path.parent / "joined.csv"
            df = load_dataframe(joined_path)
        elif sheet:
            df = load_dataframe(file_path, sheet_name=sheet)
        else:
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


def _parse_join_form(form) -> list[dict]:
    """Extract sheet join configuration from form data.

    Expects form fields:
      - sheet_0, sheet_1, ... : sheet names
      - join_key_0, join_key_1, ... : join keys for pairs (index matches right sheet)
      - join_type_0, join_type_1, ... : join types for pairs
    """
    configs = []
    i = 0
    while True:
        sheet_name = form.get(f"sheet_{i}")
        if sheet_name is None:
            break
        config = {"name": sheet_name}
        if i > 0:
            config["join_key"] = form.get(f"join_key_{i}", "")
            config["join_type"] = form.get(f"join_type_{i}", "inner")
        configs.append(config)
        i += 1
    return configs
