## nba_stables - NBA Live Stats Tables

I have a strange habit to listen to NBA live streams on nba.com while doing something else on my laptop. In order to
stay updated with latest results I have to click through all active games to check the stats and usually get
lost in sudden burst of numbers and stats. So I decided to make custom NBA Live Stats scripts to get the preferred stats
with only one click (one script execution). This repository is a collection of such live stats scripts all resulting in
drawing a table in terminal with most interesting stats for that evening.

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

## Installation

Install required packages with pip:

```
pip install -r requirements.txt
```

## Web Interface

Run the web server:

```
python api.py
```

Then open http://localhost:8000 in your browser.

**Features:**
- Live Scoreboard - Real-time game scores and top performers
- Box Scores - Detailed team statistics
- Daily Leaders - Top performers in each stat category
- Player Tracker - Search and track specific players

## Docker Deployment

```bash
# Build and run with docker-compose
docker-compose up -d

# Or build manually
docker build -t nba-stables .
docker run -d -p 8000:8000 nba-stables
```

Then open http://localhost:8000

### Deploy to a VPS

```bash
# On your server (DigitalOcean, Linode, etc.)
git clone <your-repo>
cd nba_stables
docker-compose up -d
```

## Terminal Scripts

There is an updated players static list with teamID added to each player that has played at least one game this season.

```
>>>  python results.py
╒════════════════════╤═══════╤══════════╤═══════════════════╤═════╤═════╤═════╕
│                    │ Score │ Status   │ Lead Player       │ PTS │ REB │ AST │
├────────────────────┼───────┼──────────┼───────────────────┼─────┼─────┼─────┤
│ New York Knicks    │   134 │ Final/OT │ Jalen Brunson     │  40 │   5 │   8 │
│ Indiana Pacers     │   137 │          │ Pascal Siakam     │  30 │   6 │   4 │
├────────────────────┼───────┼──────────┼───────────────────┼─────┼─────┼─────┤
│ Houston Rockets    │   102 │ Final    │ Kevin Durant      │  26 │   6 │   3 │
│ LA Clippers        │    95 │          │ Kawhi Leonard     │  24 │   8 │   3 │
├────────────────────┼───────┼──────────┼───────────────────┼─────┼─────┼─────┤
│ Phoenix Suns       │   120 │ Final    │ Devin Booker      │  19 │   4 │   6 │
│ Dallas Mavericks   │   111 │          │ Naji Marshall     │  31 │   4 │   2 │
├────────────────────┼───────┼──────────┼───────────────────┼─────┼─────┼─────┤
│ Los Angeles Lakers │   108 │ Final    │ Luke Kennard      │  14 │   2 │   5 │
│ San Antonio Spurs  │   136 │          │ Victor Wembanyama │  40 │  12 │   2 │
╘════════════════════╧═══════╧══════════╧═══════════════════╧═════╧═════╧═════╛
```

```
>>> python boxscore.py
╒═══════════════════════════╤═══════╤════════╤═══════╤═══════╤═══════╤═══════╤═══════╤════╤═════╤═════╤════╤════╤════╤════╤═══════════════╤════╤════╤════╕
│                           │ Score │ FG     │ FG %  │ 3P    │ 3P %  │ FT    │ FT %  │ RB │ ORB │ AST │ ST │ BL │ TO │ PF │ Lead Player   │ PT │ RB │ AS │
├───────────────────────────┼───────┼────────┼───────┼───────┼───────┼───────┼───────┼────┼─────┼─────┼────┼────┼────┼────┼───────────────┼────┼────┼────┤
│ New York Knicks           │ 134   │ 50/100 │ 0.5   │ 14/46 │ 0.304 │ 20/27 │ 0.741 │ 46 │ 8   │ 33  │ 4  │ 4  │ 12 │ 30 │ Jalen Brunson │ 40 │ 5  │ 8  │
├───────────────────────────┼───────┼────────┼───────┼───────┼───────┼───────┼───────┼────┼─────┼─────┼────┼────┼────┼────┼───────────────┼────┼────┼────┤
│ Indiana Pacers            │ 137   │ 50/97  │ 0.515 │ 18/45 │ 0.4   │ 19/26 │ 0.731 │ 43 │ 6   │ 30  │ 6  │ 4  │ 11 │ 23 │ Pascal Siakam │ 30 │ 6  │ 4  │
╘═══════════════════════════╧═══════╧════════╧═══════╧═══════╧═══════╧═══════╧═══════╧════╧═════╧═════╧════╧════╧════╧════╧═══════════════╧════╧════╧════╛

╒═══════════════════════════╤═══════╤═══════╤═══════╤═══════╤═══════╤═══════╤═══════╤════╤═════╤═════╤════╤════╤════╤════╤═══════════════╤════╤════╤════╕
│                           │ Score │ FG    │ FG %  │ 3P    │ 3P %  │ FT    │ FT %  │ RB │ ORB │ AST │ ST │ BL │ TO │ PF │ Lead Player   │ PT │ RB │ AS │
├───────────────────────────┼───────┼───────┼───────┼───────┼───────┼───────┼───────┼────┼─────┼─────┼────┼────┼────┼────┼───────────────┼────┼────┼────┤
│ Houston Rockets           │ 102   │ 36/79 │ 0.456 │ 14/28 │ 0.5   │ 16/18 │ 0.889 │ 44 │ 10  │ 19  │ 7  │ 5  │ 16 │ 15 │ Kevin Durant  │ 26 │ 6  │ 3  │
├───────────────────────────┼───────┼───────┼───────┼───────┼───────┼───────┼───────┼────┼─────┼─────┼────┼────┼────┼────┼───────────────┼────┼────┼────┤
│ LA Clippers               │ 95    │ 36/88 │ 0.409 │ 8/30  │ 0.267 │ 15/23 │ 0.652 │ 45 │ 17  │ 24  │ 11 │ 5  │ 11 │ 18 │ Kawhi Leonard │ 24 │ 8  │ 3  │
╘═══════════════════════════╧═══════╧═══════╧═══════╧═══════╧═══════╧═══════╧═══════╧════╧═════╧═════╧════╧════╧════╧════╧═══════════════╧════╧════╧════╛
```

### Player Tracking (Multiple Players Supported)

Track multiple players simultaneously by providing comma-separated player IDs:

```
>>> python player_live_stats.py -i "1627783, 1641705"
╒═════════════════════════════╤══════╤═══════╤════╤══════╤════╤════╤════╤════╤════╕
│ Player - ID                 │ TEAM │  TIME │ PT │   3P │ RB │ AS │ BL │ ST │ TO │
├─────────────────────────────┼──────┼───────┼────┼──────┼────┼────┼────┼────┼────┤
│ Pascal Siakam - 1627783     │  IND │ 36:57 │ 30 │ 3/10 │  6 │  4 │  0 │  3 │  1 │
├─────────────────────────────┼──────┼───────┼────┼──────┼────┼────┼────┼────┼────┤
│ Victor Wembanyama - 1641705 │  SAS │ 26:06 │ 40 │  4/6 │ 12 │  2 │  1 │  2 │  4 │
╘═════════════════════════════╧══════╧═══════╧════╧══════╧════╧════╧════╧════╧════╛
```

- daily_leaders_per_category prints the daily leader per category. In case there are more players sharing the top score
  for the category they will be all listed.

```
>>> python daily_leaders_per_category.py
╒═══════════════════════════╤════════════╤════╕
│ Jalen Brunson  (NYK)      │ POINTS     │ 40 │
├───────────────────────────┼────────────┼────┤
│ Victor Wembanyama  (SAS)  │ POINTS     │ 40 │
├───────────────────────────┼────────────┼────┤
│ Karl-Anthony Towns  (NYK) │ REBOUNDS   │ 14 │
├───────────────────────────┼────────────┼────┤
│ Josh Hart  (NYK)          │ ASSISTS    │ 11 │
├───────────────────────────┼────────────┼────┤
│ Daniel Gafford  (DAL)     │ BLOCKS     │  3 │
├───────────────────────────┼────────────┼────┤
│ Kris Dunn  (LAC)          │ STEALS     │  4 │
├───────────────────────────┼────────────┼────┤
│ Jalen Brunson  (NYK)      │ 3 POINTERS │  4 │
├───────────────────────────┼────────────┼────┤
│ Landry Shamet  (NYK)      │ 3 POINTERS │  4 │
├───────────────────────────┼────────────┼────┤
│ Quenton Jackson  (IND)    │ 3 POINTERS │  4 │
├───────────────────────────┼────────────┼────┤
│ Andrew Nembhard  (IND)    │ 3 POINTERS │  4 │
├───────────────────────────┼────────────┼────┤
│ Reed Sheppard  (HOU)      │ 3 POINTERS │  4 │
├───────────────────────────┼────────────┼────┤
│ Victor Wembanyama  (SAS)  │ 3 POINTERS │  4 │
├───────────────────────────┼────────────┼────┤
│ Royce O'Neale  (PHX)      │ 3 POINTERS │  4 │
╘═══════════════════════════╧════════════╧════╛
```
