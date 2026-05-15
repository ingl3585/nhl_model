# game_simulation.py
# Single game simulation logic with improved statistical modeling

import sqlite3
import numpy as np
from tqdm import tqdm
from config import (
    LEAGUE_AVG_XG_PER_60, OT_HOME_WIN_PROB,
    N_SIMS_TODAY, TEAM_STRENGTH_VARIANCE, GAME_PACE_VARIANCE,
    SCORING_CORRELATION, MIN_GAME_XG, MAX_GAME_XG,
    OT_ENDS_IN_GOAL_PROB, OT_SKILL_WEIGHT, SHOOTOUT_HOME_WIN_PROB
)
from team_strength import get_team_strength

# Module-level caches (cleared between runs)
_strength_cache = {}
_calibration_cache = {}


def clear_strength_cache():
    """Clear the team strength and calibration caches. Call this when data updates."""
    global _strength_cache, _calibration_cache
    _strength_cache = {}
    _calibration_cache = {}


def get_cached_strength(team, db_path, location):
    """Get team strength with caching to avoid repeated DB queries."""
    cache_key = (team, db_path, location)
    if cache_key not in _strength_cache:
        _strength_cache[cache_key] = get_team_strength(team, db_path, location)
    return _strength_cache[cache_key]


def get_xg_divisor(db_path):
    """
    Empirical divisor for the xG formula: home_xg = ho * ad / divisor.

    team_strength returns TOI-weighted position averages, which run hotter than
    the true league xGF/60 (top-line forwards dominate the weighting). Using the
    raw LEAGUE_AVG_XG_PER_60 as the divisor inflates predicted totals.

    This computes the divisor that makes E[home_xg] = LEAGUE_AVG_XG_PER_60 when
    teams are league-average, by averaging actual team_strength outputs.
    """
    if db_path in _calibration_cache:
        return _calibration_cache[db_path]

    conn = sqlite3.connect(db_path)
    teams = [r[0] for r in conn.execute(
        "SELECT DISTINCT Team FROM players WHERE Team IS NOT NULL AND Team != ''"
    ).fetchall()]
    conn.close()

    offs, defs = [], []
    for t in teams:
        for loc in ("home", "away"):
            o, d = get_cached_strength(t, db_path, loc)
            offs.append(o)
            defs.append(d)

    divisor = (float(np.mean(offs)) * float(np.mean(defs))) / LEAGUE_AVG_XG_PER_60
    _calibration_cache[db_path] = divisor
    return divisor


def _mean_one_lognormal(variance):
    """Sample a positive multiplier with mean near 1.0."""
    if variance <= 0:
        return 1.0
    sigma = variance / 2
    return float(np.random.lognormal(mean=-(sigma ** 2) / 2, sigma=sigma))


def calculate_expected_goals(home, away, db_path, use_cache=True, apply_variance=True):
    """
    Calculate regulation expected goals for a matchup.

    This is separated from simulate_game() so matchup strength can be inspected
    directly and the stochastic scoring layer can evolve independently.
    """
    if use_cache:
        ho, hd = get_cached_strength(home, db_path, location="home")
        ao, ad = get_cached_strength(away, db_path, location="away")
    else:
        ho, hd = get_team_strength(home, db_path, location="home")
        ao, ad = get_team_strength(away, db_path, location="away")

    # A good team night should improve offense and suppress xGA. Lognormal
    # multipliers avoid invalid negative tails while preserving the average.
    if apply_variance and TEAM_STRENGTH_VARIANCE > 0:
        home_form = np.clip(_mean_one_lognormal(TEAM_STRENGTH_VARIANCE), 0.85, 1.15)
        away_form = np.clip(_mean_one_lognormal(TEAM_STRENGTH_VARIANCE), 0.85, 1.15)

        ho *= home_form
        hd /= home_form
        ao *= away_form
        ad /= away_form

    divisor = get_xg_divisor(db_path)
    home_xg = ho * ad / divisor
    away_xg = ao * hd / divisor

    # Hockey games have shared tempo: officiating, score effects, goalie pulls,
    # and matchup pace tend to move both teams' scoring environments together.
    if apply_variance and GAME_PACE_VARIANCE > 0:
        pace = np.clip(_mean_one_lognormal(GAME_PACE_VARIANCE), 0.85, 1.15)
        home_xg *= pace
        away_xg *= pace

    home_xg = max(MIN_GAME_XG, min(home_xg, MAX_GAME_XG))
    away_xg = max(MIN_GAME_XG, min(away_xg, MAX_GAME_XG))

    return home_xg, away_xg


def simulate_regulation_score(home_xg, away_xg):
    """
    Simulate regulation scoring with a small shared Poisson component.

    Independent Poisson goals understate tied games in hockey. A shared scoring
    component preserves each team's xG while letting game environment influence
    both scores in the same direction.
    """
    shared_xg = min(home_xg, away_xg) * max(0, min(SCORING_CORRELATION, 0.5))
    shared_goals = np.random.poisson(shared_xg) if shared_xg > 0 else 0
    home_goals = shared_goals + np.random.poisson(max(home_xg - shared_xg, 0))
    away_goals = shared_goals + np.random.poisson(max(away_xg - shared_xg, 0))
    return int(home_goals), int(away_goals)


def simulate_overtime(home_xg, away_xg):
    """
    Simulate overtime with skill-adjusted probabilities.

    Args:
        home_xg (float): Home team's regulation expected goals
        away_xg (float): Away team's regulation expected goals

    Returns:
        tuple: (is_home_winner, win_type) where win_type is 'OT' or 'SO'
    """
    # Calculate skill-based edge in OT
    total_xg = home_xg + away_xg
    if total_xg > 0:
        home_skill_edge = home_xg / total_xg
    else:
        home_skill_edge = 0.5

    # Blend skill with base home advantage, regressed toward 50%
    home_ot_prob = (home_skill_edge * OT_SKILL_WEIGHT) + (OT_HOME_WIN_PROB * (1 - OT_SKILL_WEIGHT))

    if np.random.rand() < OT_ENDS_IN_GOAL_PROB:
        return np.random.rand() < home_ot_prob, 'OT'
    else:
        return np.random.rand() < SHOOTOUT_HOME_WIN_PROB, 'SO'


def simulate_game(home, away, db_path, use_cache=True):
    """
    Simulate a single NHL game using correlated Poisson scoring.

    Args:
        home (str): Home team name
        away (str): Away team name
        db_path (str): Path to player database
        use_cache (bool): Whether to use cached team strengths

    Returns:
        tuple: (winner, home_pts, away_pts, home_goals, away_goals, win_type)
               win_type is 'REG', 'OT', or 'SO'
    """
    home_xg, away_xg = calculate_expected_goals(home, away, db_path, use_cache=use_cache)
    hg, ag = simulate_regulation_score(home_xg, away_xg)

    if hg > ag:
        return home, 2, 0, hg, ag, 'REG'
    elif ag > hg:
        return away, 0, 2, hg, ag, 'REG'
    else:
        # Overtime/Shootout
        home_wins_ot, win_type = simulate_overtime(home_xg, away_xg)
        if home_wins_ot:
            return home, 2, 1, hg + 1, ag, win_type
        else:
            return away, 1, 2, hg, ag + 1, win_type


def predict_todays_games(today_games, db_path, confidence_threshold=0.60):
    """
    Run predictions for today's games.

    Args:
        today_games (pd.DataFrame): DataFrame of today's games
        db_path (str): Path to player database
        confidence_threshold (float): Win probability needed to declare favorite

    Returns:
        list: List of prediction dictionaries with game details
    """
    predictions = []

    # Pre-cache team strengths for efficiency (both home and away for each team)
    clear_strength_cache()
    all_teams = set(today_games["home"].tolist() + today_games["visitor"].tolist())
    for team in all_teams:
        get_cached_strength(team, db_path, location="home")
        get_cached_strength(team, db_path, location="away")

    for _, game in today_games.iterrows():
        home, away = game["home"], game["visitor"]

        home_wins = home_goals = away_goals = 0
        ot_games = 0

        for _ in tqdm(range(N_SIMS_TODAY), desc=f"{away} @ {home}", leave=False, unit="sim"):
            winner, hpts, apts, hgf, agf, win_type = simulate_game(home, away, db_path)
            home_goals += hgf
            away_goals += agf
            if winner == home:
                home_wins += 1
            if win_type != 'REG':
                ot_games += 1

        home_pct = home_wins / N_SIMS_TODAY
        away_pct = 1 - home_pct
        ot_pct = ot_games / N_SIMS_TODAY

        # Determine favorite with configurable threshold
        if home_pct > confidence_threshold:
            fav = "HOME"
        elif away_pct > confidence_threshold:
            fav = "AWAY"
        else:
            fav = "TOSS-UP"

        total = round((home_goals + away_goals) / N_SIMS_TODAY, 2)

        # Monte Carlo standard error for win probability
        std_error = np.sqrt(home_pct * (1 - home_pct) / N_SIMS_TODAY)

        predictions.append({
            "home": home,
            "away": away,
            "home_pct": round(home_pct, 3),
            "away_pct": round(away_pct, 3),
            "home_avg_goals": round(home_goals / N_SIMS_TODAY, 2),
            "away_avg_goals": round(away_goals / N_SIMS_TODAY, 2),
            "favorite": fav,
            "expected_total": total,
            "ot_probability": round(ot_pct, 3),
            "margin_of_error": round(1.96 * std_error, 3)  # 95% CI
        })

    return predictions
