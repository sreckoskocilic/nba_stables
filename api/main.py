"""
NBA Stables REST API
FastAPI backend for live NBA statistics
"""

import logging
import logging.config
import os
from contextlib import asynccontextmanager

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import helpers.common as _common
from helpers.stats import get_display_date
from routes.injuries import router as injuries_router
from routes.players import router as players_router
from routes.scores import router
from routes.season import router as season_router
from routes.trades import router as trades_router
from starlette.middleware.gzip import GZipMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    _common.cache.clear()


app = FastAPI(
    title="NBA Stables API",
    description="Live NBA statistics API",
    version="1.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

# Enable CORS for frontend
_default_cors = ["http://localhost:3000", "http://127.0.0.1:3000"]
_cors_env = os.environ.get("CORS_ORIGINS")
if _cors_env:
    _cors_origins = _cors_env.split(",")
    if _cors_origins == ["*"]:
        logger.warning("CORS_ORIGINS explicitly set to wildcard (*)")
else:
    _cors_origins = _default_cors
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(router)
app.include_router(players_router)
app.include_router(trades_router)
app.include_router(injuries_router)
app.include_router(season_router)

LOG_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "log_config.yml"
)
try:
    with open(LOG_CONFIG_FILE, "r") as f:
        logging.config.dictConfig(yaml.safe_load(f.read()))
except OSError:  # pragma: no cover
    logging.basicConfig(level=logging.WARNING)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    test_key = "_health_probe"
    _common.cache.set(test_key, True, 5)
    cache_ok = _common.cache.get(test_key) is True
    return {
        "status": "healthy" if cache_ok else "degraded",
        "date": get_display_date(0),
        "cache_ok": cache_ok,
    }


# Serve web files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
if os.path.exists(static_dir):
    app.mount("/web", StaticFiles(directory=static_dir), name="web")


@app.get("/sitemap.xml")
async def serve_sitemap():  # pragma: no cover
    """Serve sitemap.xml"""
    sitemap_path = os.path.join(static_dir, "sitemap.xml")
    if os.path.exists(sitemap_path):
        return FileResponse(sitemap_path, media_type="application/xml")
    raise HTTPException(status_code=404, detail="Sitemap not found")


@app.get("/")
async def serve_frontend():  # pragma: no cover
    """Serve the frontend"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "NBA Stables API", "docs": "/docs"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=4,
    )
