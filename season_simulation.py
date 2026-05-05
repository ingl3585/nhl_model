# season_simulation.py
# Season simulation, standings, and playoff qualification logic

import pandas as pd
from collections import defaultdict, Counter
from tqdm import tqdm
from game_simulation import simulate_game
from playoff_simulation import simulate_playoffs, simulate_playoffs_from_state

# NHL Divisions
DIVISIONS = {
    "Atlantic": ["Boston Bruins", "Buffalo Sabres", "Detroit Red Wings", "Florida Panthers",
                 "Montreal Canadiens", "Ottawa Senators", "Tampa Bay Lightning", "Toronto Maple Leafs"],
    "Metropolitan": ["Carolina Hurricanes", "Columbus Blue Jackets", "New Jersey Devils", "New York Islanders",
                     "New York Rangers", "Philadelphia Flyers", "Pittsburgh Penguins", "Washington Capitals"],
    "Central": ["Chicago Blackhawks", "Colorado Avalanche", "Dallas Stars", "Minnesota Wild",
                "Nashville Predators", "St. Louis Blues", "Utah Mammoth", "Winnipeg Jets"],
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

    # Track playoff seedings and matchups
    seeding_counter = Counter()  # Track (conference, seed, team) tuples
    matchup_counter = Counter()  # Track Round 1 matchups

    # Track matchups for all rounds
    round2_matchup_counter = Counter()  # Track Round 2 matchups: (conf, team1, team2)
    conf_finals_matchup_counter = Counter()  # Track Conference Finals matchups: (conf, team1, team2)
    cup_finals_matchup_counter = Counter()  # Track Stanley Cup Finals matchups: (east_champ, west_champ)

    # Track complete bracket paths for "most likely outcome"
    bracket_path_counter = Counter()  # Track full bracket outcomes as frozen tuples

    print(f"\nRunning {n_sims:,} full-season simulations on {len(remaining_games)} games...")

    for sim in tqdm(range(n_sims), desc="Season simulations", unit="sim"):
        standings = current_standings.copy(deep=True)

        # Simulate remaining games
        for _, game in remaining_games.iterrows():
            home, away = game.home, game.visitor
            winner, hpts, apts, hgf, agf, win_type = simulate_game(home, away, db_path)

            h_idx = standings[standings.team == home].index[0]
            a_idx = standings[standings.team == away].index[0]

            standings.loc[h_idx, ["points", "gf", "ga"]] += [hpts, hgf, agf]
            standings.loc[a_idx, ["points", "gf", "ga"]] += [apts, agf, hgf]
            # ROW = Regulation + Overtime Wins (excludes shootouts)
            if hpts == 2 and win_type != 'SO':
                standings.loc[h_idx, "row"] += 1
            if apts == 2 and win_type != 'SO':
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

        # Track seedings and matchups using proper NHL divisional format
        # EASTERN CONFERENCE
        atlantic_playoff = [t for t in playoff_teams if t in DIVISIONS["Atlantic"]]
        metro_playoff = [t for t in playoff_teams if t in DIVISIONS["Metropolitan"]]

        # Sort each division by standings
        atlantic_sorted = final[final.team.isin(atlantic_playoff)].sort_values(
            by=["points", "row", "gf-ga", "gf"], ascending=False
        ).team.tolist()
        metro_sorted = final[final.team.isin(metro_playoff)].sort_values(
            by=["points", "row", "gf-ga", "gf"], ascending=False
        ).team.tolist()

        # Determine division winners and their points
        atlantic_winner = atlantic_sorted[0] if atlantic_sorted else None
        metro_winner = metro_sorted[0] if metro_sorted else None

        atlantic_winner_pts = final[final.team == atlantic_winner].iloc[0]["points"] if atlantic_winner else 0
        metro_winner_pts = final[final.team == metro_winner].iloc[0]["points"] if metro_winner else 0

        # Identify wildcards (teams in playoff but not top 3 in their division)
        atlantic_top3 = atlantic_sorted[:3]
        metro_top3 = metro_sorted[:3]
        east_wildcards = [t for t in playoff_teams
                         if t in DIVISIONS["Atlantic"] + DIVISIONS["Metropolitan"]
                         and t not in atlantic_top3 and t not in metro_top3]

        # Sort wildcards by points
        east_wc_sorted = final[final.team.isin(east_wildcards)].sort_values(
            by=["points", "row", "gf-ga", "gf"], ascending=False
        ).team.tolist()

        # Build proper seeding: Higher-points division winner gets seed 1
        if atlantic_winner_pts >= metro_winner_pts:
            div1_teams = atlantic_sorted[:3]  # A1, A2, A3
            div2_teams = metro_sorted[:3]     # B1, B2, B3
        else:
            div1_teams = metro_sorted[:3]
            div2_teams = atlantic_sorted[:3]

        # Assign wildcards: WC1 goes to Div2 winner, WC2 goes to Div1 winner
        wc1 = east_wc_sorted[0] if len(east_wc_sorted) > 0 else None
        wc2 = east_wc_sorted[1] if len(east_wc_sorted) > 1 else None

        # East seeds: 1=Div1 winner, 2=Div2 winner, 3=Div1 2nd, 4=Div1 3rd,
        #             5=Div2 2nd, 6=Div2 3rd, 7=WC1, 8=WC2
        east_seeds = []
        if len(div1_teams) >= 1: east_seeds.append(div1_teams[0])  # Seed 1
        if len(div2_teams) >= 1: east_seeds.append(div2_teams[0])  # Seed 2
        if len(div1_teams) >= 2: east_seeds.append(div1_teams[1])  # Seed 3
        if len(div1_teams) >= 3: east_seeds.append(div1_teams[2])  # Seed 4
        if len(div2_teams) >= 2: east_seeds.append(div2_teams[1])  # Seed 5
        if len(div2_teams) >= 3: east_seeds.append(div2_teams[2])  # Seed 6
        if wc1: east_seeds.append(wc1)  # Seed 7 (WC1)
        if wc2: east_seeds.append(wc2)  # Seed 8 (WC2)

        # Record Eastern seedings
        for seed, team in enumerate(east_seeds, 1):
            seeding_counter[("Eastern", seed, team)] += 1

        # Record Eastern Round 1 matchups (divisional format)
        # Div1: Seed 1 vs WC2 (seed 8), Seed 3 vs Seed 4
        # Div2: Seed 2 vs WC1 (seed 7), Seed 5 vs Seed 6
        if len(east_seeds) >= 8:
            matchup_counter[("Eastern", 1, east_seeds[0], 8, east_seeds[7])] += 1  # 1 vs WC2
            matchup_counter[("Eastern", 3, east_seeds[2], 4, east_seeds[3])] += 1  # Div1: 2nd vs 3rd
            matchup_counter[("Eastern", 2, east_seeds[1], 7, east_seeds[6])] += 1  # 2 vs WC1
            matchup_counter[("Eastern", 5, east_seeds[4], 6, east_seeds[5])] += 1  # Div2: 2nd vs 3rd

        # WESTERN CONFERENCE
        central_playoff = [t for t in playoff_teams if t in DIVISIONS["Central"]]
        pacific_playoff = [t for t in playoff_teams if t in DIVISIONS["Pacific"]]

        central_sorted = final[final.team.isin(central_playoff)].sort_values(
            by=["points", "row", "gf-ga", "gf"], ascending=False
        ).team.tolist()
        pacific_sorted = final[final.team.isin(pacific_playoff)].sort_values(
            by=["points", "row", "gf-ga", "gf"], ascending=False
        ).team.tolist()

        central_winner = central_sorted[0] if central_sorted else None
        pacific_winner = pacific_sorted[0] if pacific_sorted else None

        central_winner_pts = final[final.team == central_winner].iloc[0]["points"] if central_winner else 0
        pacific_winner_pts = final[final.team == pacific_winner].iloc[0]["points"] if pacific_winner else 0

        central_top3 = central_sorted[:3]
        pacific_top3 = pacific_sorted[:3]
        west_wildcards = [t for t in playoff_teams
                         if t in DIVISIONS["Central"] + DIVISIONS["Pacific"]
                         and t not in central_top3 and t not in pacific_top3]

        west_wc_sorted = final[final.team.isin(west_wildcards)].sort_values(
            by=["points", "row", "gf-ga", "gf"], ascending=False
        ).team.tolist()

        if central_winner_pts >= pacific_winner_pts:
            div1_teams = central_sorted[:3]
            div2_teams = pacific_sorted[:3]
        else:
            div1_teams = pacific_sorted[:3]
            div2_teams = central_sorted[:3]

        wc1 = west_wc_sorted[0] if len(west_wc_sorted) > 0 else None
        wc2 = west_wc_sorted[1] if len(west_wc_sorted) > 1 else None

        west_seeds = []
        if len(div1_teams) >= 1: west_seeds.append(div1_teams[0])
        if len(div2_teams) >= 1: west_seeds.append(div2_teams[0])
        if len(div1_teams) >= 2: west_seeds.append(div1_teams[1])
        if len(div1_teams) >= 3: west_seeds.append(div1_teams[2])
        if len(div2_teams) >= 2: west_seeds.append(div2_teams[1])
        if len(div2_teams) >= 3: west_seeds.append(div2_teams[2])
        if wc1: west_seeds.append(wc1)
        if wc2: west_seeds.append(wc2)

        # Record Western seedings
        for seed, team in enumerate(west_seeds, 1):
            seeding_counter[("Western", seed, team)] += 1

        # Record Western Round 1 matchups (divisional format)
        if len(west_seeds) >= 8:
            matchup_counter[("Western", 1, west_seeds[0], 8, west_seeds[7])] += 1
            matchup_counter[("Western", 3, west_seeds[2], 4, west_seeds[3])] += 1
            matchup_counter[("Western", 2, west_seeds[1], 7, west_seeds[6])] += 1
            matchup_counter[("Western", 5, west_seeds[4], 6, west_seeds[5])] += 1

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

        # Track Round 2 matchups (normalize order for consistent counting)
        for conf in ['east', 'west']:
            for matchup in playoff_results['round2_matchups'][conf]:
                team1, team2, winner = matchup
                # Normalize: alphabetically sort team names for consistent key
                normalized = tuple(sorted([team1, team2]))
                round2_matchup_counter[(conf.upper(), normalized[0], normalized[1])] += 1

        # Track Conference Finals matchups
        for conf in ['east', 'west']:
            matchup = playoff_results['conf_finals_matchups'][conf]
            if matchup:
                team1, team2, winner = matchup
                normalized = tuple(sorted([team1, team2]))
                conf_finals_matchup_counter[(conf.upper(), normalized[0], normalized[1])] += 1

        # Track Stanley Cup Finals matchup
        if playoff_results['cup_finals_matchup']:
            east_champ, west_champ, winner = playoff_results['cup_finals_matchup']
            # Always store as (east, west) for consistency
            cup_finals_matchup_counter[(east_champ, west_champ)] += 1

        # Track complete bracket path for "most likely outcome"
        # Create a hashable representation of the full bracket
        bracket_path = []

        # Round 1 results (8 series)
        for conf in ['east', 'west']:
            for matchup in playoff_results['round1_matchups'][conf]:
                team1, team2, winner = matchup
                bracket_path.append((f"R1_{conf}", team1, team2, winner))

        # Round 2 results (4 series)
        for conf in ['east', 'west']:
            for matchup in playoff_results['round2_matchups'][conf]:
                team1, team2, winner = matchup
                bracket_path.append((f"R2_{conf}", team1, team2, winner))

        # Conference Finals results (2 series)
        for conf in ['east', 'west']:
            matchup = playoff_results['conf_finals_matchups'][conf]
            if matchup:
                team1, team2, winner = matchup
                bracket_path.append((f"CF_{conf}", team1, team2, winner))

        # Stanley Cup Final
        if playoff_results['cup_finals_matchup']:
            east_champ, west_champ, winner = playoff_results['cup_finals_matchup']
            bracket_path.append(("SCF", east_champ, west_champ, winner))

        # Convert to tuple for hashing
        bracket_path_counter[tuple(bracket_path)] += 1

    return (playoff_counter, round1_counter, round2_counter, conf_finals_counter,
            cup_counter, pres_counter, seeding_counter, matchup_counter,
            round2_matchup_counter, conf_finals_matchup_counter,
            cup_finals_matchup_counter, bracket_path_counter)


def simulate_playoffs_only(playoff_state, final_standings, n_sims, db_path):
    """
    Run N Monte Carlo simulations of the bracket starting from current playoff state.

    Regular season is locked in (final_standings) and any played playoff games
    constrain their respective series. Returns the same counter shape as
    simulate_full_season() so display_playoff_matchups() works unchanged.
    """
    all_teams = sorted(final_standings.team.unique())

    playoff_counter = Counter()
    round1_counter = Counter()
    round2_counter = Counter()
    conf_finals_counter = Counter()
    cup_counter = Counter()
    pres_counter = Counter()
    seeding_counter = Counter()
    matchup_counter = Counter()
    round2_matchup_counter = Counter()
    conf_finals_matchup_counter = Counter()
    cup_finals_matchup_counter = Counter()
    bracket_path_counter = Counter()

    # Pre-compute the actual playoff teams + seeding (deterministic — regular season is over)
    final = final_standings.sort_values(
        by=["points", "row", "gf-ga", "gf"], ascending=False
    ).reset_index(drop=True)
    pres_winner = final.iloc[0].team

    playoff_teams = get_playoff_teams(final)

    # Compute fixed seedings for each conference (mirrors logic in simulate_full_season)
    east_seeds = _conf_seeding(final, playoff_teams, "Atlantic", "Metropolitan")
    west_seeds = _conf_seeding(final, playoff_teams, "Central", "Pacific")

    print(f"\nRunning {n_sims:,} playoff bracket simulations from current state...")

    for _ in tqdm(range(n_sims), desc="Playoff simulations", unit="sim"):
        # Pres trophy + playoff teams are locked
        pres_counter[pres_winner] += 1
        for t in playoff_teams:
            playoff_counter[t] += 1

        # Record fixed seedings
        for seed, team in enumerate(east_seeds, 1):
            seeding_counter[("Eastern", seed, team)] += 1
        for seed, team in enumerate(west_seeds, 1):
            seeding_counter[("Western", seed, team)] += 1

        if len(east_seeds) >= 8:
            matchup_counter[("Eastern", 1, east_seeds[0], 8, east_seeds[7])] += 1
            matchup_counter[("Eastern", 3, east_seeds[2], 4, east_seeds[3])] += 1
            matchup_counter[("Eastern", 2, east_seeds[1], 7, east_seeds[6])] += 1
            matchup_counter[("Eastern", 5, east_seeds[4], 6, east_seeds[5])] += 1
        if len(west_seeds) >= 8:
            matchup_counter[("Western", 1, west_seeds[0], 8, west_seeds[7])] += 1
            matchup_counter[("Western", 3, west_seeds[2], 4, west_seeds[3])] += 1
            matchup_counter[("Western", 2, west_seeds[1], 7, west_seeds[6])] += 1
            matchup_counter[("Western", 5, west_seeds[4], 6, west_seeds[5])] += 1

        playoff_results = simulate_playoffs_from_state(playoff_state, final, db_path)

        for team in playoff_results['round1']:
            round1_counter[team] += 1
        for team in playoff_results['round2']:
            round2_counter[team] += 1
        for team in playoff_results['conf_finals']:
            conf_finals_counter[team] += 1
        if playoff_results['cup_winner']:
            cup_counter[playoff_results['cup_winner']] += 1

        for conf in ('east', 'west'):
            for matchup in playoff_results['round2_matchups'][conf]:
                team1, team2, _ = matchup
                normalized = tuple(sorted([team1, team2]))
                round2_matchup_counter[(conf.upper(), normalized[0], normalized[1])] += 1

        for conf in ('east', 'west'):
            matchup = playoff_results['conf_finals_matchups'][conf]
            if matchup:
                team1, team2, _ = matchup
                normalized = tuple(sorted([team1, team2]))
                conf_finals_matchup_counter[(conf.upper(), normalized[0], normalized[1])] += 1

        if playoff_results['cup_finals_matchup']:
            east_champ, west_champ, _ = playoff_results['cup_finals_matchup']
            cup_finals_matchup_counter[(east_champ, west_champ)] += 1

        bracket_path = []
        for conf in ('east', 'west'):
            for matchup in playoff_results['round1_matchups'][conf]:
                bracket_path.append((f"R1_{conf}", *matchup))
        for conf in ('east', 'west'):
            for matchup in playoff_results['round2_matchups'][conf]:
                bracket_path.append((f"R2_{conf}", *matchup))
        for conf in ('east', 'west'):
            matchup = playoff_results['conf_finals_matchups'][conf]
            if matchup:
                bracket_path.append((f"CF_{conf}", *matchup))
        if playoff_results['cup_finals_matchup']:
            bracket_path.append(("SCF", *playoff_results['cup_finals_matchup']))

        bracket_path_counter[tuple(bracket_path)] += 1

    return (playoff_counter, round1_counter, round2_counter, conf_finals_counter,
            cup_counter, pres_counter, seeding_counter, matchup_counter,
            round2_matchup_counter, conf_finals_matchup_counter,
            cup_finals_matchup_counter, bracket_path_counter)


def _conf_seeding(final, playoff_teams, div1_name, div2_name):
    """Helper: compute the 8-seed order for a conference from final standings."""
    div1 = DIVISIONS[div1_name]
    div2 = DIVISIONS[div2_name]

    div1_playoff = [t for t in playoff_teams if t in div1]
    div2_playoff = [t for t in playoff_teams if t in div2]

    div1_sorted = final[final.team.isin(div1_playoff)].sort_values(
        by=["points", "row", "gf-ga", "gf"], ascending=False
    ).team.tolist()
    div2_sorted = final[final.team.isin(div2_playoff)].sort_values(
        by=["points", "row", "gf-ga", "gf"], ascending=False
    ).team.tolist()

    div1_top3 = div1_sorted[:3]
    div2_top3 = div2_sorted[:3]

    if not div1_top3 or not div2_top3:
        return []

    div1_pts = final[final.team == div1_top3[0]].iloc[0]["points"]
    div2_pts = final[final.team == div2_top3[0]].iloc[0]["points"]

    conf_teams = div1 + div2
    used = set(div1_top3 + div2_top3)
    wc = final[final.team.isin(conf_teams) & final.team.isin(playoff_teams)
               & ~final.team.isin(used)].sort_values(
        by=["points", "row", "gf-ga", "gf"], ascending=False
    ).team.tolist()[:2]

    if div1_pts >= div2_pts:
        a_top, b_top = div1_top3, div2_top3
    else:
        a_top, b_top = div2_top3, div1_top3

    return a_top[:1] + b_top[:1] + a_top[1:3] + b_top[1:3] + wc


def display_playoff_matchups(seeding_counter, matchup_counter, n_sims,
                             round2_matchup_counter=None, conf_finals_matchup_counter=None,
                             cup_finals_matchup_counter=None, bracket_path_counter=None,
                             cup_counter=None,
                             min_probability=0.05, round_status=None):
    """
    Display most likely playoff seedings and matchups for all rounds.

    When `round_status` is provided (from playoff_state.round_status), sections
    whose outcomes are already locked in are skipped to reduce noise.

    Args:
        seeding_counter (Counter): Counter of (conference, seed, team) tuples
        matchup_counter (Counter): Counter of Round 1 matchup tuples
        n_sims (int): Total number of simulations
        round2_matchup_counter (Counter): Counter of Round 2 matchups
        conf_finals_matchup_counter (Counter): Counter of Conference Finals matchups
        cup_finals_matchup_counter (Counter): Counter of Stanley Cup Finals matchups
        bracket_path_counter (Counter): Counter of complete bracket paths
        min_probability (float): Minimum probability to display (default 5%)
        round_status (dict | None): {'R1','R2','CF','SCF'} -> 'pending'|'active'|'done'
    """
    # In playoff mode, a round's matchups are deterministic when the upstream
    # round is fully decided (the seeds/winners are all known). Skip those.
    show_seedings = round_status is None
    show_r1 = round_status is None
    show_r2 = round_status is None or round_status.get('R1') != 'done'
    show_cf = round_status is None or round_status.get('R2') != 'done'
    show_scf = round_status is None or round_status.get('CF') != 'done'
    show_r1_bracket = round_status is None

    if show_seedings:
        print("\n" + "=" * 80)
        print("MOST LIKELY PLAYOFF SEEDINGS")
        print("=" * 80)

        # Group seedings by conference
        for conf in ["Eastern", "Western"]:
            print(f"\n{conf} Conference:")
            print("-" * 80)

            for seed in range(1, 9):
                # Get all teams that achieved this seed in this conference
                seed_teams = [(team, count) for (c, s, team), count in seeding_counter.items()
                             if c == conf and s == seed]

                if seed_teams:
                    # Sort by frequency
                    seed_teams.sort(key=lambda x: x[1], reverse=True)

                    print(f"\n  Seed #{seed}:")
                    for team, count in seed_teams[:5]:  # Show top 5 most likely
                        prob = count / n_sims
                        if prob >= min_probability:
                            print(f"    {team:30s} {prob*100:5.1f}%  ({count:,}/{n_sims:,})")

    if show_r1:
        print("\n" + "=" * 80)
        print("MOST LIKELY ROUND 1 MATCHUPS")
        print("=" * 80)

        # Group matchups by conference and series
        for conf in ["Eastern", "Western"]:
            print(f"\n{conf} Conference:")
            print("-" * 80)

            # Group by series type (divisional format: 1v8, 3v4, 2v7, 5v6)
            # Div1: 1vWC2, 3v4  |  Div2: 2vWC1, 5v6
            for series_seeds in [(1, 8), (3, 4), (2, 7), (5, 6)]:
                seed1, seed2 = series_seeds

                # Get all matchups for this series
                series_matchups = [(key, count) for key, count in matchup_counter.items()
                                  if key[0] == conf and key[1] == seed1 and key[3] == seed2]

                if not series_matchups:
                    continue

                series_matchups.sort(key=lambda x: x[1], reverse=True)

                # Show top 5 for each series
                print(f"\n  ({seed1}) vs ({seed2}):")
                displayed = 0
                for matchup, count in series_matchups[:10]:
                    _, s1, team1, s2, team2 = matchup
                    prob = count / n_sims
                    if prob >= min_probability or displayed < 3:  # Show at least top 3
                        print(f"    {team1:28s} vs {team2:28s}  {prob*100:5.1f}%  ({count:,}/{n_sims:,})")
                        displayed += 1
                        if displayed >= 5:  # Cap at 5 per series
                            break

    # Display Round 2 matchups
    if show_r2 and round2_matchup_counter:
        print("\n" + "=" * 80)
        print("MOST LIKELY ROUND 2 (SECOND ROUND) MATCHUPS")
        print("=" * 80)

        for conf in ["EAST", "WEST"]:
            conf_display = "Eastern" if conf == "EAST" else "Western"
            print(f"\n{conf_display} Conference:")
            print("-" * 80)

            # Get all Round 2 matchups for this conference
            conf_matchups = [(key, count) for key, count in round2_matchup_counter.items()
                            if key[0] == conf]

            if conf_matchups:
                conf_matchups.sort(key=lambda x: x[1], reverse=True)

                displayed = 0
                for matchup, count in conf_matchups[:10]:
                    _, team1, team2 = matchup
                    prob = count / n_sims
                    if prob >= min_probability or displayed < 5:
                        print(f"    {team1:28s} vs {team2:28s}  {prob*100:5.1f}%  ({count:,}/{n_sims:,})")
                        displayed += 1
                        if displayed >= 10:
                            break

    # Display Conference Finals matchups
    if show_cf and conf_finals_matchup_counter:
        print("\n" + "=" * 80)
        print("MOST LIKELY CONFERENCE FINALS MATCHUPS")
        print("=" * 80)

        for conf in ["EAST", "WEST"]:
            conf_display = "Eastern" if conf == "EAST" else "Western"
            print(f"\n{conf_display} Conference Final:")
            print("-" * 80)

            # Get all Conference Finals matchups for this conference
            conf_matchups = [(key, count) for key, count in conf_finals_matchup_counter.items()
                            if key[0] == conf]

            if conf_matchups:
                conf_matchups.sort(key=lambda x: x[1], reverse=True)

                displayed = 0
                for matchup, count in conf_matchups[:10]:
                    _, team1, team2 = matchup
                    prob = count / n_sims
                    if prob >= min_probability or displayed < 5:
                        print(f"    {team1:28s} vs {team2:28s}  {prob*100:5.1f}%  ({count:,}/{n_sims:,})")
                        displayed += 1
                        if displayed >= 10:
                            break

    # Display Stanley Cup Finals matchups + most likely champion
    if show_scf and cup_finals_matchup_counter:
        print("\n" + "=" * 80)
        print("MOST LIKELY STANLEY CUP FINALS MATCHUP")
        print("=" * 80)

        cup_matchups = list(cup_finals_matchup_counter.items())
        cup_matchups.sort(key=lambda x: x[1], reverse=True)

        displayed = 0
        for matchup, count in cup_matchups[:15]:
            east_champ, west_champ = matchup
            prob = count / n_sims
            if prob >= min_probability or displayed < 5:
                print(f"    {east_champ:28s} vs {west_champ:28s}  {prob*100:5.1f}%  ({count:,}/{n_sims:,})")
                displayed += 1
                if displayed >= 15:
                    break

        if cup_counter:
            print()
            print("  Most Likely Stanley Cup Champion:")
            print("  " + "-" * 78)
            top_champs = cup_counter.most_common(10)
            displayed = 0
            for team, count in top_champs:
                prob = count / n_sims
                if prob >= min_probability or displayed < 5:
                    print(f"    {team:28s}                                  {prob*100:5.1f}%  ({count:,}/{n_sims:,})")
                    displayed += 1
                    if displayed >= 10:
                        break

    if show_r1_bracket:
        print("\n" + "=" * 80)
        print("MOST LIKELY ROUND 1 BRACKET")
        print("=" * 80)
        print("(Based on most common seeding for each team)")
        print("=" * 80)

        # For each conference, build bracket from most common seeds
        for conf in ["Eastern", "Western"]:
            print(f"\n{conf} Conference:")
            print("-" * 80)

            # Get all seedings for this conference and sort by frequency
            conf_seedings = [(seed, team, count) for (c, seed, team), count in seeding_counter.items() if c == conf]
            conf_seedings.sort(key=lambda x: x[2], reverse=True)

            # Greedily assign teams to seeds (most frequent first)
            bracket = {}
            used_teams = set()

            for seed, team, count in conf_seedings:
                # If this seed is empty and this team hasn't been assigned yet
                if seed not in bracket and team not in used_teams:
                    bracket[seed] = team
                    used_teams.add(team)

                    # Stop once we have all 8 seeds filled
                    if len(bracket) == 8:
                        break

            # Display the bracket matchups (divisional format)
            if len(bracket) >= 8:
                print(f"  Division 1 (Higher seed):")
                print(f"    (1) {bracket[1]:26s} vs (WC2) {bracket[8]:26s}")
                print(f"    (3) {bracket[3]:26s} vs (4)   {bracket[4]:26s}")
                print(f"  Division 2 (Lower seed):")
                print(f"    (2) {bracket[2]:26s} vs (WC1) {bracket[7]:26s}")
                print(f"    (5) {bracket[5]:26s} vs (6)   {bracket[6]:26s}")
            else:
                print(f"  [Not enough data to construct full bracket - only {len(bracket)} seeds]")

    print("\n" + "=" * 80)