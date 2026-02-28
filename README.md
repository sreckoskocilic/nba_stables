## nba_stables - NBA Live Stats & Tables

![Python](https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
[![codecov](https://codecov.io/gh/sreckoskocilic/nba_stables/branch/main/graph/badge.svg)](https://codecov.io/gh/sreckoskocilic/nba_stables)

## Features

- **Live Scoreboard** - Real-time scores with game clock, status, and leading scorers
- **Box Scores** - Detailed team stats for any game (supports browsing past 7 days)
- **Daily Leaders** - Top performers per stat category across all games
- **Player Tracker** - Search and track specific players with live stats and advanced metrics
- **Last N Games** - Per-player performance over the last N games (up to 15)
- **Season Averages** - Current season averages for any player
- **Double/Triple Doubles** - Automatic detection and dedicated tracking endpoint
- **Playoffs** - Current playoff picture with projected seedings
- **Standings** - Conference standings with W/L, streak, home/away splits
- **Injury Report** - Current NBA injury data sourced from CBS Sports

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

### Docker

```bash
docker-compose --profile dev up -d --build
```

## API Endpoints

### NBA Stats

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/dates` | Date labels for day offset buttons (0–7) |
| GET | `/api/scoreboard` | Live scores with leading scorers |
| GET | `/api/boxscores` | Box scores (`?days_offset=0-7`) |
| GET | `/api/leaders` | Daily stat leaders (`?days_offset=0-7`) |
| GET | `/api/standings` | East/West conference standings |
| GET | `/api/playoffs` | Playoff picture with projected seedings |
| GET | `/api/doubledoubles` | DD/TD tracker (`?days_offset=0-7`) |
| GET | `/api/injuries` | CBS Sports injury report |

### Players

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/players/search?q={query}` | Search players by name |
| GET | `/api/players/stats?ids={ids}` | Live stats for specific players |
| GET | `/api/players/advanced?ids={ids}` | Advanced stats (TS%, eFG%, +/-, DD/TD) |
| GET | `/api/players/{id}/last-n-games` | Last N games stats (default 5, max 15) |
| GET | `/api/players/{id}/season-avg` | Current season averages |
| GET | `/api/games/{game_id}/players` | All player stats for a game |

## Statistics Reference

### Player Stats

| Stat | Full Name | Description |
|------|-----------|-------------|
| **PT** | Points | Total points scored |
| **3P** | Three-Pointers | Made/Attempted three-point field goals |
| **RB** | Rebounds | Total rebounds (offensive + defensive) |
| **AS** | Assists | Passes leading directly to a made basket |
| **BL** | Blocks | Shots blocked |
| **ST** | Steals | Turnovers forced by taking the ball |
| **TO** | Turnovers | Times the player lost possession |
| **TIME** | Minutes Played | Time on court (MM:SS) |
| **TS%** | True Shooting % | Scoring efficiency including free throws |
| **eFG%** | Effective FG% | Adjusts for 3-pointers being worth more |
| **+/-** | Plus/Minus | Point differential while player is on court |

### Team Stats (Box Score)

| Stat | Full Name | Description |
|------|-----------|-------------|
| **FG** | Field Goals | Made/Attempted (excludes free throws) |
| **FG%** | Field Goal % | Shooting percentage |
| **3P** | Three-Pointers | Made/Attempted from beyond the arc |
| **3P%** | Three-Point % | Three-point shooting percentage |
| **FT** | Free Throws | Made/Attempted free throws |
| **FT%** | Free Throw % | Free throw shooting percentage |
| **RB** | Rebounds | Total team rebounds |
| **ORB** | Offensive Rebounds | Rebounds of own team's missed shots |
| **AST** | Assists | Total team assists |
| **ST** | Steals | Total team steals |
| **BL** | Blocks | Total team blocks |
| **TO** | Turnovers | Total team turnovers |
| **PF** | Personal Fouls | Total team fouls committed |
