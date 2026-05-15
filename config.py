# config.py
# Central configuration for NHL Monte Carlo Model

from datetime import datetime

# =============================================================================
# AUTO-GENERATED VALUES
# =============================================================================
TODAY = datetime.now()
# NHL season runs October-June. If we're in July-Dec, we're in the new season that starts this year.
# If we're in Jan-June, we're still in the season that started last year.
CURRENT_SEASON_START_YEAR = TODAY.year if TODAY.month >= 7 else TODAY.year - 1
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
N_SIMS_FULL = 1001                     # Full season simulations
N_SIMS_TODAY = 100001                  # Simulations per today's game
# HOME_ICE_ADVANTAGE removed - now using actual home/away player stats from NST
# Home advantage is built into the empirical performance differences between locations
LEAGUE_AVG_XG_PER_60 = 3.10            # All-situations league average (updated from 2.95 for 5v5)
OT_HOME_WIN_PROB = 0.51                # Empirical 2025-26: 49.1% (160/326). Historical ~51%.
TEAM_STRENGTH_VARIANCE = 0.15          # ±15% game-to-game variance (injuries, form, etc.)
GAME_PACE_VARIANCE = 0.08              # Shared game tempo variance; raises/lowers both teams' xG
SCORING_CORRELATION = 0.35             # Shared Poisson component; increases realistic tied-game rates
MIN_GAME_XG = 0.5                      # Floor for simulated regulation expected goals
MAX_GAME_XG = 6.0                      # Ceiling for simulated regulation expected goals
OT_ENDS_IN_GOAL_PROB = 0.67            # Probability overtime ends before shootout
OT_SKILL_WEIGHT = 0.30                 # Weight of regulation xG edge in OT winner probability
SHOOTOUT_HOME_WIN_PROB = 0.52          # Shootouts are close to coin flips

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
RECENT_GAMES_TGP = 25                  # Recent games window for "last N games" stats (e.g. 10, 25)
ACTIVE_ROSTER_WINDOW = 10             # Games window for active roster determination
ACTIVE_ROSTER_MIN_GP_PCT = 0.50       # Min fraction of window games to be considered active (e.g. 5/10)
MIN_GP_PERCENTAGE = 0.50               # Skaters must have played >= this fraction of full-season games (0 = off)

# =============================================================================
# STAT WEIGHTING (must sum to 1.0)
# =============================================================================
RECENT_FORM_WEIGHT = 0.55   # 55% recent (last X games)
FULL_SEASON_WEIGHT = 0.30   # 30% current full season
LAST_YEAR_WEIGHT = 0.15     # 15% last year's stats
                            # Total = 1.0 (55% + 30% + 15%)

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

# =============================================================================
# VISUALIZATION SETTINGS
# =============================================================================
ENABLE_VISUALIZATIONS = True            # Master switch for chart generation
VIZ_OUTPUT_DIR = "data/visualizations"  # Directory for saved charts
VIZ_FORMAT = "png"                      # Output format: "png" or "pdf"
VIZ_DPI = 300                           # Resolution (300 = print quality)

# Chart dimensions (width, height in inches)
TODAY_GAMES_FIGURE_SIZE = (16, 10)      # Game cards grid
PLAYOFF_BAR_FIGURE_SIZE = (14, 12)      # Playoff probability bars
CUP_BAR_FIGURE_SIZE = (12, 8)           # Cup probability bars
HEATMAP_FIGURE_SIZE = (14, 16)          # Probability heatmap

# Color schemes (hex colors)
EAST_PRIMARY = "#1f77b4"                # Blue for Eastern Conference
WEST_PRIMARY = "#d62728"                # Red for Western Conference

# Chart-specific settings
TODAY_GAMES_GRID_COLS = 2               # Columns for game cards (2 or 3)
CUP_CHART_TOP_N = 20                    # Number of teams in Cup chart
HEATMAP_COLORMAP = "Blues"              # Matplotlib colormap name

print(f"Config loaded -> Season {CURRENT_SEASON_FULL} | Today: {TODAY_PRETTY}")
