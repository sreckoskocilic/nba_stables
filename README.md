## nbastables.com — NBA Live Stats & Tables

[nbastables.com](https://nbastables.com) is a web portal for following NBA statistics in real time.

## Features

- **Live Scoreboard** — real-time scores with game clock, status, and leading scorers
- **Box Scores** — detailed team stats for any game (browse the past 7 days)
- **Daily Leaders** — top performers per stat category across all games
- **Player Tracker** — search and track players with live stats and advanced metrics
- **Last N Games** — per-player performance over the last N games (up to 15)
- **Player Season Averages** — current-season averages for any player
- **Game Players** — full player stats per game with advanced metrics (offensive/defensive rebounds, turnovers, fouls)
- **Playoffs** — current playoff picture with projected seedings
- **Standings** — conference standings (W/L, streak, home/away splits)
- **Injury Report** — current NBA injury data sourced from CBS Sports
- **Trades & Player Movement** — latest NBA transactions (trades, signings, waivers) with 6-month history
- **Season Highs** — single-game season highs per stat category
- **Season Doubles & Triples** — top 30 double-double and top 20 triple-double leaders this season

## Tech

- **Backend**: FastAPI + uvicorn (Python 3.12+)
- **Frontend**: vanilla JS SPA, PWA-ready (installable, service worker)
- **Data**: `nba_api` for live stats; CBS Sports scraping for injuries
- **Caching**: in-memory cache with tiered TTLs (30s live → 24h historical)
- **Deployment**: Docker + Caddy reverse proxy, deployed via GitHub Actions
