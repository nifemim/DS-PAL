"""FastAPI application factory."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import init_db

logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).parent

# Templates - importable by routers
templates = Jinja2Templates(directory=APP_DIR / "templates")
templates.env.globals["debug"] = settings.app_debug


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup, clean up on shutdown."""
    logging.basicConfig(
        level=logging.DEBUG if settings.app_debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info("Starting DS-PAL...")

    # Initialize database
    await init_db()

    # Create cache directory
    Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)

    # Pending analyses store (in-memory, keyed by UUID)
    app.state.pending_analyses = {}

    # Chat conversation store (in-memory, keyed by session_id)
    app.state.conversations = {}

    # Shared HTTP client for outbound API calls (reuses TCP connections)
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=35.0, write=10.0, pool=5.0),
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
    )

    yield

    await app.state.http_client.aclose()
    logger.info("Shutting down DS-PAL...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="DS-PAL", lifespan=lifespan)

    # Mount static files
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

    # Security headers
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    # Register routers
    from app.routers import pages, search, analysis, saved, upload, chat

    app.include_router(pages.router)
    app.include_router(search.router, prefix="/api")
    app.include_router(analysis.router, prefix="/api")
    app.include_router(saved.router, prefix="/api")
    app.include_router(upload.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")

    return app


app = create_app()
