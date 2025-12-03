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
                "Nashville Predators", "St. Louis Blues", "Utah Hockey Club", "Winnipeg Jets"],
    "Pacific": ["Anaheim Ducks", "Calgary Flames", "Edmonton Oilers", "Los Angeles Kings",
                "San Jose Sharks", "Seattle Kraken", "Vancouver Canucks", "Vegas Golden Knights"]
}


def best_of_7(team1, team2, home_first, db_path):
    """
    Simulate a best-of-7 playoff series.

    Args:
        team1 (str): First team (typically higher seed)
        team2 (str): Second team
        home_first (bool): Whether team1 has home ice advantage
        db_path (str): Path to player database

    Returns:
        str: Winning team name
    """
    wins1 = wins2 = 0
    home_turn = home_first

    while wins1 < 4 and wins2 < 4:
        winner = simulate_game(
            team1 if home_turn else team2,
            team2 if home_turn else team1,
            db_path
        )[0]

        if winner == team1:
            wins1 += 1
        else:
            wins2 += 1

        home_turn = not home_turn

    return team1 if wins1 == 4 else team2


def simulate_playoffs(playoff_teams, final_standings, db_path):
    """
    Simulate the full NHL playoff bracket (both conferences + Stanley Cup Final).

    Args:
        playoff_teams (list): List of 16 playoff team names
        final_standings (pd.DataFrame): Final season standings (for seeding)
        db_path (str): Path to player database

    Returns:
        dict: Dictionary with playoff results by round
            {
                'round1': [list of 8 teams that won round 1],
                'round2': [list of 4 teams that won round 2],
                'conf_finals': [list of 2 teams that won conference finals],
                'cup_winner': team name or None
            }
    """
    results = {
        'round1': [],
        'round2': [],
        'conf_finals': [],
        'cup_winner': None
    }
    
    # Split into conferences
    east = [t for t in playoff_teams if t in DIVISIONS["Atlantic"] + DIVISIONS["Metropolitan"]]
    west = [t for t in playoff_teams if t in DIVISIONS["Central"] + DIVISIONS["Pacific"]]

    # Sort by final standings position (higher seed = lower index)
    east.sort(key=lambda x: final_standings[final_standings.team == x].index[0])
    west.sort(key=lambda x: final_standings[final_standings.team == x].index[0])

    # ROUND 1 (8 teams -> 4 teams per conference)
    # NHL format: 1v8, 2v7, 3v6, 4v5
    if len(east) >= 8:
        east_r1 = [
            best_of_7(east[0], east[7], home_first=True, db_path=db_path),  # 1v8
            best_of_7(east[1], east[6], home_first=True, db_path=db_path),  # 2v7
            best_of_7(east[2], east[5], home_first=True, db_path=db_path),  # 3v6
            best_of_7(east[3], east[4], home_first=True, db_path=db_path),  # 4v5
        ]
        results['round1'].extend(east_r1)
        east = east_r1

    if len(west) >= 8:
        west_r1 = [
            best_of_7(west[0], west[7], home_first=True, db_path=db_path),  # 1v8
            best_of_7(west[1], west[6], home_first=True, db_path=db_path),  # 2v7
            best_of_7(west[2], west[5], home_first=True, db_path=db_path),  # 3v6
            best_of_7(west[3], west[4], home_first=True, db_path=db_path),  # 4v5
        ]
        results['round1'].extend(west_r1)
        west = west_r1

    # ROUND 2 (4 teams -> 2 teams per conference)
    if len(east) >= 2:
        east_r2 = [best_of_7(east[i], east[i+1], home_first=True, db_path=db_path)
                   for i in range(0, len(east), 2)]
        results['round2'].extend(east_r2)
        east = east_r2
    
    if len(west) >= 2:
        west_r2 = [best_of_7(west[i], west[i+1], home_first=True, db_path=db_path)
                   for i in range(0, len(west), 2)]
        results['round2'].extend(west_r2)
        west = west_r2

    # CONFERENCE FINALS (2 teams -> 1 team per conference)
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
