"""
NBA Stables REST API
FastAPI backend for live NBA statistics
"""

import json
import logging.config
import os

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from helpers.common import CACHE_TTL, cache
from helpers.stats import get_display_date
from routes.players import router as players_router
from routes.scores import router

app = FastAPI(
    title="NBA Stables API",
    description="Live NBA statistics API",
    version="1.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# sys.path.append(os.path.dirname(os.path.abspath(__file__)))
app.include_router(router)
app.include_router(players_router)

CBS_INJURIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static/cbs_injuries.json")
LOG_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log_config.yml")
with open(LOG_CONFIG_FILE, 'r') as f:
    logging.config.dictConfig(yaml.safe_load(f.read()))

if not os.path.exists("../logs"):
    os.makedirs("../logs")


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "date": get_display_date(0)}


@app.get("/api/injuries")
def get_injuries():
    """Get NBA injury report from CBS Sports"""
    cached = cache.get("injuries")
    if cached:
        return cached

    if not os.path.exists(CBS_INJURIES_FILE):
        raise HTTPException(status_code=503, detail="CBS injuries data not available")
    try:
        with open(CBS_INJURIES_FILE, "r", encoding="utf-8") as f:
            result = json.load(f)
        cache.set("injuries", result, CACHE_TTL["injuries"])
        return result
    except Exception as e:
        from helpers.logger import log_exceptions
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


# Serve web files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
if os.path.exists(static_dir):
    app.mount("/web", StaticFiles(directory=static_dir), name="web")


@app.get("/sitemap.xml")
async def serve_sitemap():
    """Serve sitemap.xml"""
    sitemap_path = os.path.join(static_dir, "sitemap.xml")
    if os.path.exists(sitemap_path):
        return FileResponse(sitemap_path, media_type="application/xml")
    raise HTTPException(status_code=404, detail="Sitemap not found")


@app.get("/about")
async def serve_about():
    """Serve the about page"""
    about_path = os.path.join(static_dir, "about.html")
    if os.path.exists(about_path):
        return FileResponse(about_path)
    raise HTTPException(status_code=404, detail="Page not found")


@app.get("/")
async def serve_frontend():
    """Serve the frontend"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "NBA Stables API", "docs": "/docs"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, workers=4, reload=True, reload_includes="*.json")
