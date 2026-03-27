# NBA API constants - column indices and magic numbers centralized for maintainability

# NBA season constants
NBA_REGULAR_SEASON_GAMES = 82  # Number of games in a regular NBA season

# Column index constants for NBA API responses:
# CommonAllPlayers columns
CAP_PERSON_ID = 0
CAP_DISPLAY_LAST_COMMA_FIRST = 1
CAP_TEAM_ID = 7

# BoxScoreTraditionalV3 player_stats columns
BS_PLAYER_ID = 6
BS_MINUTES = 14
BS_FGM = 15
BS_FGA = 16
BS_FG3M = 18
BS_FG3A = 19
BS_FTM = 21
BS_FTA = 22
BS_REB = 26
BS_AST = 27
BS_BLK = 28
BS_STL = 29
BS_PF = 31
BS_PTS = 32

# PlayerGameLog columns (SEASON_ID, PLAYER_ID, GAME_ID, GAME_DATE, MATCHUP, ...)
PGL_GAME_ID = 2
PGL_GAME_DATE = 3
PGL_MATCHUP = 4

# LeagueStandings columns
ST_TEAM_ID = 2
ST_CITY = 3
ST_NAME = 4
ST_CONF = 5
ST_RANK = 7
ST_WINS = 12
ST_LOSSES = 13
ST_WIN_PCT = 14
ST_HOME_RECORD = 17
ST_AWAY_RECORD = 18
ST_L10 = 19
ST_STREAK = 36
ST_GAMES_BACK = 37
