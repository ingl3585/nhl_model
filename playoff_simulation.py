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
    Simulate the full NHL playoff bracket using divisional format.

    NHL Playoff Format (2013-present):
    - Each conference seeds 8 teams
    - Division winners get seeds 1-2 (by points)
    - Remaining division spots (2nd, 3rd) fill seeds 3-6
    - Two wildcards get seeds 7-8
    - Round 1: Division matchups (1v4, 2v3 in each division) + wildcard crossovers
    - Rounds 2+: Re-seed by points within conference

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

    def seed_conference(conf_divisions):
        """Seed one conference using divisional format."""
        conf_teams = [t for div in conf_divisions for t in DIVISIONS[div]]
        conf_playoff = [t for t in playoff_teams if t in conf_teams]

        # Get division standings
        seeds = []
        for div in conf_divisions:
            div_teams = [t for t in conf_playoff if t in DIVISIONS[div]]
            div_standings = final_standings[final_standings.team.isin(div_teams)].copy()
            div_standings = div_standings.sort_values(by=["points", "row", "gf-ga", "gf"], ascending=False)
            seeds.extend(div_standings.team.tolist())

        # Sort all 8 teams by points for matchups
        conf_standings = final_standings[final_standings.team.isin(conf_playoff)].copy()
        conf_standings = conf_standings.sort_values(by=["points", "row", "gf-ga", "gf"], ascending=False)
        return conf_standings.team.tolist()

    # Seed each conference
    east = seed_conference(["Atlantic", "Metropolitan"])
    west = seed_conference(["Central", "Pacific"])

    # ROUND 1 - Divisional format: 1v4, 2v3, then wildcard crossovers
    # Higher seed always gets home ice
    if len(east) >= 8:
        east_r1 = [
            best_of_7(east[0], east[3], home_first=True, db_path=db_path),  # 1v4
            best_of_7(east[1], east[2], home_first=True, db_path=db_path),  # 2v3
            best_of_7(east[4], east[7], home_first=True, db_path=db_path),  # 5v8
            best_of_7(east[5], east[6], home_first=True, db_path=db_path),  # 6v7
        ]
        results['round1'].extend(east_r1)

        # Re-seed by standings for Round 2
        east_r1_sorted = sorted(east_r1, key=lambda t: final_standings[final_standings.team == t].index[0])
        east = east_r1_sorted

    if len(west) >= 8:
        west_r1 = [
            best_of_7(west[0], west[3], home_first=True, db_path=db_path),  # 1v4
            best_of_7(west[1], west[2], home_first=True, db_path=db_path),  # 2v3
            best_of_7(west[4], west[7], home_first=True, db_path=db_path),  # 5v8
            best_of_7(west[5], west[6], home_first=True, db_path=db_path),  # 6v7
        ]
        results['round1'].extend(west_r1)

        # Re-seed by standings for Round 2
        west_r1_sorted = sorted(west_r1, key=lambda t: final_standings[final_standings.team == t].index[0])
        west = west_r1_sorted

    # ROUND 2 - Re-seeded: 1v4, 2v3
    if len(east) >= 4:
        east_r2 = [
            best_of_7(east[0], east[3], home_first=True, db_path=db_path),  # Highest vs 4th
            best_of_7(east[1], east[2], home_first=True, db_path=db_path),  # 2nd vs 3rd
        ]
        results['round2'].extend(east_r2)
        east = sorted(east_r2, key=lambda t: final_standings[final_standings.team == t].index[0])

    if len(west) >= 4:
        west_r2 = [
            best_of_7(west[0], west[3], home_first=True, db_path=db_path),
            best_of_7(west[1], west[2], home_first=True, db_path=db_path),
        ]
        results['round2'].extend(west_r2)
        west = sorted(west_r2, key=lambda t: final_standings[final_standings.team == t].index[0])

    # CONFERENCE FINALS
    east_champ = None
    west_champ = None

    if len(east) >= 2:
        east_champ = best_of_7(east[0], east[1], home_first=True, db_path=db_path)
        results['conf_finals'].append(east_champ)
    elif len(east) == 1:
        east_champ = east[0]
        results['conf_finals'].append(east_champ)

    if len(west) >= 2:
        west_champ = best_of_7(west[0], west[1], home_first=True, db_path=db_path)
        results['conf_finals'].append(west_champ)
    elif len(west) == 1:
        west_champ = west[0]
        results['conf_finals'].append(west_champ)

    # STANLEY CUP FINAL
    if east_champ and west_champ:
        home_first = final_standings[final_standings.team == east_champ].index[0] < \
                     final_standings[final_standings.team == west_champ].index[0]
        cup_winner = best_of_7(east_champ, west_champ, home_first, db_path)
        results['cup_winner'] = cup_winner

    return results
