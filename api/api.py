"""
NBA Stables REST API
FastAPI backend for live NBA statistics
"""

import json
import logging
import os
import sys

import yaml

sys.path.append(os.getcwd())

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from helpers.common import CACHE_TTL, SimpleCache
from helpers.stats import get_display_date
from routes.nba import router

# SOCKS5 proxy for stats.nba.com (Cloudflare WARP on the host)
STATS_PROXY = os.environ.get("STATS_PROXY", None)

app = FastAPI(
    title="NBA Stables API",
    description="Live NBA statistics API",
    version="1.0.0",
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

# sys.path.append(os.path.dirname(os.path.abspath(__file__)))
app.include_router(router)

CBS_INJURIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../cbs_injuries.json")
LOG_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log_config.yml")
cache = SimpleCache()

if not os.path.exists("../logs"):
    os.makedirs("../logs")

def setup_logging(config_path=LOG_CONFIG_FILE):
    with open(config_path, 'r') as f:
        logging.config.dictConfig(yaml.safe_load(f.read()))

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

    try:
        if not os.path.exists(CBS_INJURIES_FILE):
            raise HTTPException(status_code=503, detail="CBS injuries data not available")
        with open(CBS_INJURIES_FILE, "r", encoding="utf-8") as f:
            result = json.load(f)
        cache.set("injuries", result, CACHE_TTL["injuries"])
        return result
    except Exception as e:
        from api.helpers.logger import log_exceptions
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


# Serve static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


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
    uvicorn.run("api:app", host="0.0.0.0", port=8000, workers=4)
