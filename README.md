# NHL Monte Carlo Simulation Model

A sophisticated NHL season prediction model that combines **expected goals (xG)** with **actual performance data** through a multi-layered weighting system. Uses Monte Carlo simulations with live player-level statistics to predict game outcomes, playoff probabilities, and Stanley Cup champions.

## 🎯 Key Features

- **Hybrid xG + Actual Goals**: Blends predictive power of expected goals (70%) with real-world performance (30%)
- **Position-Weighted Team Ratings**: Forwards, defensemen, and goalies weighted by their actual impact on offense/defense
- **Recent Form Emphasis**: 60% weight on last 10 games, 40% on full season
- **Live Player Data**: Downloads current 5v5 stats from Natural Stat Trick
- **Monte Carlo Simulation**: Runs thousands of season simulations for probabilistic predictions
- **Full Playoff Simulation**: Best-of-7 series through Stanley Cup Final
- **Game-to-Game Variance**: Realistic ±15% fluctuations for injuries, lineup changes, and form

---

## 🚀 Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run the model
python main.py
```

**Requirements:** Python 3.7+, pandas, numpy, beautifulsoup4, requests, tqdm

### What It Does

1. Scrapes current season schedule from Hockey-Reference
2. Downloads live player stats from Natural Stat Trick (5v5 rate stats)
3. Calculates position-weighted team offensive/defensive ratings
4. Displays today's game predictions (win %, expected goals)
5. Runs full-season Monte Carlo simulations
6. Outputs playoff odds, President's Trophy odds, and Stanley Cup probabilities

---

## 📊 The Weighting System

This model uses a **three-layer weighting system** to balance prediction accuracy with real-world results:

### Layer 1: Temporal Weighting (Recent Form)
```
Final Stat = (Last 10 Games × 60%) + (Full Season × 40%)
```
- **Why?** Captures current team form, injuries, and momentum
- **Configurable:** `RECENT_FORM_WEIGHT` in config.py (line 51)

### Layer 2: xG vs Actual Goals Blending
```
Weighted xGF/60 = (xGF/60 × 70%) + (GF/60 × 30%)
Weighted xGA/60 = (xGA/60 × 70%) + (GA/60 × 30%)
Goalie Weighted xGA/60 = (xG Against/60 × 70%) + (GAA × 30%)
```
- **Why?** xG is predictive, actual goals reward performance (finishing skill, hot goaltending)
- **Configurable:** `XG_WEIGHT` (70%) and `ACTUAL_GOALS_WEIGHT` (30%) in config.py (lines 57-58)

### Layer 3: Position Weights
```
Team Offense = (Forwards × 85%) + (Defensemen × 15%)
Team Defense = (Forwards × 20%) + (Defensemen × 30%) + (Goalies × 50%)
```
- **Why?** Different positions contribute differently to offense/defense
- **Configurable:** `FORWARD_OFFENSE_WEIGHT`, etc. in config.py (lines 35-39)

**All weights sum to 100%** to maintain proper scaling.

---

## 🔬 How It Works: Complete Pipeline

### Stage 1: Data Collection

**Files:** `nhl_schedule.py`, `nhl_rosters.py`

1. **Schedule Scraping** (Hockey-Reference)
   - Downloads full season schedule
   - Tracks completed games and scores
   - Saves to `data/schedule/schedule_YYYY_YYYY.csv`

2. **Player Stats Download** (Natural Stat Trick)
   - Full season 5v5 rate stats (xGF/60, GF/60, xGA/60, GA/60)
   - Last 10 games 5v5 rate stats (for recent form)
   - Goalie-specific stats (xG Against/60, GAA)
   - **Temporal weighting applied:** 60% recent + 40% full season
   - Saves to SQLite: `data/db/nhl_YYYY_YYYY_players.db`

**Key Functions:**
- `scrape_schedule()` - Downloads schedule, handles team name mappings
- `download_nst_data()` - Pulls player stats with recent form weighting
- `merge_and_weight_stats()` - Blends full season + last 10 games

---

### Stage 2: Team Strength Calculation

**File:** `team_strength.py`

**Function:** `get_team_strength(team, db_path)` → Returns `(offensive_rating, defensive_rating)`

**Process:**

#### Step A: Position-Specific TOI-Weighted Averages
```sql
-- Example for forwards offense (actual SQL query in team_strength.py:37-75)
Forward_xGF = SUM(xGF/60 × TOI) / SUM(TOI)  -- where Position IN ('C','L','R')
Forward_GF = SUM(GF/60 × TOI) / SUM(TOI)
```
Calculated separately for:
- Forwards: xGF/60, GF/60, xGA/60, GA/60
- Defensemen: xGF/60, GF/60, xGA/60, GA/60
- Goalies: xG Against/60, GAA

#### Step B: Blend xG + Actual for Each Position
```python
forward_off = (forward_xgf × 0.70) + (forward_gf × 0.30)
defense_off = (defense_xgf × 0.70) + (defense_gf × 0.30)
forward_def = (forward_xga × 0.70) + (forward_ga × 0.30)
defense_def = (defense_xga × 0.70) + (defense_ga × 0.30)
goalie_def = (goalie_xga × 0.70) + (goalie_gaa × 0.30)
```

#### Step C: Apply Position Weights
```python
Team_Offense = (forward_off × 0.85) + (defense_off × 0.15)
Team_Defense = (forward_def × 0.20) + (defense_def × 0.30) + (goalie_def × 0.50)
```

**Example Output:**
- Minnesota Wild: 2.45 xGF/60 (offense), 2.56 xGA/60 (defense)
- Colorado Avalanche: 3.15 xGF/60 (offense), 2.32 xGA/60 (defense)

**Sanity Checks:**
- Values clamped to [1.8, 4.8] to prevent unrealistic ratings
- Falls back to 2.80/2.80 if no data available

---

### Stage 3: Game Simulation

**File:** `game_simulation.py`

**Function:** `simulate_game(home, away, db_path)` → Returns `(winner, home_pts, away_pts, home_goals, away_goals, regulation_win)`

**Process:**

#### Step 1: Get Team Ratings
```python
home_off, home_def = get_team_strength(home, db_path)
away_off, away_def = get_team_strength(away, db_path)
```

#### Step 2: Apply Game-to-Game Variance
```python
# ±15% random variance for injuries, lineup changes, hot/cold streaks
home_off *= random_uniform(0.85, 1.15)
home_def *= random_uniform(0.85, 1.15)
away_off *= random_uniform(0.85, 1.15)
away_def *= random_uniform(0.85, 1.15)
```

#### Step 3: Calculate Expected Goals
```python
home_xg = home_off × 1.10 × (away_def / 2.95)  # 1.10 = home ice advantage
away_xg = away_off × (home_def / 2.95)         # 2.95 = league average
```

**Formula Breakdown:**
- **Team Offense:** How many goals this team generates per 60 minutes
- **Home Ice Advantage:** 10% boost for home team
- **League Average Baseline:** 2.95 xG/60 (normalizes across league)
- **Opponent Defense:** How many goals opponent allows per 60 minutes

#### Step 4: Poisson Distribution
```python
home_goals = np.random.poisson(home_xg)
away_goals = np.random.poisson(away_xg)
```
**Why Poisson?** Goal-scoring events are discrete and independent, following Poisson distribution in hockey.

#### Step 5: Determine Winner
- **Regulation Win:** Winner gets 2 pts, loser gets 0 pts
- **Overtime/Shootout:** Coin flip with 55% home advantage, winner gets 2 pts, loser gets 1 pt

---

### Stage 4: Season Simulation

**Files:** `season_simulation.py`, `playoff_simulation.py`

#### Full Season Monte Carlo
1. Load current standings from completed games
2. For each simulation (default: 1,000):
   - Simulate all remaining games using `simulate_game()`
   - Calculate final standings with tiebreakers (points → ROW → OTW → GF-GA → GF)
   - Determine playoff teams (top 3 per division + 2 wildcards per conference)
   - Track President's Trophy winner (most points)

#### Playoff Simulation
3. Seed playoff teams by standings
4. Simulate first round (best-of-7 series)
5. Simulate second round
6. Simulate conference finals
7. Simulate Stanley Cup Final
8. Track advancement for each team

#### Results Aggregation
9. Calculate probabilities:
   - Playoff % = (simulations made playoffs / total simulations)
   - President's Trophy % = (simulations won most points / total)
   - Stanley Cup % = (simulations won Cup / total)

---

## 📈 Configuration Options

All parameters are configurable in **`config.py`**:

### Weighting Parameters
| Parameter | Default | Description | Line |
|-----------|---------|-------------|------|
| `RECENT_FORM_WEIGHT` | 0.60 | Weight for last 10 games (vs full season) | 51 |
| `XG_WEIGHT` | 0.70 | Weight for expected goals (vs actual) | 58 |
| `ACTUAL_GOALS_WEIGHT` | 0.30 | Weight for actual goals (vs expected) | 57 |
| `FORWARD_OFFENSE_WEIGHT` | 0.85 | Forward contribution to team offense | 35 |
| `DEFENSE_OFFENSE_WEIGHT` | 0.15 | Defense contribution to team offense | 36 |
| `FORWARD_DEFENSE_WEIGHT` | 0.20 | Forward contribution to team defense | 37 |
| `DEFENSE_DEFENSE_WEIGHT` | 0.30 | Defense contribution to team defense | 38 |
| `GOALIE_DEFENSE_WEIGHT` | 0.50 | Goalie contribution to team defense | 39 |

### Simulation Settings
| Parameter | Default | Description | Line |
|-----------|---------|-------------|------|
| `N_SIMS_FULL` | 1 | Number of full-season simulations | 27 |
| `N_SIMS_TODAY` | 1 | Simulations per today's game | 28 |
| `TEAM_STRENGTH_VARIANCE` | 0.15 | Game-to-game variance (±15%) | 32 |
| `HOME_ICE_ADVANTAGE` | 1.10 | Home team xG multiplier | 29 |
| `LEAGUE_AVG_XG_PER_60` | 2.95 | League baseline xG/60 | 30 |
| `OT_HOME_WIN_PROB` | 0.55 | Home team OT/SO win probability | 31 |

### Data Filters
| Parameter | Default | Description | Line |
|-----------|---------|-------------|------|
| `MIN_TOI_MINUTES` | 20 | Minimum TOI to include player | 44 |
| `FALLBACK_OFFENSIVE_RATING` | 2.80 | Default if no data | 45 |
| `FALLBACK_DEFENSIVE_RATING` | 2.80 | Default if no data | 46 |

### Display Settings
| Parameter | Default | Description | Line |
|-----------|---------|-------------|------|
| `SHOW_TODAYS_GAMES` | True | Display today's predictions | 57 |
| `SHOW_ROSTER_DUMP` | True | Print full roster stats | 58 |
| `SHOW_PROGRESS_EVERY` | 2000 | Progress bar frequency | 59 |

---

## 📊 Understanding the Output

### Team Strength Display
```
Minnesota Wild
TEAM STRENGTH (Position-Weighted):
  Offensive Rating: 2.45 xGF/60
  Defensive Rating: 2.56 xGA/60

FORWARDS (sorted by offensive contribution)
 Player              Position  TOI   xGF/60  GF/60  xGA/60  GA/60  Weighted xGF/60  Weighted xGA/60  Off_Contrib  Def_Contrib
 Matt Boldy          L         379   3.21    3.01   2.79    1.42   3.15             2.38             0.03         0.0
 Kirill Kaprizov     L         442   2.61    2.99   2.75    2.04   2.72             2.54             0.01         0.0
```

**Column Explanations:**
- **xGF/60**: Expected goals for per 60 minutes (quality of scoring chances created)
- **GF/60**: Actual goals for per 60 minutes (actual scoring rate)
- **xGA/60**: Expected goals against per 60 minutes (quality of chances allowed)
- **GA/60**: Actual goals against per 60 minutes (actual goals allowed rate)
- **Weighted xGF/60**: Blended offense (70% xGF + 30% GF) — **used in team rating**
- **Weighted xGA/60**: Blended defense (70% xGA + 30% GA) — **used in team rating**
- **Off_Contrib**: Player's offensive contribution to team (above/below position average × TOI% × position weight)
- **Def_Contrib**: Player's defensive contribution to team (above/below team average × TOI% × position weight)

**Interpreting Contributions:**
- **+0.03**: This player adds ~0.03 xGF/60 to the team's offensive rating
- **-0.01**: This player subtracts ~0.01 xGA/60 from team's defensive rating
- **0.0**: Player is at position average (neither helps nor hurts)

### Goalie Display
```
GOALIES (sorted by defensive contribution)
 Player              Position  TOI   xG Against/60  GAA   Weighted xGA/60  Off_Contrib  Def_Contrib
 Jesper Wallstedt    G         494   2.60           1.34  2.22             0.0          0.01
```

**Column Explanations:**
- **xG Against/60**: Expected goals against (goalie-specific metric)
- **GAA**: Goals against average (actual performance)
- **Weighted xGA/60**: Blended (70% xGA + 30% GAA) — **used in team rating**
- **Def_Contrib**: Defensive contribution (positive = better than average goalie)

**Why Wallstedt has high contribution:**
- Weighted xGA/60 of 2.22 is well below team average (2.56)
- Strong actual performance (1.34 GAA) pulls weighted value down
- As goalie, contributes 50% of team defense → large impact

---

### Game Predictions
```
TODAY'S NHL GAMES
Minnesota Wild @ Colorado Avalanche
  Minnesota Wild:       45.2% to win  |  Avg Goals: 2.4
  Colorado Avalanche:   54.8% to win  |  Avg Goals: 2.9
  Favorite: AWAY  |  Expected Total: 5.3
```

**Interpretation:**
- **Win %**: Probability of winning based on 1,000+ simulations
- **Avg Goals**: Expected goals from Poisson distribution
- **Favorite**: Team with >62% win probability (else "TOSS-UP")
- **Expected Total**: Sum of both teams' average goals

---

### Season Simulation Results
```
NHL 2025-2026 FINAL RESULTS — 10,000 simulations
                    Team  Playoff %  Round 1 %  Round 2 %  Conf Finals %  Cup %  Pres Trophy %
      Colorado Avalanche       98.5       92.1       71.3           48.2   12.3           45.2
    Carolina Hurricanes        96.2       88.4       65.7           42.1    8.4           18.7
```

**Column Explanations:**
- **Playoff %**: Made playoffs (top 3 division + 2 wildcards)
- **Round 1 %**: Won first round
- **Round 2 %**: Won second round (Conference Semifinals)
- **Conf Finals %**: Won conference finals
- **Cup %**: Won Stanley Cup
- **Pres Trophy %**: Finished with most regular season points

---

## 🗂️ File Structure

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
    │   └── nhl_2025_2026_players.db      # SQLite player stats
    ├── schedule/
    │   └── schedule_2025_2026.csv         # Season schedule
    └── results/
        └── nhl_predictions_YYYYMMDD.csv   # Simulation results
```

---

## 🧮 Key Formulas Reference

### Team Offensive Rating
```python
# Step 1: Calculate position-weighted averages (TOI-weighted)
forward_xgf = SUM(forward_xGF/60 × TOI) / SUM(forward_TOI)
forward_gf = SUM(forward_GF/60 × TOI) / SUM(forward_TOI)
defense_xgf = SUM(defense_xGF/60 × TOI) / SUM(defense_TOI)
defense_gf = SUM(defense_GF/60 × TOI) / SUM(defense_TOI)

# Step 2: Blend xG + Actual for each position
forward_off = (forward_xgf × 0.70) + (forward_gf × 0.30)
defense_off = (defense_xgf × 0.70) + (defense_gf × 0.30)

# Step 3: Apply position weights
Team_Offense = (forward_off × 0.85) + (defense_off × 0.15)
```

### Team Defensive Rating
```python
# Step 1: Calculate position-weighted averages (TOI-weighted)
forward_xga = SUM(forward_xGA/60 × TOI) / SUM(forward_TOI)
forward_ga = SUM(forward_GA/60 × TOI) / SUM(forward_TOI)
defense_xga = SUM(defense_xGA/60 × TOI) / SUM(defense_TOI)
defense_ga = SUM(defense_GA/60 × TOI) / SUM(defense_TOI)
goalie_xga = SUM(goalie_xG_Against/60 × TOI) / SUM(goalie_TOI)
goalie_gaa = SUM(goalie_GAA × TOI) / SUM(goalie_TOI)

# Step 2: Blend xG + Actual for each position
forward_def = (forward_xga × 0.70) + (forward_ga × 0.30)
defense_def = (defense_xga × 0.70) + (defense_ga × 0.30)
goalie_def = (goalie_xga × 0.70) + (goalie_gaa × 0.30)

# Step 3: Apply position weights
Team_Defense = (forward_def × 0.20) + (defense_def × 0.30) + (goalie_def × 0.50)
```

### Game Expected Goals
```python
# Get team ratings (already weighted/blended)
home_off, home_def = get_team_strength(home)
away_off, away_def = get_team_strength(away)

# Apply variance (±15%)
home_off *= uniform(0.85, 1.15)
home_def *= uniform(0.85, 1.15)
away_off *= uniform(0.85, 1.15)
away_def *= uniform(0.85, 1.15)

# Calculate expected goals
home_xg = home_off × 1.10 × (away_def / 2.95)
away_xg = away_off × (home_def / 2.95)

# Simulate with Poisson
home_goals ~ Poisson(home_xg)
away_goals ~ Poisson(away_xg)
```

---

## 🤔 Why This Approach?

### Why Blend xG + Actual Goals?

**Problem:** Pure xG models can undervalue teams with:
- Elite finishing talent (high shooting percentage)
- Hot goaltending (save percentage above expected)
- Clutch performance (scoring in close games)

**Solution:** Blend 70% xG + 30% actual goals
- **70% xG**: Maintains predictive stability (xG regresses to mean better than actual goals)
- **30% Actual**: Rewards current performance (finishing skill, goaltending streaks)

**Example - Minnesota Wild:**
- Pure xG model: 2.62 off / 2.83 def (looks average)
- Blended model: 2.45 off / 2.56 def (credits strong goaltending in actual GAA)
- Reality: 8-0-2 in last 10 games with strong finishing + goaltending

### Why Position Weighting?

**Not all positions contribute equally:**
- **Offense**: Forwards generate 85% of goals (they play in offensive zone, shoot more)
- **Defense**: Goalies prevent 50% of goals (last line of defense, face all shots)

**Empirical basis:** Position weights roughly match NHL goal contribution patterns.

### Why Recent Form Weighting?

**Hockey teams change rapidly:**
- Injuries/returns
- Trade deadline acquisitions
- Hot/cold streaks
- Lineup adjustments

**60% recent + 40% full season** balances:
- **Recent form**: Captures current state
- **Full season**: Provides statistical stability (avoids small sample noise)

### Why Monte Carlo Simulation?

**Hockey is high-variance:**
- Low-scoring sport (2-3 goals/game)
- One hot goalie can swing a series
- Overtime/shootout adds randomness

**Monte Carlo benefits:**
- Captures full probability distribution (not just point estimates)
- Naturally handles uncertainty
- Produces interpretable probabilities

---

## ⚙️ Customization Examples

### Make Model More Reactive to Recent Performance
```python
# config.py
RECENT_FORM_WEIGHT = 0.80  # 80% recent, 20% full season
ACTUAL_GOALS_WEIGHT = 0.40  # 40% actual, 60% xG
```
**Effect:** Model reacts faster to hot/cold streaks, but more volatile.

### Make Model More Predictive/Stable
```python
# config.py
RECENT_FORM_WEIGHT = 0.40  # 40% recent, 60% full season
XG_WEIGHT = 0.85  # 85% xG, 15% actual
```
**Effect:** Model focuses on long-term talent, ignores short-term noise.

### Increase Goalie Importance
```python
# config.py
GOALIE_DEFENSE_WEIGHT = 0.60  # 60% (up from 50%)
DEFENSE_DEFENSE_WEIGHT = 0.25  # 25% (down from 30%)
FORWARD_DEFENSE_WEIGHT = 0.15  # 15% (down from 20%)
```
**Effect:** Goaltending matters more (must sum to 100%).

### Run Quick Test
```python
# config.py
N_SIMS_FULL = 100  # 100 simulations (fast, less accurate)
SHOW_ROSTER_DUMP = False  # Skip roster display
```
**Effect:** Completes in ~30 seconds instead of 5+ minutes.

---

## 🐛 Troubleshooting

### Schedule Scraping Fails
**Error:** `"Schedule table not found"`

**Causes:**
- Hockey-Reference changed HTML structure
- Network connectivity issues
- Season hasn't started yet

**Solutions:**
1. Check Hockey-Reference manually: `https://www.hockey-reference.com/leagues/NHL_2026_games.html`
2. Update table search in `nhl_schedule.py` if structure changed
3. Use cached schedule from previous run (`data/schedule/`)

### Player Stats Download Fails
**Error:** `"NST download failed completely → using league averages"`

**Causes:**
- Natural Stat Trick website down
- Changed URL structure
- Network issues

**Solutions:**
1. Check NST manually: `https://www.naturalstattrick.com/playerteams.php`
2. Model will fall back to 2.80/2.80 ratings (league average)
3. Wait and retry later (NST updates may be in progress)

### Team Ratings All Show 1.80/1.80
**Cause:** Database query failing (position-weighted calculation issue)

**Solutions:**
1. Check if `data/db/nhl_YYYY_YYYY_players.db` exists and has data
2. Verify `MIN_TOI_MINUTES` isn't set too high (no players qualify)
3. Check for SQL errors in console output

### Very Slow Performance
**Symptoms:** 10,000 simulations taking >30 minutes

**Solutions:**
1. Reduce `N_SIMS_FULL` to 1,000 (still statistically valid)
2. Set `SHOW_ROSTER_DUMP = False` to skip player display
3. Consider PyPy instead of CPython (2-3x speedup)
4. Disable progress bars: `SHOW_PROGRESS_EVERY = 0`

---

## 🚧 Known Limitations

1. **5v5 Only**: Special teams (PP/PK) not included
   - *Rationale:* 5v5 is ~85% of game time and most predictive

2. **No Individual Matchups**: Doesn't model line matching
   - *Rationale:* Variance parameter (±15%) captures some of this

3. **Small Sample Bias**: Early season has limited data
   - *Mitigation:* Recent form weighting helps, but <20 games is noisy

4. **Injury Tracking**: No explicit injury adjustments
   - *Mitigation:* Recent form (60%) naturally excludes injured players
   - *Limitation:* Doesn't project returns/absences

5. **Goalie Variance**: Goalies can be streaky (hot/cold)
   - *Mitigation:* 30% actual goals weight captures current form
   - *Limitation:* Can't predict regression to mean

---

## 🔮 Future Enhancements

**Potential improvements:**
- [ ] Special teams modeling (PP/PK efficiency)
- [ ] Goalie-specific variance/streakiness modeling
- [ ] Trade deadline roster change tracking
- [ ] Historical validation (backtest on past seasons)
- [ ] Team-specific home ice advantages (travel distance, altitude)
- [ ] Line-matching simulation (top lines vs bottom pairs)
- [ ] Web interface for interactive predictions
- [ ] API for live game probability updates
- [ ] Bayesian updating during games (in-game win probability)

---

## 📚 References & Data Sources

- **Schedule Data:** [Hockey-Reference.com](https://www.hockey-reference.com/)
- **Player Stats:** [Natural Stat Trick](https://www.naturalstattrick.com/)
- **Methodology:** Based on hockey analytics research (xG models, Monte Carlo simulation)
- **Inspiration:** Nate Silver's FiveThirtyEight NHL models, Evolving-Hockey's RAPM models

---

## 📄 License

This project is for **educational and research purposes**.

Not affiliated with the NHL or any official league entity. All data is publicly available from Hockey-Reference and Natural Stat Trick.

---

## 🙏 Acknowledgments

Special thanks to:
- **Natural Stat Trick** for providing free, comprehensive hockey analytics data
- **Hockey-Reference** for maintaining historical NHL data
- The **hockey analytics community** for pioneering xG models and advanced metrics
- **Evolving-Hockey, MoneyPuck, and Dom Luszczyszyn** for methodology inspiration

---

**Questions? Issues?** Open an issue on GitHub or consult the inline code documentation.

**Want to contribute?** Pull requests welcome for bug fixes, performance improvements, or new features!
