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
    standings = defaultdict(lambda: {"points": 0, "row": 0, "otw": 0, "gf": 0, "ga": 0, "gp": 0})

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
            standings[h]["otw"] += 1
            standings[a]["points"] += 1
        else:
            standings[a]["points"] += 2
            standings[a]["otw"] += 1
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
        div_df = div_df.sort_values(by=["points", "row", "otw", "gf-ga", "gf"], ascending=False)
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
        tuple: (playoff_counter, cup_counter, pres_counter) as Counter objects
    """
    remaining_games = schedule_df[~schedule_df.played]
    all_teams = sorted(current_standings.team.unique())

    playoff_counter = Counter()
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
            if hpts == 2 and reg:
                standings.loc[h_idx, "row"] += 1
            if apts == 2 and reg:
                standings.loc[a_idx, "row"] += 1
            if hpts == 2:
                standings.loc[h_idx, "otw"] += 1
            if apts == 2:
                standings.loc[a_idx, "otw"] += 1

        standings["gf-ga"] = standings["gf"] - standings["ga"]
        final = standings.sort_values(
            by=["points", "row", "otw", "gf-ga", "gf"],
            ascending=False
        ).reset_index(drop=True)

        # President's Trophy winner
        pres_counter[final.iloc[0].team] += 1

        # Playoff teams
        playoff_teams = get_playoff_teams(final)
        for t in playoff_teams:
            playoff_counter[t] += 1

        # Simulate playoffs
        cup_winner = simulate_playoffs(playoff_teams, final, db_path)
        if cup_winner:
            cup_counter[cup_winner] += 1

    return playoff_counter, cup_counter, pres_counter
