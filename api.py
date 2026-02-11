"""
NBA Stables REST API
FastAPI backend for live NBA statistics
"""

import json
import os
from datetime import date, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from isodate import parse_duration
from nba_api.live.nba.endpoints import boxscore, scoreboard
from nba_api.stats.endpoints import boxscoretraditionalv3, scoreboardv2

app = FastAPI(
    title="NBA Stables API",
    description="Live NBA statistics API",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PLAYERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "players_with_teamid.json")


# Helper functions
def get_date_str(days_offset: int = 0) -> str:
    target_date = date.today() - timedelta(days=days_offset)
    return target_date.strftime("%Y-%m-%d")


def get_display_date(days_offset: int = 0) -> str:
    target_date = date.today() - timedelta(days=days_offset)
    return target_date.strftime("%B %d, %Y")


def reformat_player_minutes(total_seconds: int) -> str:
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def load_players_file():
    with open(PLAYERS_FILE, "r") as f:
        return json.load(f)


def get_games_list(days_offset: int = 1):
    """Get list of game IDs for a given date offset"""
    g_dict = []
    target_date = date.today() - timedelta(days=days_offset)
    try:
        sb = scoreboardv2.ScoreboardV2(game_date=target_date.strftime("%Y-%m-%d"))
        games = sb.game_header.get_dict()
        for g in games["data"]:
            g_dict.append(g[2])  # game_id is at index 2
    except Exception:
        pass
    return list(set(g_dict))


def get_games_leaders_list(days_offset: int = 1):
    """Get games with their leaders"""
    g_dict = {}
    target_date = date.today() - timedelta(days=days_offset)
    try:
        sb = scoreboardv2.ScoreboardV2(game_date=target_date.strftime("%Y-%m-%d"))
        games = sb.game_header.get_dict()
        leaders = sb.team_leaders.get_dict()

        # Get game IDs
        for g in games["data"]:
            game_id = g[2]
            g_dict[game_id] = []

        # Get leaders for each game (leaders data structure: game_id, team_id, player_id, player_name, pts, reb, ast...)
        for ld in leaders["data"]:
            game_id = ld[0]
            if game_id in g_dict:
                player_name = ld[4] if len(ld) > 4 else ""
                pts = ld[5] if len(ld) > 5 else 0
                reb = ld[6] if len(ld) > 6 else 0
                ast = ld[7] if len(ld) > 7 else 0
                g_dict[game_id].append([player_name, pts, reb, ast])
    except Exception:
        pass
    return g_dict


# API Endpoints

@app.get("/api/scoreboard")
async def get_scoreboard():
    """Get live scoreboard with game results and leading scorers"""
    try:
        games = []
        for game in scoreboard.ScoreBoard().games.data:
            home_team = game["homeTeam"]
            away_team = game["awayTeam"]
            home_leaders = game["gameLeaders"]["homeLeaders"]
            away_leaders = game["gameLeaders"]["awayLeaders"]

            games.append({
                "gameId": game["gameId"],
                "status": game["gameStatusText"],
                "homeTeam": {
                    "name": "{} {}".format(home_team["teamCity"], home_team["teamName"]),
                    "tricode": home_team["teamTricode"],
                    "score": home_team["score"],
                    "leader": {
                        "name": home_leaders["name"],
                        "points": home_leaders["points"],
                        "rebounds": home_leaders["rebounds"],
                        "assists": home_leaders["assists"]
                    }
                },
                "awayTeam": {
                    "name": "{} {}".format(away_team["teamCity"], away_team["teamName"]),
                    "tricode": away_team["teamTricode"],
                    "score": away_team["score"],
                    "leader": {
                        "name": away_leaders["name"],
                        "points": away_leaders["points"],
                        "rebounds": away_leaders["rebounds"],
                        "assists": away_leaders["assists"]
                    }
                }
            })

        return {"games": games, "date": get_display_date(0)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/boxscores")
async def get_boxscores(days_offset: int = Query(default=1, ge=0, le=7)):
    """Get detailed box scores for games"""
    try:
        boxscores_list = []

        # Use the helper function to get games with leaders
        leaders_by_game = get_games_leaders_list(days_offset)

        for game_id, leaders_data in leaders_by_game.items():
            try:
                bs_stats = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
            except Exception:
                continue

            if bs_stats is None:
                continue

            team_stats = bs_stats.team_stats.get_dict()["data"]
            game_box = {"gameId": game_id, "teams": []}

            for i, team in enumerate(team_stats):
                # leaders_data is list of [name, points, rebounds, assists]
                leader = {"name": "", "points": 0, "rebounds": 0, "assists": 0}
                if i < len(leaders_data):
                    ld = leaders_data[i]
                    leader = {"name": ld[0], "points": ld[1], "rebounds": ld[2], "assists": ld[3]}

                game_box["teams"].append({
                    "name": "{} {}".format(team[2], team[3]),
                    "score": team[-2],
                    "stats": {
                        "fg": "{}/{}".format(team[7], team[8]),
                        "fgPct": team[9],
                        "threePt": "{}/{}".format(team[10], team[11]),
                        "threePtPct": team[12],
                        "ft": "{}/{}".format(team[13], team[14]),
                        "ftPct": team[15],
                        "rebounds": team[18],
                        "offRebounds": team[16],
                        "assists": team[19],
                        "steals": team[20],
                        "blocks": team[21],
                        "turnovers": team[22],
                        "fouls": team[23]
                    },
                    "leader": leader
                })

            boxscores_list.append(game_box)

        return {"boxscores": boxscores_list, "date": get_display_date(days_offset)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/players/search")
async def search_players(q: str = Query(..., min_length=2)):
    """Search for players by name"""
    try:
        players = load_players_file()
        results = []
        query = q.lower()

        for player in players:
            if query in player[1].lower():
                results.append({
                    "id": player[0],
                    "name": player[1],
                    "teamId": player[2]
                })

        return {"players": results[:20]}  # Limit to 20 results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/players/stats")
async def get_player_stats(ids: str = Query(..., description="Comma-separated player IDs")):
    """Get live stats for specific players"""
    try:
        player_ids = [int(pid.strip()) for pid in ids.split(",")]
        players_data = load_players_file()

        # Get team IDs for requested players
        team_ids = []
        for pid in player_ids:
            player = next((p for p in players_data if p[0] == pid), None)
            if player and player[2] and player[2] not in team_ids:
                team_ids.append(player[2])

        results = []

        for game in scoreboard.ScoreBoard().games.data:
            if game["homeTeam"]["teamId"] in team_ids or game["awayTeam"]["teamId"] in team_ids:
                try:
                    bs = boxscore.BoxScore(game_id=game["gameId"]).get_dict()
                except Exception:
                    continue

                for team_key in ["homeTeam", "awayTeam"]:
                    team = bs["game"][team_key]
                    for player in team["players"]:
                        if player["personId"] in player_ids and player["status"] == "ACTIVE":
                            stats = player["statistics"]
                            try:
                                minutes = reformat_player_minutes(
                                    int(parse_duration(stats["minutes"]).total_seconds())
                                )
                            except Exception:
                                minutes = "0:00"

                            results.append({
                                "id": player["personId"],
                                "name": player["name"],
                                "team": team["teamTricode"],
                                "minutes": minutes,
                                "points": stats["points"],
                                "threePointers": "{}/{}".format(stats["threePointersMade"], stats["threePointersAttempted"]),
                                "rebounds": stats["reboundsTotal"],
                                "assists": stats["assists"],
                                "blocks": stats["blocks"],
                                "steals": stats["steals"],
                                "turnovers": stats["turnovers"]
                            })

        return {"players": results}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid player IDs format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leaders")
async def get_daily_leaders(days_offset: int = Query(default=1, ge=0, le=7)):
    """Get daily leaders across statistical categories"""
    try:
        # Get game IDs using helper function
        game_ids = get_games_list(days_offset)

        all_players = []

        for gid in game_ids:
            try:
                bs = boxscore.BoxScore(game_id=gid).get_dict()
            except Exception:
                continue

            for team_key in ["homeTeam", "awayTeam"]:
                team = bs["game"][team_key]
                tricode = team["teamTricode"]

                for player in team["players"]:
                    if player["status"] == "ACTIVE":
                        stats = player["statistics"]
                        all_players.append({
                            "name": player["name"],
                            "team": tricode,
                            "points": stats["points"],
                            "rebounds": stats["reboundsTotal"],
                            "assists": stats["assists"],
                            "blocks": stats["blocks"],
                            "steals": stats["steals"],
                            "threePointers": stats["threePointersMade"]
                        })

        categories = [
            ("points", "Points"),
            ("rebounds", "Rebounds"),
            ("assists", "Assists"),
            ("blocks", "Blocks"),
            ("steals", "Steals"),
            ("threePointers", "3-Pointers")
        ]

        leaders = {}
        for key, label in categories:
            if all_players:
                max_val = max(p[key] for p in all_players)
                top_players = [p for p in all_players if p[key] == max_val]
                leaders[key] = {
                    "label": label,
                    "value": max_val,
                    "players": [{"name": p["name"], "team": p["team"]} for p in top_players]
                }

        return {"leaders": leaders, "date": get_display_date(days_offset)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "date": get_display_date(0)}


# Serve static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the frontend"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "NBA Stables API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
