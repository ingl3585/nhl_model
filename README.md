# NHL Monte Carlo Simulation Model

A sophisticated NHL season prediction model that combines **expected goals (xG)** with **actual performance data** through a multi-layered weighting system. Uses Monte Carlo simulations with live player-level statistics to predict game outcomes, playoff probabilities, and Stanley Cup champions.

## Key Features

- **Three-Way Temporal Weighting**: 55% last 10 games, 30% full season, 15% prior season
- **xG + Actual Goals Blend**: 70% expected goals, 30% actual goals per player
- **Position-Weighted Team Ratings**: Forwards, defensemen, and goalies weighted by positional impact
- **Home/Away Split Stats**: Separate offensive/defensive ratings for home and away contexts
- **Smart Daily Caching**: Skips re-downloading player data if the database is already current
- **Live Player Data**: Downloads current 5v5 stats from Natural Stat Trick
- **Monte Carlo Simulation**: Runs full-season simulations for probabilistic predictions
- **Full Playoff Simulation**: Best-of-7 series through Stanley Cup Final
- **Visualization Output**: Charts for game predictions, playoff odds, and probability heatmaps

---

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run the model
python main.py
```

**Requirements:** Python 3.8+, see `requirements.txt`

### What It Does

1. Scrapes current season schedule from Hockey-Reference
2. Downloads live player stats from Natural Stat Trick (5v5 rate stats) — skipped if already downloaded today
3. Calculates position-weighted team offensive/defensive ratings
4. Displays today's game predictions (win %, expected goals)
5. Runs full-season Monte Carlo simulations
6. Outputs playoff odds, President's Trophy odds, Stanley Cup probabilities, and visualization charts

---

## The Weighting System

This model uses a **three-layer weighting system** to balance prediction accuracy with real-world results:

### Layer 1: Temporal Weighting (Recent Form)
```
Final Stat = (Last 10 Games × 55%) + (Full Season × 30%) + (Prior Season × 15%)
```
- **Why?** Captures current team form while maintaining statistical stability via full-season and prior-year context
- **Configurable:** `RECENT_FORM_WEIGHT`, `FULL_SEASON_WEIGHT`, `LAST_YEAR_WEIGHT` in `config.py`

### Layer 2: xG vs Actual Goals Blending
```
Weighted xGF/60 = (xGF/60 × 70%) + (GF/60 × 30%)
Weighted xGA/60 = (xGA/60 × 70%) + (GA/60 × 30%)
Goalie Weighted xGA/60 = (xG Against/60 × 70%) + (GAA × 30%)
```
- **Why?** xG is predictive; actual goals reward finishing skill and goaltending performance
- **Configurable:** `XG_WEIGHT` and `ACTUAL_GOALS_WEIGHT` in `config.py`

### Layer 3: Position Weights
```
Team Offense = (Forwards × 85%) + (Defensemen × 15%)
Team Defense = (Forwards × 20%) + (Defensemen × 30%) + (Goalies × 50%)
```
- **Why?** Positions contribute differently to offense and defense
- **Configurable:** `FORWARD_OFFENSE_WEIGHT`, etc. in `config.py`

**All weights sum to 100%** to maintain proper scaling.

---

## How It Works: Complete Pipeline

### Stage 1: Data Collection

**Files:** `nhl_schedule.py`, `nhl_rosters.py`

1. **Schedule Scraping** (Hockey-Reference)
   - Downloads full season schedule
   - Tracks completed games and scores
   - Saves to `data/schedule/schedule_YYYY_YYYY.csv`

2. **Player Stats Download** (Natural Stat Trick)
   - Full season 5v5 rate stats (xGF/60, GF/60, xGA/60, GA/60) — separate home and away
   - Last 10 games 5v5 rate stats (for recent form) — home and away
   - Prior season stats for additional context
   - Goalie-specific stats (xG Against/60, GAA)
   - Active roster filter: only players who appeared in their team's last game
   - **Smart caching:** skips download entirely if the database was already updated today
   - Saves to SQLite: `data/db/nhl_YYYY_YYYY_players.db`

**Key Functions:**
- `scrape_schedule()` — Downloads schedule, handles team name mappings
- `download_nst_data()` — Pulls player stats with temporal weighting and daily cache check
- `merge_and_weight_stats()` — Blends recent, full-season, and prior-year data

---

### Stage 2: Team Strength Calculation

**File:** `team_strength.py`

**Function:** `get_team_strength(team, db_path)` → Returns `(offensive_rating, defensive_rating)`

**Process:**

#### Step A: Position-Specific TOI-Weighted Averages
```sql
Forward_xGF = SUM(xGF/60 × TOI) / SUM(TOI)  -- Position IN ('C','L','R')
Forward_GF  = SUM(GF/60  × TOI) / SUM(TOI)
```
Calculated separately for forwards, defensemen, and goalies.

#### Step B: Blend xG + Actual for Each Position
```python
forward_off = (forward_xgf × 0.70) + (forward_gf × 0.30)
defense_off = (defense_xgf × 0.70) + (defense_gf × 0.30)
forward_def = (forward_xga × 0.70) + (forward_ga × 0.30)
defense_def = (defense_xga × 0.70) + (defense_ga × 0.30)
goalie_def  = (goalie_xga × 0.70) + (goalie_gaa × 0.30)
```

#### Step C: Apply Position Weights
```python
Team_Offense = (forward_off × 0.85) + (defense_off × 0.15)
Team_Defense = (forward_def × 0.20) + (defense_def × 0.30) + (goalie_def × 0.50)
```

**Sanity Checks:**
- Values clamped to [1.8, 4.8] to prevent unrealistic ratings
- Falls back to 2.80/2.80 if no data available

---

### Stage 3: Game Simulation

**File:** `game_simulation.py`

**Function:** `simulate_game(home, away, db_path)` → Returns `(winner, home_pts, away_pts, home_goals, away_goals, regulation_win)`

**Process:**

#### Step 1: Get Team Ratings
Home/away advantage is built directly into the player stats — NST data is split by location, so home offensive ratings and away defensive ratings already reflect real performance splits.

#### Step 2: Apply Game-to-Game Variance
```python
# ±15% random variance for injuries, lineup changes, hot/cold streaks
home_off *= random_uniform(0.85, 1.15)
away_off *= random_uniform(0.85, 1.15)
```

#### Step 3: Calculate Expected Goals
```python
home_xg = home_off × (away_def / LEAGUE_AVG_XG_PER_60)  # 3.10 league avg
away_xg = away_off × (home_def / LEAGUE_AVG_XG_PER_60)
```

#### Step 4: Poisson Distribution
```python
home_goals = np.random.poisson(home_xg)
away_goals = np.random.poisson(away_xg)
```
**Why Poisson?** Goal-scoring events are discrete and independent, following Poisson distribution in hockey.

#### Step 5: Determine Winner
- **Regulation Win:** Winner gets 2 pts, loser gets 0 pts
- **Overtime/Shootout:** 55% home advantage, winner gets 2 pts, loser gets 1 pt

---

### Stage 4: Season Simulation

**Files:** `season_simulation.py`, `playoff_simulation.py`

#### Full Season Monte Carlo
1. Load current standings from completed games
2. For each simulation:
   - Simulate all remaining games using `simulate_game()`
   - Calculate final standings with tiebreakers (points → ROW → OTW → GF-GA → GF)
   - Determine playoff teams (top 3 per division + 2 wildcards per conference)
   - Track President's Trophy winner (most points)

#### Playoff Simulation
3. Seed playoff teams by standings
4. Simulate first round through Stanley Cup Final (best-of-7 series each)
5. Track advancement for each team across all simulations

#### Results Aggregation
6. Calculate probabilities:
   - Playoff % = simulations made playoffs / total simulations
   - President's Trophy % = simulations won most points / total
   - Stanley Cup % = simulations won Cup / total

---

## Configuration Options

All parameters are configurable in **`config.py`**:

### Weighting Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `RECENT_FORM_WEIGHT` | 0.55 | Weight for last 10 games |
| `FULL_SEASON_WEIGHT` | 0.30 | Weight for current full season |
| `LAST_YEAR_WEIGHT` | 0.15 | Weight for prior season stats |
| `XG_WEIGHT` | 0.70 | Weight for expected goals (vs actual) |
| `ACTUAL_GOALS_WEIGHT` | 0.30 | Weight for actual goals (vs expected) |
| `FORWARD_OFFENSE_WEIGHT` | 0.85 | Forward contribution to team offense |
| `DEFENSE_OFFENSE_WEIGHT` | 0.15 | Defense contribution to team offense |
| `FORWARD_DEFENSE_WEIGHT` | 0.20 | Forward contribution to team defense |
| `DEFENSE_DEFENSE_WEIGHT` | 0.30 | Defense contribution to team defense |
| `GOALIE_DEFENSE_WEIGHT` | 0.50 | Goalie contribution to team defense |

### Simulation Settings
| Parameter | Default | Description |
|-----------|---------|-------------|
| `N_SIMS_FULL` | 105 | Number of full-season simulations |
| `N_SIMS_TODAY` | 10294 | Simulations per today's game prediction |
| `TEAM_STRENGTH_VARIANCE` | 0.15 | Game-to-game variance (±15%) |
| `LEAGUE_AVG_XG_PER_60` | 3.10 | League baseline xG/60 |
| `OT_HOME_WIN_PROB` | 0.55 | Home team OT/SO win probability |

### Data Filters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `MIN_TOI_MINUTES` | 20 | Minimum TOI to include a player |
| `FALLBACK_OFFENSIVE_RATING` | 2.80 | Default rating if no data |
| `FALLBACK_DEFENSIVE_RATING` | 2.80 | Default rating if no data |

### Display Settings
| Parameter | Default | Description |
|-----------|---------|-------------|
| `SHOW_TODAYS_GAMES` | True | Display today's predictions |
| `SHOW_ROSTER_DUMP` | False | Print full roster stats |
| `ENABLE_VISUALIZATIONS` | True | Generate chart output |

---

## Understanding the Output

### Game Predictions
```
TODAY'S NHL GAMES
Minnesota Wild @ Colorado Avalanche
  Minnesota Wild:       45.2% to win  |  Avg Goals: 2.4
  Colorado Avalanche:   54.8% to win  |  Avg Goals: 2.9
  Favorite: AWAY  |  Expected Total: 5.3
```

- **Win %**: Probability of winning based on simulations
- **Avg Goals**: Expected goals from Poisson distribution
- **Favorite**: Team with >62% win probability (else "TOSS-UP")
- **Expected Total**: Sum of both teams' average goals

### Season Simulation Results
```
NHL 2025-2026 FINAL RESULTS — 105 simulations
                    Team  Playoff %  Round 2 %  Conf Finals %  Finals %  Cup %  Pres Trophy %
      Colorado Avalanche      100.0      59.0%          30.5%     20.0%   8.6%          73.3%
    Carolina Hurricanes        100.0      56.2%          41.9%     25.7%  16.2%          11.4%
```

- **Playoff %**: Made playoffs (top 3 per division + 2 wildcards)
- **Round 2 %**: Won first round
- **Conf Finals %**: Won conference semifinals
- **Finals %**: Won conference finals
- **Cup %**: Won Stanley Cup
- **Pres Trophy %**: Finished with most regular season points

---

## File Structure

```
nhl_model/
├── main.py                    # Entry point, orchestrates full pipeline
├── config.py                  # All configuration parameters
│
├── nhl_schedule.py            # Schedule scraping from Hockey-Reference
├── nhl_rosters.py             # Player stat download from Natural Stat Trick
├── team_strength.py           # Team rating calculations (core logic)
├── game_simulation.py         # Single game Poisson simulation
├── season_simulation.py       # Full season Monte Carlo + standings
├── playoff_simulation.py      # Playoff bracket + best-of-7 series
│
└── data/
    ├── db/
    │   └── nhl_2025_2026_players.db          # SQLite player stats
    ├── schedule/
    │   └── schedule_2025_2026.csv             # Season schedule
    ├── results/
    │   └── nhl_predictions_YYYYMMDD.csv       # Simulation results
    └── visualizations/
        ├── todays_games_YYYYMMDD.png          # Game prediction cards
        ├── playoff_probabilities_YYYYMMDD.png # Playoff probability bars
        ├── cup_probabilities_YYYYMMDD.png     # Cup probability bars
        └── probability_heatmap_YYYYMMDD.png   # Full probability heatmap
```

---

## Troubleshooting

### Schedule Scraping Fails
**Error:** `"Schedule table not found"`

**Causes:** Hockey-Reference changed HTML structure, or network issue.

**Solutions:**
1. Check the schedule page on Hockey-Reference manually
2. Update table search in `nhl_schedule.py` if the structure changed
3. Use a cached schedule from a previous run (`data/schedule/`)

### Player Stats Download Fails
**Error:** `"NST download failed completely → using league averages"`

**Causes:** Natural Stat Trick is down or URL structure changed.

**Solutions:**
1. Check NST manually at naturalstattrick.com
2. The model will fall back to 2.80/2.80 league-average ratings
3. Wait and retry — NST may be updating its data

### Team Ratings All Show 1.80
**Cause:** Database query failing or no players qualify the TOI filter.

**Solutions:**
1. Confirm `data/db/nhl_YYYY_YYYY_players.db` exists and has rows
2. Lower `MIN_TOI_MINUTES` in `config.py` if it's set too high
3. Check for SQL errors in console output

### Slow Performance
**Solutions:**
1. Lower `N_SIMS_FULL` (105 is fast; 1,000+ is more accurate but slower)
2. Set `SHOW_ROSTER_DUMP = False`
3. Set `ENABLE_VISUALIZATIONS = False` to skip chart generation

---

## Known Limitations

1. **5v5 Only**: Special teams (PP/PK) not modeled — 5v5 is ~75% of game time and the most stable predictor
2. **No Individual Matchups**: Doesn't model line-matching; `TEAM_STRENGTH_VARIANCE` (±15%) captures some of this
3. **Small Sample Bias**: Early-season predictions are noisy with <20 games of data; prior-season weighting (15%) helps
4. **Injury Tracking**: No explicit injury adjustments — recent form weighting (55% L10) naturally downweights injured players' contributions but doesn't project returns

---

## Future Enhancements

- [ ] Special teams modeling (PP/PK efficiency)
- [ ] Goalie-specific streakiness / hot-hand modeling
- [ ] Trade deadline roster change tracking
- [ ] Historical backtesting (validate against past seasons)
- [ ] Team-specific home ice factors (altitude, travel fatigue)
- [ ] Web interface for interactive predictions
- [ ] In-game win probability updates

---

## Data Sources

- **Schedule Data:** [Hockey-Reference.com](https://www.hockey-reference.com/)
- **Player Stats:** [Natural Stat Trick](https://www.naturalstattrick.com/)
- **Methodology:** xG-based Monte Carlo simulation, inspired by hockey analytics research

---

## License

This project is for **educational and research purposes**.

Not affiliated with the NHL or any official league entity. All data is publicly available from Hockey-Reference and Natural Stat Trick.
