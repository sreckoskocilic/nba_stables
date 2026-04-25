"""
NBA Stables REST API
FastAPI backend for live NBA statistics
"""

import asyncio
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
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from helpers.stats import get_display_date
from middleware.security import SecurityHeadersMiddleware
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
    # Startup
    logger.info("Starting NBA Stables API...")
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
    # Pre-warm players cache to avoid slow first request
    try:
        await asyncio.to_thread(_stats.load_players_file)
        logger.info("Players cache warmed")
    except Exception as e:  # pragma: no cover
        logger.warning("Failed to warm players cache: %s", e)
    yield
    # Shutdown - only clear cache, executor shutdown handled by atexit
    logger.info("Shutting down NBA Stables API...")
    _common.cache.clear()
    logger.info("Shutdown complete")


app = FastAPI(
    title="NBA Stables API",
    description="Live NBA statistics API",
    version="1.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(SecurityHeadersMiddleware)
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
    with open(LOG_CONFIG_FILE, "r", encoding="utf-8") as f:
        logging.config.dictConfig(yaml.safe_load(f.read()))
except OSError:  # pragma: no cover
    logging.basicConfig(level=logging.WARNING)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    try:
        _common.cache.set("_hc", True, 1)
        cache_ok = _common.cache.get("_hc") is True
        nba_api_ok = _stats.is_players_cache_valid()
        status = "healthy" if cache_ok and nba_api_ok else "degraded"
    except Exception as e:
        logger.warning("Health check failed: %s", e)
        return {
            "status": "degraded",
            "date": get_display_date(0),
            "version": app.version,
            "cache_ok": False,
            "nba_api_ok": False,
        }
    return {
        "status": status,
        "date": get_display_date(0),
        "version": app.version,
        "cache_ok": cache_ok,
        "nba_api_ok": nba_api_ok,
    }


# Serve web files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
if os.path.exists(static_dir):
    app.mount("/web", StaticFiles(directory=static_dir), name="web")


@app.get("/t/a.js")
async def analytics_stub():  # pragma: no cover
    """Dev stub — in production Caddy proxies /t/a.js to the analytics server."""
    return Response(content="", media_type="application/javascript")


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


if __name__ == "__main__":  # pragma: no cover
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=4,
    )
