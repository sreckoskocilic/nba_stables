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

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

import helpers.common as _common
import helpers.stats as _stats
from middleware.security import SecurityHeadersMiddleware
from routes.injuries import CBS_INJURIES_FILE
from routes.injuries import router as injuries_router
from routes.players import router as players_router
from routes.scores import router
from routes.season import router as season_router
from routes.trades import router as trades_router

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
    # Validate env var bounds (_safe_int_env already floors both at 1)
    workers = _common._DEFAULT_WORKERS
    if workers > 100:
        logger.warning("EXECUTOR_WORKERS=%d is above the maximum 100", workers)
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
    try:
        _common.cache.set("_hc", True, 1)
        _common.cache.get("_hc")
        return {"status": "ok"}
    except Exception as e:
        logger.warning("Health check failed: %s", e)
        return JSONResponse({"status": "degraded"}, status_code=503)


# Serve web files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
if os.path.exists(static_dir):
    app.mount("/web", StaticFiles(directory=static_dir), name="web")


@app.get("/t/a.js")
async def analytics_stub():  # pragma: no cover
    """Dev stub — in production Caddy proxies /t/a.js to the analytics server."""
    return Response(content="", media_type="application/javascript")


@app.get("/sw.js")
async def serve_service_worker():  # pragma: no cover
    """Serve the service worker from the root — a worker's scope is its own
    directory, so /web/sw.js could never control the app served at /."""
    sw_path = os.path.join(static_dir, "sw.js")
    if os.path.exists(sw_path):
        return FileResponse(
            sw_path,
            media_type="application/javascript",
            # Always revalidate: a cached worker script keeps serving its old
            # version, so a fix here would never reach an existing install.
            headers={"Cache-Control": "no-cache"},
        )
    raise HTTPException(status_code=404, detail="Service worker not found")


@app.get("/sitemap.xml")
async def serve_sitemap():  # pragma: no cover
    """Serve sitemap.xml"""
    sitemap_path = os.path.join(static_dir, "sitemap.xml")
    if os.path.exists(sitemap_path):
        return FileResponse(sitemap_path, media_type="application/xml")
    raise HTTPException(status_code=404, detail="Sitemap not found")


@app.get("/")
async def serve_frontend():  # pragma: no cover
    index_path = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404)
    return FileResponse(index_path)


if __name__ == "__main__":  # pragma: no cover
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        # One worker: SimpleCache is in-process, so each extra worker is a
        # separate cache and another multiplier on stats.nba.com calls.
        workers=1,
    )
