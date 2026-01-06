# main.py
# NHL Monte Carlo Model - Main Entry Point

import pandas as pd
import time
from config import *
from nhl_schedule import scrape_schedule, get_todays_games
from nhl_rosters import download_nst_data
from game_simulation import predict_todays_games
from season_simulation import build_current_standings, simulate_full_season, display_playoff_matchups
from visualization import generate_all_visualizations

# Header
print("=" * 100)
print(f"NHL MONTE CARLO PRO — {CURRENT_SEASON_FULL} SEASON".center(100))
print(f"Live 5v5 xGF/xGA model | {N_SIMS_FULL:,} simulations | Today: {TODAY_PRETTY}".center(100))
print("=" * 100)

# Step 1: Scrape schedule
schedule = scrape_schedule(output_path=SCHEDULE_CSV)

# Step 2: Build current standings
current_standings = build_current_standings(schedule)

# Step 3: Download player data
download_nst_data(DB_FILE, recent_weight=RECENT_FORM_WEIGHT)

# Step 4: Today's games predictions (if enabled)
if SHOW_TODAYS_GAMES:
    print("\n" + "=" * 88)
    print(f"TODAY'S NHL GAMES — {TODAY_PRETTY} — LIVE MODEL ODDS ({N_SIMS_TODAY:,} sims each)")
    print("=" * 88)

    today_games = get_todays_games(schedule, TODAY_STR)

    if today_games.empty:
        print("   No games scheduled today.\n")
    else:
        predictions = predict_todays_games(today_games, DB_FILE)

        for pred in predictions:
            print(f"{pred['away']} — {pred['away_avg_goals']:.2f} GF — {pred['away_pct']:.1%} to win")
            print(f"{pred['home']} — {pred['home_avg_goals']:.2f} GF — {pred['home_pct']:.1%} to win")
            print(f"   → Favorite: {pred['favorite']} | Expected Total: ~{pred['expected_total']}")
            print("-" * 60)

        # Generate today's games visualization
        if ENABLE_VISUALIZATIONS:
            viz_paths = generate_all_visualizations(
                today_predictions=predictions,
                n_sims_today=N_SIMS_TODAY,
                date_str=TODAY_PRETTY
            )
            if viz_paths.get('today_games'):
                print(f"   Today's games chart saved → {viz_paths['today_games']}\n")

    print("=" * 88 + "\n")

# Step 5: Full season Monte Carlo simulations
start_time = time.time()
(playoff_counter, round1_counter, round2_counter, conf_finals_counter,
 cup_counter, pres_counter, seeding_counter, matchup_counter,
 round2_matchup_counter, conf_finals_matchup_counter,
 cup_finals_matchup_counter, bracket_path_counter) = simulate_full_season(
    schedule,
    current_standings,
    N_SIMS_FULL,
    DB_FILE,
    show_progress_every=SHOW_PROGRESS_EVERY
)
elapsed = time.time() - start_time

# Step 6: Generate and display results
all_teams = sorted(current_standings.team.unique())
results = []

for team in all_teams:
    results.append({
        "Team": team,
        "Playoff %": f"{playoff_counter[team]/N_SIMS_FULL:.1%}",
        "Round 2 %": f"{round1_counter[team]/N_SIMS_FULL:.1%}",
        "Conf Finals %": f"{round2_counter[team]/N_SIMS_FULL:.1%}",
        "Finals %": f"{conf_finals_counter[team]/N_SIMS_FULL:.1%}",
        "Stanley Cup %": f"{cup_counter[team]/N_SIMS_FULL:.1%}",
        "President's Trophy %": f"{pres_counter[team]/N_SIMS_FULL:.1%}",
        "_cup": cup_counter[team]/N_SIMS_FULL,
        "_playoff": playoff_counter[team]/N_SIMS_FULL
    })

final_df = pd.DataFrame(results).sort_values(
    ["_playoff", "_cup"],
    ascending=False
).drop(columns=["_cup", "_playoff"])

# Display playoff seedings and matchups for all rounds
display_playoff_matchups(
    seeding_counter, matchup_counter, N_SIMS_FULL,
    round2_matchup_counter=round2_matchup_counter,
    conf_finals_matchup_counter=conf_finals_matchup_counter,
    cup_finals_matchup_counter=cup_finals_matchup_counter,
    bracket_path_counter=bracket_path_counter
)

print("\n" + "=" * 120)
print(f"NHL {CURRENT_SEASON_FULL} FINAL RESULTS — {N_SIMS_FULL:,} sims in {elapsed:.0f}s".center(120))
print("=" * 120)
print(final_df.to_string(index=False))
print(f"\nResults saved → {PREDICTIONS_CSV}")
final_df.to_csv(PREDICTIONS_CSV, index=False)

# Generate all probability visualizations
if ENABLE_VISUALIZATIONS:
    # Convert percentage strings back to floats for visualization
    viz_df = final_df.copy()
    percentage_cols = ["Playoff %", "Round 2 %", "Conf Finals %",
                       "Finals %", "Stanley Cup %", "President's Trophy %"]
    for col in percentage_cols:
        viz_df[col] = viz_df[col].str.rstrip('%').astype(float) / 100

    viz_paths = generate_all_visualizations(
        results_df=viz_df,
        n_sims_full=N_SIMS_FULL,
        date_str=TODAY_PRETTY
    )

    print("\nVisualizations saved:")
    for chart_type, path in viz_paths.items():
        if path and chart_type != 'today_games':  # Don't duplicate today's games message
            print(f"  - {chart_type}: {path}")

if SHOW_ROSTER_DUMP:
    from nhl_rosters import view_team_rosters
    view_team_rosters(DB_FILE)