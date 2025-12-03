# config.py
# Central configuration for NHL Monte Carlo Model

from datetime import datetime

# =============================================================================
# AUTO-GENERATED VALUES
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
N_SIMS_FULL = 1                       # Full season simulations
N_SIMS_TODAY = 25000                     # Simulations per today's game
HOME_ICE_ADVANTAGE = 1.10
LEAGUE_AVG_XG_PER_60 = 2.95
OT_HOME_WIN_PROB = 0.55                # Historical: ~55% of OT/SO won by home team
TEAM_STRENGTH_VARIANCE = 0.15          # ±9% game-to-game variance (injuries, form, etc.)

# Position weights for team strength calculations (must sum to 1.0)
FORWARD_OFFENSE_WEIGHT = 0.85          # Forwards drive 85% of offense
DEFENSE_OFFENSE_WEIGHT = 0.15          # Defensemen contribute 15% to offense
FORWARD_DEFENSE_WEIGHT = 0.20          # Forwards contribute 20% to defense
DEFENSE_DEFENSE_WEIGHT = 0.30          # Defensemen contribute 30% to defense
GOALIE_DEFENSE_WEIGHT = 0.50           # Goalies contribute 50% to defense

# =============================================================================
# DATA FILTERS
# =============================================================================
MIN_TOI_MINUTES = 20                   # Players must have >60 min 5v5 TOI
FALLBACK_OFFENSIVE_RATING = 2.80       # xGF/60 if no data
FALLBACK_DEFENSIVE_RATING = 2.80       # xGA/60 if no data

# =============================================================================
# RECENT FORM WEIGHTING
# =============================================================================
RECENT_FORM_WEIGHT = 0.60  # 60% recent (last 10 games), 40% full season
                           # Set to 0.5 for equal weight, 1.0 for recent only

# =============================================================================
# EXPECTED GOALS vs ACTUAL GOALS BLENDING
# =============================================================================
ACTUAL_GOALS_WEIGHT = 0.30  # 30% actual goals (GF/60, GA/60, GAA)
XG_WEIGHT = 0.70            # 70% expected goals (xGF/60, xGA/60)
                            # Higher xG weight = more predictive, less reactive
                            # Higher actual weight = rewards current performance

# =============================================================================
# DISPLAY SETTINGS
# =============================================================================
SHOW_TODAYS_GAMES = True
SHOW_ROSTER_DUMP = True               # Set True if you want full roster print
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