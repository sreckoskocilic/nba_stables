## nba_stables - NBA Live Stats Tables

I have a strange habit to listen to NBA live streams on nba.com while doing something else on my laptop. In order to
stay updated with latest results I have to click through all active games to check the stats. That led me to an idea to 
show desired stats in one webpage and make them easy to read.

## Statistics Reference

### Player Stats (Individual Performance)

| Stat | Full Name | Description |
|------|-----------|-------------|
| **PT** | Points | Total points scored (2PT + 3PT + FT) |
| **3P** | Three-Pointers | Made/Attempted three-point field goals |
| **RB** | Rebounds | Total rebounds (offensive + defensive) |
| **AS** | Assists | Passes leading directly to a made basket |
| **BL** | Blocks | Shots blocked by the defender |
| **ST** | Steals | Turnovers forced by taking the ball from opponent |
| **TO** | Turnovers | Times the player lost possession |
| **TIME** | Minutes Played | Total time on court (MM:SS format) |

### Team Stats (Box Score)

| Stat | Full Name | Description |
|------|-----------|-------------|
| **FG** | Field Goals | Made/Attempted shots (excludes free throws) |
| **FG%** | Field Goal % | Percentage of made field goals |
| **3P** | Three-Pointers | Made/Attempted shots from beyond the arc |
| **3P%** | Three-Point % | Percentage of made three-pointers |
| **FT** | Free Throws | Made/Attempted free throws |
| **FT%** | Free Throw % | Percentage of made free throws |
| **RB** | Rebounds | Total team rebounds |
| **ORB** | Offensive Rebounds | Rebounds of own team's missed shots |
| **AST** | Assists | Total team assists |
| **ST** | Steals | Total team steals |
| **BL** | Blocks | Total team blocks |
| **TO** | Turnovers | Total team turnovers |
| **PF** | Personal Fouls | Total team fouls committed |

### Potential Future Statistics

These stats are available from the NBA API and could be added:

| Stat | Description |
|------|-------------|
| **+/-** | Plus/Minus - Point differential while player is on court |
| **PER** | Player Efficiency Rating - Overall performance metric |
| **TS%** | True Shooting % - Scoring efficiency including FT |
| **eFG%** | Effective FG% - Adjusts for 3PT being worth more |
| **USG%** | Usage Rate - % of team plays used by player |
| **DD/TD** | Double-Double / Triple-Double tracking |
| **PIE** | Player Impact Estimate |
| **OREB/DREB** | Offensive/Defensive rebounds separately |
| **FBP** | Fast Break Points |
| **PITP** | Points in the Paint |
| **2CP** | Second Chance Points |
| **BP** | Bench Points |

## Running Locally

### Prerequisites

- Python 3.9+
- pip

### Setup

```bash
git clone https://github.com/sreckoskocilic/nba_stables.git
cd nba_stables
pip install -r requirements.txt
```

### Start the web app

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

### Docker

```bash
docker-compose --profile dev up -d --build
```

### Features

- Live Scoreboard - Real-time scores with game times in CET
- Box Scores - Detailed team stats with top performers
- Daily Leaders - Top performers per stat category
- Player Tracker - Search and track specific players live
- Standings - Conference standings
- Injury Report