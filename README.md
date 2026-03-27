## nba_stables - NBA Live Stats & Tables

![Python](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
[![codecov](https://codecov.io/gh/sreckoskocilic/nba_stables/branch/main/graph/badge.svg)](https://codecov.io/gh/sreckoskocilic/nba_stables)

## Features

- **Live Scoreboard** - Real-time scores with game clock, status, and leading scorers
- **Box Scores** - Detailed team stats for any game (supports browsing past 7 days)
- **Daily Leaders** - Top performers per stat category across all games
- **Player Tracker** - Search and track specific players with live stats and advanced metrics
- **Last N Games** - Per-player performance over the last N games (up to 15)
- **Player Season Averages** - Current season averages for any player (points, rebounds, assists, etc.)
- **Game Players** - Full player stats for any game with advanced metrics (offensive/defensive rebounds, turnovers, fouls)
- **Playoffs** - Current playoff picture with projected seedings
- **Standings** - Conference standings with W/L, streak, home/away splits
- **Injury Report** - Current NBA injury data sourced from CBS Sports
- **Trades & Player Movement** - Latest NBA transactions (trades, signings, waivers) with 6-month history and color-coded contract highlights
- **Season Highs** - Season single-game highs for each statistical category (points, rebounds, 3-pointers, etc.)
- **Season Doubles & Triples** - Top 30 double-double and top 20 triple-double leaders this season, with expandable per-game triple-double details

## Tech Stack

- **Backend**: FastAPI + uvicorn (Python 3.12+)
- **Frontend**: Vanilla JS SPA, PWA-ready (installable, service worker)
- **Data**: `nba_api` library for live stats; CBS Sports scraping for injuries
- **Caching**: In-memory cache with tiered TTLs (30s live → 24h historical)
- **Deployment**: Docker + Caddy reverse proxy; automated via GitHub Actions

## Running Locally

### Prerequisites

- Python 3.12+
- pip

### Setup

```bash
git clone https://github.com/sreckoskocilic/nba_stables.git
cd nba_stables
pip install -r requirements.txt
```

### Start the web app

```bash
cd api
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

### Running Tests

```bash
# Run all tests
python -m pytest

# Run with verbose output
python -m pytest -v

# Run with coverage report
python -m pytest --cov=api --cov-report=term-missing

# Run a specific test file
python -m pytest tests/test_helpers_stats.py

# Run a specific test class or test
python -m pytest tests/test_integration.py::TestInjuries
python -m pytest tests/test_integration.py::TestInjuries::test_returns_data_from_file
```

### Docker

```bash
docker-compose --profile dev up -d --build
```

## Statistics Reference

### Player Stats

| Stat | Full Name | Description |
|------|-----------|-------------|
| **MIN** | Minutes Played | Time on court (MM:SS) |
| **PTS** | Points | Total points scored |
| **FG** | Field Goals | Made/Attempted field goals |
| **3PT** | Three-Pointers | Made/Attempted three-point field goals |
| **FT** | Free Throws | Made/Attempted free throws |
| **REB** | Rebounds | Total rebounds (offensive + defensive) |
| **AST** | Assists | Passes leading directly to a made basket |
| **BLK** | Blocks | Shots blocked |
| **STL** | Steals | Turnovers forced by taking the ball |

### Team Stats (Box Score)

| Stat | Full Name | Description |
|------|-----------|-------------|
| **FG** | Field Goals | Made/Attempted (excludes free throws) |
| **FG%** | Field Goal % | Shooting percentage |
| **3PT** | Three-Pointers | Made/Attempted from beyond the arc |
| **3P%** | Three-Point % | Three-point shooting percentage |
| **FT** | Free Throws | Made/Attempted free throws |
| **FT%** | Free Throw % | Free throw shooting percentage |
| **REB** | Rebounds | Total team rebounds |
| **AST** | Assists | Total team assists |
| **STL** | Steals | Total team steals |
| **BLK** | Blocks | Total team blocks |
| **TOV** | Turnovers | Total team turnovers |
