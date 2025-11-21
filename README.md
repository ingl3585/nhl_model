# NHL Monte Carlo Simulation Model

A sophisticated NHL season prediction model that uses Monte Carlo simulations with live player-level expected goals (xGF/xGA) data to predict playoff probabilities, President's Trophy winners, and Stanley Cup champions.

## Features

- **Live Player Data**: Downloads current season 5v5 stats from Natural Stat Trick
- **Team Strength Ratings**: Calculates team offensive and defensive ratings from player xGF/xGA data
- **Monte Carlo Simulation**: Runs thousands of season simulations for statistical predictions
- **Today's Game Predictions**: Provides win probabilities and expected totals for today's games
- **Realistic Variance**: Simulates injuries, lineup changes, and team form with game-to-game variance
- **Full Playoff Brackets**: Simulates conference playoffs and Stanley Cup Finals

## Installation

### Requirements
- Python 3.7+
- pip

### Setup

1. Clone or download this repository

2. Install dependencies:
```bash
pip install -r requirements.txt
```

Required packages:
- pandas
- numpy
- beautifulsoup4
- selenium

## Usage

### Run the Model

```bash
python main.py
```

This will:
1. Scrape the current season schedule from Hockey-Reference
2. Download live player statistics from Natural Stat Trick
3. Display today's game predictions (if enabled)
4. Run full season Monte Carlo simulations
5. Output results to CSV

### Sample Output

```
NHL MONTE CARLO PRO — 2025-2026 SEASON
Live 5v5 xGF/xGA model | 1000 simulations

TODAY'S NHL GAMES — November 21, 2025
Chicago Blackhawks — 2.46 GF — 38.5% to win
Buffalo Sabres — 2.92 GF — 61.5% to win
   → Favorite: TOSS-UP | Expected Total: ~5.38

NHL 2025-2026 FINAL RESULTS — 1000 sims in 480s
                Team Playoff % President's Trophy % Stanley Cup %
 Colorado Avalanche     98.5%               45.2%           12.3%
   Carolina Hurricanes  96.2%               18.7%            8.4%
      ...
```

## Configuration

All settings can be adjusted in `config.py`:

### Simulation Settings
```python
N_SIMS_FULL = 1000              # Full season simulations
N_SIMS_TODAY = 500              # Simulations per today's game
TEAM_STRENGTH_VARIANCE = 0.08   # ±8% game-to-game variance
```

### Model Parameters
```python
HOME_ICE_ADVANTAGE = 1.10       # Home team xG multiplier
LEAGUE_AVG_XG_PER_60 = 2.95    # League average expected goals per 60 min
OT_HOME_WIN_PROB = 0.55        # Home team OT/SO win probability
```

### Data Filters
```python
MIN_TOI_MINUTES = 60            # Minimum TOI to include player
FALLBACK_OFFENSIVE_RATING = 2.80  # Used when no data available
FALLBACK_DEFENSIVE_RATING = 2.80
```

### Display Options
```python
SHOW_TODAYS_GAMES = True        # Display today's game predictions
SHOW_PROGRESS_EVERY = 2000      # Print progress every N simulations
```

## Output Files

All output files are organized in the `data/` directory:

- `data/schedule/schedule_YYYY_YYYY.csv` - Full season schedule
- `data/db/nhl_YYYY_YYYY_players.db` - SQLite database of player stats
- `data/results/nhl_predictions_YYYYMMDD.csv` - Simulation results

## Project Structure

```
nhl_model/
├── main.py                   # Entry point
├── config.py                 # Configuration settings
├── nhl_schedule.py          # Schedule scraping
├── nhl_rosters.py           # Player data management
├── team_strength.py         # Team rating calculations
├── game_simulation.py       # Single game simulation
├── playoff_simulation.py    # Playoff bracket simulation
├── season_simulation.py     # Full season simulation
└── data/                    # Output directory
    ├── db/                  # Player databases
    ├── schedule/            # Schedule files
    └── results/             # Prediction results
```

## How It Works

### 1. Data Collection
- Scrapes season schedule from Hockey-Reference
- Downloads live 5v5 player stats (xGF, xGA, TOI) from Natural Stat Trick
- Stores player data in SQLite database

### 2. Team Strength Calculation
- Aggregates player-level xGF and xGA for each team
- Calculates team offensive rating (xGF/60) and defensive rating (xGA/60)
- Applies minimum TOI filter to exclude low-usage players
- Falls back to league averages if insufficient data

### 3. Game Simulation
- Uses Poisson distribution based on team strength ratings
- Applies home ice advantage (default 1.10x multiplier)
- Adds game-to-game variance (±8%) to simulate injuries, form, etc.
- Handles overtime/shootout with historical probability (55% home win rate)

### 4. Season Simulation
- Simulates all remaining games in the schedule
- Calculates standings with proper tiebreakers (points, ROW, OTW, GF-GA)
- Determines playoff teams (top 3 per division + 2 wildcards per conference)

### 5. Playoff Simulation
- Seeds teams by final standings
- Simulates best-of-7 series with home ice advantage
- Runs conference playoffs (East and West)
- Simulates Stanley Cup Final

### 6. Results Aggregation
- Runs thousands of simulations
- Calculates probabilities for each team:
  - Making playoffs
  - Winning President's Trophy
  - Winning Stanley Cup

## Model Philosophy

This model balances realism with computational efficiency:

- **Player-Based**: Uses actual player stats, not team-level averages
- **Dynamic**: Updates with current season data on each run
- **Variance-Aware**: Incorporates randomness to reflect real-world unpredictability
- **Transparent**: All parameters are configurable and documented
- **Fast**: Modular design allows for optimization and parallelization

## Customization

### Adjust Simulation Count
For faster testing, reduce simulation counts in `config.py`:
```python
N_SIMS_FULL = 100  # Quick test
N_SIMS_FULL = 10000  # High accuracy
```

### Modify Variance
To make results more or less random:
```python
TEAM_STRENGTH_VARIANCE = 0.05  # Less variance (more predictable)
TEAM_STRENGTH_VARIANCE = 0.12  # More variance (more chaos)
```

### Change Team Mappings
If new teams are added or abbreviations change, update `TEAM_ABBREV_FIXES` in `config.py`.

## Troubleshooting

### "Schedule table not found"
Hockey-Reference may have changed their HTML structure. Check `nhl_schedule.py` and update the scraping logic.

### "NST download failed"
Natural Stat Trick may be down or have changed their format. The model will fall back to league average ratings.

### Very slow performance
- Reduce `N_SIMS_FULL` in config.py
- Consider using PyPy instead of CPython
- Implement parallel processing for multiple cores

## Future Enhancements

Potential improvements:
- Add special teams (power play/penalty kill) modeling
- Incorporate goalie stats separately from skater stats
- Add trade deadline / roster change tracking
- Web interface for interactive predictions
- Historical validation against past seasons
- Team-specific home ice advantages

## License

This project is for educational and research purposes.

## Acknowledgments

- Data sources: Hockey-Reference and Natural Stat Trick
- Inspired by advanced hockey analytics and Monte Carlo simulation methods
