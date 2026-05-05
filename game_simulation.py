# game_simulation.py
# Single game simulation logic with improved statistical modeling

import sqlite3
import numpy as np
from tqdm import tqdm
from config import (
    LEAGUE_AVG_XG_PER_60, OT_HOME_WIN_PROB,
    N_SIMS_TODAY, TEAM_STRENGTH_VARIANCE
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


def simulate_overtime(home_xg, away_xg):
    """
    Simulate overtime with skill-adjusted probabilities.

    Args:
        home_xg (float): Home team's regulation expected goals
        away_xg (float): Away team's regulation expected goals

    Returns:
        tuple: (is_home_winner, win_type) where win_type is 'OT' or 'SO'
    """
    OT_ENDS_IN_GOAL_PROB = 0.67  # ~67% of OT ends before shootout
    HOME_SHOOTOUT_ADVANTAGE = 0.52  # Shootouts nearly 50/50
    SKILL_WEIGHT_OT = 0.30  # Reduced skill weight in OT (more random)

    # Calculate skill-based edge in OT
    total_xg = home_xg + away_xg
    if total_xg > 0:
        home_skill_edge = home_xg / total_xg
    else:
        home_skill_edge = 0.5

    # Blend skill with base home advantage, regressed toward 50%
    home_ot_prob = (home_skill_edge * SKILL_WEIGHT_OT) + (OT_HOME_WIN_PROB * (1 - SKILL_WEIGHT_OT))

    if np.random.rand() < OT_ENDS_IN_GOAL_PROB:
        return np.random.rand() < home_ot_prob, 'OT'
    else:
        return np.random.rand() < HOME_SHOOTOUT_ADVANTAGE, 'SO'


def simulate_game(home, away, db_path, use_cache=True):
    """
    Simulate a single NHL game using Poisson distribution.

    Args:
        home (str): Home team name
        away (str): Away team name
        db_path (str): Path to player database
        use_cache (bool): Whether to use cached team strengths

    Returns:
        tuple: (winner, home_pts, away_pts, home_goals, away_goals, win_type)
               win_type is 'REG', 'OT', or 'SO'
    """
    # Get team strengths with location (home team plays at home, away team plays away)
    if use_cache:
        ho, hd = get_cached_strength(home, db_path, location="home")
        ao, ad = get_cached_strength(away, db_path, location="away")
    else:
        ho, hd = get_team_strength(home, db_path, location="home")
        ao, ad = get_team_strength(away, db_path, location="away")

    # Per-team form variance: a "good night" should raise offense AND lower xGA (better defense).
    # Previous version multiplied both ho and hd by the same factor, which falsely made defense
    # *worse* on a team's good night (higher xGA = more goals allowed).
    if TEAM_STRENGTH_VARIANCE > 0:
        sigma = TEAM_STRENGTH_VARIANCE / 2
        home_form = np.clip(np.random.normal(1.0, sigma), 0.85, 1.15)
        away_form = np.clip(np.random.normal(1.0, sigma), 0.85, 1.15)

        ho *= home_form
        hd /= home_form
        ao *= away_form
        ad /= away_form

    # Calculate expected goals using location-specific team strength.
    # Home ice advantage is built into the home/away stats (no multiplier needed).
    # Divisor is calibrated empirically (see get_xg_divisor) so league-average teams
    # produce league-average xG; using LEAGUE_AVG_XG_PER_60 directly inflates totals.
    divisor = get_xg_divisor(db_path)
    home_xg = ho * ad / divisor
    away_xg = ao * hd / divisor

    home_xg = max(0.5, min(home_xg, 6.0))
    away_xg = max(0.5, min(away_xg, 6.0))

    # Simulate goals
    hg = np.random.poisson(home_xg)
    ag = np.random.poisson(away_xg)

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
