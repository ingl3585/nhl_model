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


def best_of_7(team1, team2, home_first, db_path):
    """
    Simulate a best-of-7 playoff series using NHL's 2-2-1-1-1 format.

    NHL Home Ice Format:
    - Games 1, 2: Higher seed at home
    - Games 3, 4: Lower seed at home
    - Games 5, 7: Higher seed at home
    - Game 6: Lower seed at home

    Args:
        team1 (str): First team (typically higher seed)
        team2 (str): Second team
        home_first (bool): Whether team1 has home ice advantage
        db_path (str): Path to player database

    Returns:
        str: Winning team name
    """
    wins1 = wins2 = 0
    game_num = 0

    # 2-2-1-1-1 format: Games at home for higher seed (if home_first=True)
    # Game 1: home, Game 2: home, Game 3: away, Game 4: away,
    # Game 5: home, Game 6: away, Game 7: home
    home_pattern = [True, True, False, False, True, False, True]

    while wins1 < 4 and wins2 < 4:
        # Determine home team based on 2-2-1-1-1 pattern
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
        dict: Dictionary with playoff results by round
    """
    results = {
        'round1': [],
        'round2': [],
        'conf_finals': [],
        'cup_winner': None
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
        east_r1.append(best_of_7(east_div1[0], east_wc[1], home_first=True, db_path=db_path))  # Div1 winner vs WC2
        east_r1.append(best_of_7(east_div1[1], east_div1[2], home_first=True, db_path=db_path))  # Div1: 2nd vs 3rd
        # Division 2 bracket
        east_r1.append(best_of_7(east_div2[0], east_wc[0], home_first=True, db_path=db_path))  # Div2 winner vs WC1
        east_r1.append(best_of_7(east_div2[1], east_div2[2], home_first=True, db_path=db_path))  # Div2: 2nd vs 3rd

    results['round1'].extend(east_r1)

    west_r1 = []
    if len(west_div1) >= 3 and len(west_wc) >= 2:
        west_r1.append(best_of_7(west_div1[0], west_wc[1], home_first=True, db_path=db_path))
        west_r1.append(best_of_7(west_div1[1], west_div1[2], home_first=True, db_path=db_path))
        west_r1.append(best_of_7(west_div2[0], west_wc[0], home_first=True, db_path=db_path))
        west_r1.append(best_of_7(west_div2[1], west_div2[2], home_first=True, db_path=db_path))

    results['round1'].extend(west_r1)

    # ROUND 2 - Divisional semifinals (winners within each division bracket)
    # Div1 bracket winner vs Div1 bracket winner
    # Div2 bracket winner vs Div2 bracket winner
    east_r2 = []
    if len(east_r1) >= 4:
        # Sort within each division bracket by original standing
        east_div1_r2 = sorted(east_r1[:2], key=lambda t: final_standings[final_standings.team == t].index[0])
        east_div2_r2 = sorted(east_r1[2:], key=lambda t: final_standings[final_standings.team == t].index[0])

        east_r2.append(best_of_7(east_div1_r2[0], east_div1_r2[1], home_first=True, db_path=db_path))
        east_r2.append(best_of_7(east_div2_r2[0], east_div2_r2[1], home_first=True, db_path=db_path))

    results['round2'].extend(east_r2)

    west_r2 = []
    if len(west_r1) >= 4:
        west_div1_r2 = sorted(west_r1[:2], key=lambda t: final_standings[final_standings.team == t].index[0])
        west_div2_r2 = sorted(west_r1[2:], key=lambda t: final_standings[final_standings.team == t].index[0])

        west_r2.append(best_of_7(west_div1_r2[0], west_div1_r2[1], home_first=True, db_path=db_path))
        west_r2.append(best_of_7(west_div2_r2[0], west_div2_r2[1], home_first=True, db_path=db_path))

    results['round2'].extend(west_r2)

    # CONFERENCE FINALS - Division bracket winners play each other
    east_champ = None
    west_champ = None

    if len(east_r2) >= 2:
        east_cf = sorted(east_r2, key=lambda t: final_standings[final_standings.team == t].index[0])
        east_champ = best_of_7(east_cf[0], east_cf[1], home_first=True, db_path=db_path)
        results['conf_finals'].append(east_champ)
    elif len(east_r2) == 1:
        east_champ = east_r2[0]
        results['conf_finals'].append(east_champ)

    if len(west_r2) >= 2:
        west_cf = sorted(west_r2, key=lambda t: final_standings[final_standings.team == t].index[0])
        west_champ = best_of_7(west_cf[0], west_cf[1], home_first=True, db_path=db_path)
        results['conf_finals'].append(west_champ)
    elif len(west_r2) == 1:
        west_champ = west_r2[0]
        results['conf_finals'].append(west_champ)

    # STANLEY CUP FINAL
    if east_champ and west_champ:
        home_first = final_standings[final_standings.team == east_champ].index[0] < \
                     final_standings[final_standings.team == west_champ].index[0]
        cup_winner = best_of_7(east_champ, west_champ, home_first, db_path)
        results['cup_winner'] = cup_winner

    return results
