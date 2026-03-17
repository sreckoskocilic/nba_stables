"""
NBA Stables REST API
FastAPI backend for live NBA statistics
"""

import logging
import logging.config
import os
import time
from contextlib import asynccontextmanager

import helpers.common as _common
import helpers.stats as _stats
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from helpers.stats import get_display_date
from routes.injuries import CBS_INJURIES_FILE
from routes.injuries import router as injuries_router
from routes.players import router as players_router
from routes.scores import router
from routes.season import router as season_router
from routes.trades import router as trades_router
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

logger = logging.getLogger(__name__)
_perf_logger = logging.getLogger("perf")


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        path = request.url.path
        if not path.startswith("/web/"):
            _perf_logger.info(
                "%-7s %-40s %d  %.0fms",
                request.method,
                path,
                response.status_code,
                duration_ms,
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate env var bounds
    workers = _common._DEFAULT_WORKERS
    if not (1 <= workers <= 100):
        logger.warning(
            "EXECUTOR_WORKERS=%d is outside reasonable range [1, 100]", workers
        )
    timeout = _common.STATS_TIMEOUT
    if timeout < 1:
        logger.warning("STATS_TIMEOUT=%d must be >= 1", timeout)
    # Warn if injuries data file is missing
    if not os.path.exists(CBS_INJURIES_FILE):
        logger.warning("CBS injuries file not found at startup: %s", CBS_INJURIES_FILE)
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
app.add_middleware(TimingMiddleware)

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
    nba_api_ok = (
        bool(_stats._players_cache) and _stats._players_cache_expires > time.time()
    )
    status = "healthy" if cache_ok else "degraded"
    return {
        "status": status,
        "date": get_display_date(0),
        "cache_ok": cache_ok,
        "nba_data_fresh": nba_api_ok,
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


@app.get("/soccer")
async def serve_soccer():  # pragma: no cover
    soccer_path = os.path.join(static_dir, "soccer.html")
    return FileResponse(soccer_path)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=4,
    )
