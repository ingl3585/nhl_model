# game_simulation.py
# Single game simulation logic

import numpy as np
from config import HOME_ICE_ADVANTAGE, LEAGUE_AVG_XG_PER_60, OT_HOME_WIN_PROB, N_SIMS_TODAY
from team_strength import get_team_strength


def simulate_game(home, away, db_path):
    """
    Simulate a single NHL game using Poisson distribution.

    Args:
        home (str): Home team name
        away (str): Away team name
        db_path (str): Path to player database

    Returns:
        tuple: (winner, home_pts, away_pts, home_goals, away_goals, regulation_win)
    """
    ho, hd = get_team_strength(home, db_path)
    ao, ad = get_team_strength(away, db_path)

    home_xg = ho * HOME_ICE_ADVANTAGE * (LEAGUE_AVG_XG_PER_60 / ad)
    away_xg = ao * (LEAGUE_AVG_XG_PER_60 / hd)

    hg = np.random.poisson(home_xg)
    ag = np.random.poisson(away_xg)

    if hg > ag:
        return home, 2, 0, hg, ag, True
    elif ag > hg:
        return away, 0, 2, hg, ag, True
    else:
        # Overtime/Shootout
        winner = home if np.random.rand() < OT_HOME_WIN_PROB else away
        return winner, 2, 1, hg + (winner == home), ag + (winner == away), False


def predict_todays_games(today_games, db_path):
    """
    Run predictions for today's games.

    Args:
        today_games (pd.DataFrame): DataFrame of today's games
        db_path (str): Path to player database

    Returns:
        list: List of prediction dictionaries with game details
    """
    predictions = []

    for _, game in today_games.iterrows():
        home, away = game["home"], game["visitor"]

        home_wins = home_goals = away_goals = 0

        for _ in range(N_SIMS_TODAY):
            winner, hpts, apts, hgf, agf, reg = simulate_game(home, away, db_path)
            home_goals += hgf
            away_goals += agf
            if winner == home:
                home_wins += 1

        home_pct = home_wins / N_SIMS_TODAY
        away_pct = 1 - home_pct

        fav = "HOME" if home_pct > 0.62 else "AWAY" if away_pct > 0.62 else "TOSS-UP"
        total = round((home_goals + away_goals) / N_SIMS_TODAY, 2)

        predictions.append({
            "home": home,
            "away": away,
            "home_pct": home_pct,
            "away_pct": away_pct,
            "home_avg_goals": home_goals / N_SIMS_TODAY,
            "away_avg_goals": away_goals / N_SIMS_TODAY,
            "favorite": fav,
            "expected_total": total
        })

    return predictions
