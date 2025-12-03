# season_simulation.py
# Season simulation, standings, and playoff qualification logic

import pandas as pd
from collections import defaultdict, Counter
from tqdm import tqdm
from game_simulation import simulate_game
from playoff_simulation import simulate_playoffs

# NHL Divisions
DIVISIONS = {
    "Atlantic": ["Boston Bruins", "Buffalo Sabres", "Detroit Red Wings", "Florida Panthers",
                 "Montreal Canadiens", "Ottawa Senators", "Tampa Bay Lightning", "Toronto Maple Leafs"],
    "Metropolitan": ["Carolina Hurricanes", "Columbus Blue Jackets", "New Jersey Devils", "New York Islanders",
                     "New York Rangers", "Philadelphia Flyers", "Pittsburgh Penguins", "Washington Capitals"],
    "Central": ["Chicago Blackhawks", "Colorado Avalanche", "Dallas Stars", "Minnesota Wild",
                "Nashville Predators", "St. Louis Blues", "Utah Hockey Club", "Winnipeg Jets"],
    "Pacific": ["Anaheim Ducks", "Calgary Flames", "Edmonton Oilers", "Los Angeles Kings",
                "San Jose Sharks", "Seattle Kraken", "Vancouver Canucks", "Vegas Golden Knights"]
}


def build_current_standings(schedule_df):
    """
    Calculate current standings from completed games.

    Args:
        schedule_df (pd.DataFrame): Full schedule with played games marked

    Returns:
        pd.DataFrame: Current standings with points, ROW, OTW, GF, GA
    """
    standings = defaultdict(lambda: {"points": 0, "row": 0, "gf": 0, "ga": 0, "gp": 0})

    for _, g in schedule_df[schedule_df.played].iterrows():
        h, a = g.home, g.visitor
        standings[h]["gf"] += g.hg
        standings[h]["ga"] += g.vg
        standings[h]["gp"] += 1
        standings[a]["gf"] += g.vg
        standings[a]["ga"] += g.hg
        standings[a]["gp"] += 1

        if g.hg > g.vg and g.ot == "":
            standings[h]["points"] += 2
            standings[h]["row"] += 1
        elif g.vg > g.hg and g.ot == "":
            standings[a]["points"] += 2
            standings[a]["row"] += 1
        elif g.hg > g.vg:
            standings[h]["points"] += 2
            standings[h]["row"] += 1  # ROW includes OT/SO wins
            standings[a]["points"] += 1
        else:
            standings[a]["points"] += 2
            standings[a]["row"] += 1  # ROW includes OT/SO wins
            standings[h]["points"] += 1

    df = pd.DataFrame.from_dict(standings, orient="index").reset_index().rename(columns={"index": "team"})
    df["gf-ga"] = df["gf"] - df["ga"]
    return df


def get_playoff_teams(final_standings):
    """
    Determine playoff teams from final standings.

    Args:
        final_standings (pd.DataFrame): Final season standings

    Returns:
        list: 16 playoff team names
    """
    playoff = []

    # Top 3 from each division
    for div, teams in DIVISIONS.items():
        div_df = final_standings[final_standings.team.isin(teams)].copy()
        div_df = div_df.sort_values(by=["points", "row", "gf-ga", "gf"], ascending=False)
        playoff.extend(div_df.head(3).team.tolist())

    # Wildcards
    remaining = final_standings[~final_standings.team.isin(playoff)].copy()
    east = DIVISIONS["Atlantic"] + DIVISIONS["Metropolitan"]
    west = DIVISIONS["Central"] + DIVISIONS["Pacific"]

    playoff.extend(remaining[remaining.team.isin(east)].head(2).team.tolist())
    playoff.extend(remaining[remaining.team.isin(west)].head(2).team.tolist())

    return list(dict.fromkeys(playoff))[:16]  # dedup & cap at 16


def simulate_full_season(schedule_df, current_standings, n_sims, db_path, show_progress_every=None):
    """
    Run full season Monte Carlo simulations.

    Args:
        schedule_df (pd.DataFrame): Full season schedule
        current_standings (pd.DataFrame): Current standings before simulation
        n_sims (int): Number of simulations to run
        db_path (str): Path to player database
        show_progress_every (int, optional): Print progress every N simulations

    Returns:
        tuple: (playoff_counter, round1_counter, round2_counter, conf_finals_counter, cup_counter, pres_counter)
    """
    remaining_games = schedule_df[~schedule_df.played]
    all_teams = sorted(current_standings.team.unique())

    playoff_counter = Counter()
    round1_counter = Counter()
    round2_counter = Counter()
    conf_finals_counter = Counter()
    cup_counter = Counter()
    pres_counter = Counter()

    print(f"\nRunning {n_sims:,} full-season simulations on {len(remaining_games)} games...")

    for sim in tqdm(range(n_sims), desc="Season simulations", unit="sim"):
        standings = current_standings.copy(deep=True)

        # Simulate remaining games
        for _, game in remaining_games.iterrows():
            home, away = game.home, game.visitor
            winner, hpts, apts, hgf, agf, reg = simulate_game(home, away, db_path)

            h_idx = standings[standings.team == home].index[0]
            a_idx = standings[standings.team == away].index[0]

            standings.loc[h_idx, ["points", "gf", "ga"]] += [hpts, hgf, agf]
            standings.loc[a_idx, ["points", "gf", "ga"]] += [apts, agf, hgf]
            if hpts == 2:  # ROW includes all 2-pt wins (regulation + OT/SO)
                standings.loc[h_idx, "row"] += 1
            if apts == 2:  # ROW includes all 2-pt wins
                standings.loc[a_idx, "row"] += 1

        standings["gf-ga"] = standings["gf"] - standings["ga"]
        final = standings.sort_values(
            by=["points", "row", "gf-ga", "gf"],
            ascending=False
        ).reset_index(drop=True)

        # President's Trophy winner
        pres_counter[final.iloc[0].team] += 1

        # Playoff teams
        playoff_teams = get_playoff_teams(final)
        for t in playoff_teams:
            playoff_counter[t] += 1

        # Simulate playoffs and track each round
        playoff_results = simulate_playoffs(playoff_teams, final, db_path)
        
        # Count teams advancing through each round
        for team in playoff_results['round1']:
            round1_counter[team] += 1
        
        for team in playoff_results['round2']:
            round2_counter[team] += 1
        
        for team in playoff_results['conf_finals']:
            conf_finals_counter[team] += 1
        
        if playoff_results['cup_winner']:
            cup_counter[playoff_results['cup_winner']] += 1

    return playoff_counter, round1_counter, round2_counter, conf_finals_counter, cup_counter, pres_counter