# playoff_simulation.py
# NHL playoff bracket simulation logic

from game_simulation import simulate_game

# NHL Divisions (for determining conferences)
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


def best_of_7(team1, team2, home_first, db_path,
              starting_wins=(0, 0), starting_game=0):
    """
    Simulate a best-of-7 playoff series using NHL's 2-2-1-1-1 format.
    Optionally resume from a partially-played state.

    Args:
        team1 (str): First team (higher seed by convention)
        team2 (str): Second team
        home_first (bool): Whether team1 had home ice in Game 1
        db_path (str): Path to player database
        starting_wins (tuple): (wins1, wins2) — current series score
        starting_game (int): Number of games already played (resumes Game N+1)

    Returns:
        str: Winning team name
    """
    wins1, wins2 = starting_wins
    game_num = starting_game

    # 2-2-1-1-1 home pattern for the team with home-ice (team1 if home_first=True)
    home_pattern = [True, True, False, False, True, False, True]

    # Defensive: if state already says someone won, return them
    if wins1 >= 4:
        return team1
    if wins2 >= 4:
        return team2

    while wins1 < 4 and wins2 < 4:
        team1_at_home = home_pattern[game_num] if home_first else not home_pattern[game_num]

        winner = simulate_game(
            team1 if team1_at_home else team2,
            team2 if team1_at_home else team1,
            db_path
        )[0]

        if winner == team1:
            wins1 += 1
        else:
            wins2 += 1

        game_num += 1

    return team1 if wins1 == 4 else team2


def _resolve_series(slot, playoff_state, fallback_team1, fallback_team2,
                    fallback_home_first, db_path):
    """
    Return the winner of a series slot.

    If the slot has known state (completed or in progress), use it.
    Otherwise fall back to a fresh best-of-7 between the two passed teams.
    """
    s = playoff_state['series'].get(slot) if playoff_state else None
    if s is None:
        # Future series with no recorded state yet — fresh sim
        return best_of_7(fallback_team1, fallback_team2, fallback_home_first, db_path)

    if s['completed']:
        return s['winner']

    # In-progress series: resume from current score
    return best_of_7(
        s['team1'], s['team2'], s['home_first'], db_path,
        starting_wins=(s['wins1'], s['wins2']),
        starting_game=s['games_played'],
    )


def simulate_playoffs(playoff_teams, final_standings, db_path):
    """
    Simulate the full NHL playoff bracket using proper divisional format.

    NHL Playoff Format (2013-present):
    - Division winners get seeds 1-2 (by points)
    - Division 2nd/3rd fill seeds 3-6
    - Wildcards get seeds 7-8
    - Round 1: Divisional matchups (1vWC2, 3v4, 2vWC1, 5v6)
    - Rounds 2+: Divisional semifinals within each division bracket

    Args:
        playoff_teams (list): List of 16 playoff team names
        final_standings (pd.DataFrame): Final season standings (for seeding)
        db_path (str): Path to player database

    Returns:
        dict: Dictionary with playoff results by round, including matchup details
    """
    results = {
        'round1': [],
        'round2': [],
        'conf_finals': [],
        'cup_winner': None,
        # Detailed matchup tracking for each round
        'round1_matchups': {
            'east': [],  # List of (team1, team2, winner) tuples
            'west': []
        },
        'round2_matchups': {
            'east': [],  # List of (team1, team2, winner) tuples
            'west': []
        },
        'conf_finals_matchups': {
            'east': None,  # (team1, team2, winner) tuple
            'west': None
        },
        'cup_finals_matchup': None,  # (east_champ, west_champ, winner) tuple
        'east_champ': None,
        'west_champ': None
    }

    def get_divisional_seeding(div1_name, div2_name, playoff_teams, final_standings):
        """
        Get proper NHL divisional seeding for a conference.

        Returns:
            tuple: (div1_teams, div2_teams, wildcards) where div1 has higher-points winner
        """
        # Get playoff teams from each division
        div1_playoff = [t for t in playoff_teams if t in DIVISIONS[div1_name]]
        div2_playoff = [t for t in playoff_teams if t in DIVISIONS[div2_name]]

        # Sort by standings
        div1_sorted = final_standings[final_standings.team.isin(div1_playoff)].sort_values(
            by=["points", "row", "gf-ga", "gf"], ascending=False
        ).team.tolist()
        div2_sorted = final_standings[final_standings.team.isin(div2_playoff)].sort_values(
            by=["points", "row", "gf-ga", "gf"], ascending=False
        ).team.tolist()

        # Get division winners' points
        div1_winner_pts = final_standings[final_standings.team == div1_sorted[0]].iloc[0]["points"] if div1_sorted else 0
        div2_winner_pts = final_standings[final_standings.team == div2_sorted[0]].iloc[0]["points"] if div2_sorted else 0

        # Identify top 3 from each division and wildcards
        div1_top3 = div1_sorted[:3]
        div2_top3 = div2_sorted[:3]

        conf_teams = DIVISIONS[div1_name] + DIVISIONS[div2_name]
        wildcards = [t for t in playoff_teams
                     if t in conf_teams and t not in div1_top3 and t not in div2_top3]
        wc_sorted = final_standings[final_standings.team.isin(wildcards)].sort_values(
            by=["points", "row", "gf-ga", "gf"], ascending=False
        ).team.tolist()

        # Higher-points division winner's division becomes "Division 1"
        if div1_winner_pts >= div2_winner_pts:
            return div1_top3, div2_top3, wc_sorted
        else:
            return div2_top3, div1_top3, wc_sorted

    # Get divisional seeding for each conference
    east_div1, east_div2, east_wc = get_divisional_seeding(
        "Atlantic", "Metropolitan", playoff_teams, final_standings
    )
    west_div1, west_div2, west_wc = get_divisional_seeding(
        "Central", "Pacific", playoff_teams, final_standings
    )

    # ROUND 1 - Divisional format
    # Div1: Winner vs WC2, 2nd vs 3rd
    # Div2: Winner vs WC1, 2nd vs 3rd

    east_r1 = []
    if len(east_div1) >= 3 and len(east_wc) >= 2:
        # Division 1 bracket
        winner1 = best_of_7(east_div1[0], east_wc[1], home_first=True, db_path=db_path)  # Div1 winner vs WC2
        east_r1.append(winner1)
        results['round1_matchups']['east'].append((east_div1[0], east_wc[1], winner1))

        winner2 = best_of_7(east_div1[1], east_div1[2], home_first=True, db_path=db_path)  # Div1: 2nd vs 3rd
        east_r1.append(winner2)
        results['round1_matchups']['east'].append((east_div1[1], east_div1[2], winner2))

        # Division 2 bracket
        winner3 = best_of_7(east_div2[0], east_wc[0], home_first=True, db_path=db_path)  # Div2 winner vs WC1
        east_r1.append(winner3)
        results['round1_matchups']['east'].append((east_div2[0], east_wc[0], winner3))

        winner4 = best_of_7(east_div2[1], east_div2[2], home_first=True, db_path=db_path)  # Div2: 2nd vs 3rd
        east_r1.append(winner4)
        results['round1_matchups']['east'].append((east_div2[1], east_div2[2], winner4))

    results['round1'].extend(east_r1)

    west_r1 = []
    if len(west_div1) >= 3 and len(west_wc) >= 2:
        winner1 = best_of_7(west_div1[0], west_wc[1], home_first=True, db_path=db_path)
        west_r1.append(winner1)
        results['round1_matchups']['west'].append((west_div1[0], west_wc[1], winner1))

        winner2 = best_of_7(west_div1[1], west_div1[2], home_first=True, db_path=db_path)
        west_r1.append(winner2)
        results['round1_matchups']['west'].append((west_div1[1], west_div1[2], winner2))

        winner3 = best_of_7(west_div2[0], west_wc[0], home_first=True, db_path=db_path)
        west_r1.append(winner3)
        results['round1_matchups']['west'].append((west_div2[0], west_wc[0], winner3))

        winner4 = best_of_7(west_div2[1], west_div2[2], home_first=True, db_path=db_path)
        west_r1.append(winner4)
        results['round1_matchups']['west'].append((west_div2[1], west_div2[2], winner4))

    results['round1'].extend(west_r1)

    # ROUND 2 - Divisional semifinals (winners within each division bracket)
    # Div1 bracket winner vs Div1 bracket winner
    # Div2 bracket winner vs Div2 bracket winner
    east_r2 = []
    if len(east_r1) >= 4:
        # Sort within each division bracket by original standing
        east_div1_r2 = sorted(east_r1[:2], key=lambda t: final_standings[final_standings.team == t].index[0])
        east_div2_r2 = sorted(east_r1[2:], key=lambda t: final_standings[final_standings.team == t].index[0])

        winner1 = best_of_7(east_div1_r2[0], east_div1_r2[1], home_first=True, db_path=db_path)
        east_r2.append(winner1)
        results['round2_matchups']['east'].append((east_div1_r2[0], east_div1_r2[1], winner1))

        winner2 = best_of_7(east_div2_r2[0], east_div2_r2[1], home_first=True, db_path=db_path)
        east_r2.append(winner2)
        results['round2_matchups']['east'].append((east_div2_r2[0], east_div2_r2[1], winner2))

    results['round2'].extend(east_r2)

    west_r2 = []
    if len(west_r1) >= 4:
        west_div1_r2 = sorted(west_r1[:2], key=lambda t: final_standings[final_standings.team == t].index[0])
        west_div2_r2 = sorted(west_r1[2:], key=lambda t: final_standings[final_standings.team == t].index[0])

        winner1 = best_of_7(west_div1_r2[0], west_div1_r2[1], home_first=True, db_path=db_path)
        west_r2.append(winner1)
        results['round2_matchups']['west'].append((west_div1_r2[0], west_div1_r2[1], winner1))

        winner2 = best_of_7(west_div2_r2[0], west_div2_r2[1], home_first=True, db_path=db_path)
        west_r2.append(winner2)
        results['round2_matchups']['west'].append((west_div2_r2[0], west_div2_r2[1], winner2))

    results['round2'].extend(west_r2)

    # CONFERENCE FINALS - Division bracket winners play each other
    east_champ = None
    west_champ = None

    if len(east_r2) >= 2:
        east_cf = sorted(east_r2, key=lambda t: final_standings[final_standings.team == t].index[0])
        east_champ = best_of_7(east_cf[0], east_cf[1], home_first=True, db_path=db_path)
        results['conf_finals'].append(east_champ)
        results['conf_finals_matchups']['east'] = (east_cf[0], east_cf[1], east_champ)
    elif len(east_r2) == 1:
        east_champ = east_r2[0]
        results['conf_finals'].append(east_champ)

    if len(west_r2) >= 2:
        west_cf = sorted(west_r2, key=lambda t: final_standings[final_standings.team == t].index[0])
        west_champ = best_of_7(west_cf[0], west_cf[1], home_first=True, db_path=db_path)
        results['conf_finals'].append(west_champ)
        results['conf_finals_matchups']['west'] = (west_cf[0], west_cf[1], west_champ)
    elif len(west_r2) == 1:
        west_champ = west_r2[0]
        results['conf_finals'].append(west_champ)

    # Store conference champions
    results['east_champ'] = east_champ
    results['west_champ'] = west_champ

    # STANLEY CUP FINAL
    if east_champ and west_champ:
        home_first = final_standings[final_standings.team == east_champ].index[0] < \
                     final_standings[final_standings.team == west_champ].index[0]
        cup_winner = best_of_7(east_champ, west_champ, home_first, db_path)
        results['cup_winner'] = cup_winner
        results['cup_finals_matchup'] = (east_champ, west_champ, cup_winner)

    return results


def _seed_priority(team, final_standings):
    rows = final_standings.index[final_standings.team == team]
    return rows[0] if len(rows) else 999


def simulate_playoffs_from_state(playoff_state, final_standings, db_path):
    """
    Simulate the bracket starting from the current real-world state.

    For each slot:
      - completed → lock in the actual winner
      - in progress → resume best_of_7 from current score
      - future (no state yet) → fresh best_of_7 between upstream winners

    Args:
        playoff_state (dict): output of playoff_state.build_playoff_state()
        final_standings (pd.DataFrame): final regular-season standings
        db_path (str): path to player database

    Returns:
        dict: same shape as simulate_playoffs() result
    """
    results = {
        'round1': [], 'round2': [], 'conf_finals': [], 'cup_winner': None,
        'round1_matchups': {'east': [], 'west': []},
        'round2_matchups': {'east': [], 'west': []},
        'conf_finals_matchups': {'east': None, 'west': None},
        'cup_finals_matchup': None,
        'east_champ': None, 'west_champ': None,
    }

    series = playoff_state['series']

    def resolve(slot, fallback_t1=None, fallback_t2=None, fallback_home_first=True):
        s = series.get(slot)
        if s is None:
            # Future series — pair upstream winners (resolved already)
            return best_of_7(fallback_t1, fallback_t2, fallback_home_first, db_path), \
                   (fallback_t1, fallback_t2)
        if s['completed']:
            return s['winner'], (s['team1'], s['team2'])
        winner = best_of_7(
            s['team1'], s['team2'], s['home_first'], db_path,
            starting_wins=(s['wins1'], s['wins2']),
            starting_game=s['games_played'],
        )
        return winner, (s['team1'], s['team2'])

    # ROUND 1
    r1_winners = {}
    for conf in ('east', 'west'):
        for div in ('div1', 'div2'):
            for half in ('top', 'bot'):
                slot = f"R1_{conf}_{div}_{half}"
                winner, (t1, t2) = resolve(slot)
                r1_winners[slot] = winner
                results['round1'].append(winner)
                results['round1_matchups'][conf].append((t1, t2, winner))

    # ROUND 2 — pair top/bot winners within each div bracket
    r2_winners = {}
    for conf in ('east', 'west'):
        for div in ('div1', 'div2'):
            top_w = r1_winners[f"R1_{conf}_{div}_top"]
            bot_w = r1_winners[f"R1_{conf}_{div}_bot"]
            # Higher seed (lower standings index) gets home ice
            if _seed_priority(top_w, final_standings) <= _seed_priority(bot_w, final_standings):
                fb_t1, fb_t2 = top_w, bot_w
            else:
                fb_t1, fb_t2 = bot_w, top_w
            slot = f"R2_{conf}_{div}"
            winner, (t1, t2) = resolve(slot, fb_t1, fb_t2, True)
            r2_winners[slot] = winner
            results['round2'].append(winner)
            results['round2_matchups'][conf].append((t1, t2, winner))

    # CONFERENCE FINALS
    cf_winners = {}
    for conf in ('east', 'west'):
        d1_w = r2_winners[f"R2_{conf}_div1"]
        d2_w = r2_winners[f"R2_{conf}_div2"]
        if _seed_priority(d1_w, final_standings) <= _seed_priority(d2_w, final_standings):
            fb_t1, fb_t2 = d1_w, d2_w
        else:
            fb_t1, fb_t2 = d2_w, d1_w
        slot = f"CF_{conf}"
        winner, (t1, t2) = resolve(slot, fb_t1, fb_t2, True)
        cf_winners[conf] = winner
        results['conf_finals'].append(winner)
        results['conf_finals_matchups'][conf] = (t1, t2, winner)

    results['east_champ'] = cf_winners['east']
    results['west_champ'] = cf_winners['west']

    # STANLEY CUP FINAL — east vs west
    e, w = cf_winners['east'], cf_winners['west']
    if _seed_priority(e, final_standings) <= _seed_priority(w, final_standings):
        fb_t1, fb_t2 = e, w
    else:
        fb_t1, fb_t2 = w, e
    cup_winner, (t1, t2) = resolve('SCF', fb_t1, fb_t2, True)
    results['cup_winner'] = cup_winner
    results['cup_finals_matchup'] = (t1, t2, cup_winner)

    return results
