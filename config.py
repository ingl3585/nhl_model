# config.py
# Central configuration for NHL Monte Carlo Model
# Edit this file only — never touch nhl_monte_carlo.py again

from datetime import datetime

# =============================================================================
# AUTO-DETECTED VALUES (no need to change)
# =============================================================================
TODAY = datetime.now()
CURRENT_SEASON_START_YEAR = 2025 if TODAY.month >= 7 else 2024
CURRENT_SEASON_END_YEAR = CURRENT_SEASON_START_YEAR + 1
CURRENT_SEASON_FULL = f"{CURRENT_SEASON_START_YEAR}-{CURRENT_SEASON_END_YEAR}"
SEASON_CODE = str(CURRENT_SEASON_END_YEAR) # Hockey-Reference uses end year
TODAY_STR = TODAY.strftime("%Y-%m-%d")
TODAY_PRETTY = TODAY.strftime("%B %d, %Y")

# =============================================================================
# FILE NAMES & PATHS
# =============================================================================
DB_FILE = f"data/db/nhl_{CURRENT_SEASON_START_YEAR}_{CURRENT_SEASON_END_YEAR}_players.db"
SCHEDULE_CSV = f"data/schedule/schedule_{CURRENT_SEASON_START_YEAR}_{CURRENT_SEASON_END_YEAR}.csv"
PREDICTIONS_CSV = f"data/results/nhl_predictions_{TODAY.strftime('%Y%m%d')}.csv"

# =============================================================================
# SIMULATION SETTINGS
# =============================================================================
N_SIMS_FULL = 26                       # Full season simulations
N_SIMS_TODAY = 13                      # Simulations per today's game
HOME_ICE_ADVANTAGE = 1.10
LEAGUE_AVG_XG_PER_60 = 2.95
OT_HOME_WIN_PROB = 0.55                # Historical: ~55% of OT/SO won by home team

# =============================================================================
# DATA FILTERS
# =============================================================================
MIN_TOI_MINUTES = 60                   # Players must have >60 min 5v5 TOI
FALLBACK_OFFENSIVE_RATING = 2.80       # xGF/60 if no data
FALLBACK_DEFENSIVE_RATING = 2.80       # xGA/60 if no data

# =============================================================================
# DISPLAY SETTINGS
# =============================================================================
SHOW_TODAYS_GAMES = True
SHOW_ROSTER_DUMP = False               # Set True if you want full roster print
SHOW_PROGRESS_EVERY = 2000             # Print progress every N sims

# =============================================================================
# TEAM NAME FIXES (only edit if NST changes format)
# =============================================================================
TEAM_ABBREV_FIXES = {
    "L.A": "Los Angeles Kings",
    "N.J": "New Jersey Devils",
    "T.B": "Tampa Bay Lightning",
    "S.J": "San Jose Sharks",
}

print(f"Config loaded → Season {CURRENT_SEASON_FULL} | Today: {TODAY_PRETTY}")