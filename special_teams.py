# special_teams.py
# Team-level power play / penalty kill matchup modifiers.

import sqlite3

import numpy as np
import pandas as pd

from config import (
    ACTUAL_GOALS_WEIGHT,
    ENABLE_SPECIAL_TEAMS_ADJUSTMENTS,
    SPECIAL_TEAMS_MATCHUP_WEIGHT,
    SPECIAL_TEAMS_MAX_XG_ADJUSTMENT,
    XG_WEIGHT,
)


_special_teams_cache = {}
_league_cache = {}


def clear_special_teams_cache():
    _special_teams_cache.clear()
    _league_cache.clear()


def _empty_profile(team):
    return {
        "Team": team,
        "pp_attack": np.nan,
        "pk_allowed": np.nan,
    }


def _load_special_teams_table(db_path):
    if db_path in _special_teams_cache:
        return _special_teams_cache[db_path]

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='team_special_teams'")
        if not cursor.fetchone():
            conn.close()
            _special_teams_cache[db_path] = pd.DataFrame()
            return _special_teams_cache[db_path]
        df = pd.read_sql("SELECT * FROM team_special_teams", conn)
        conn.close()
    except Exception:
        df = pd.DataFrame()

    if not df.empty:
        for col in ("PP_xGF/60", "PP_GF/60", "PK_xGA/60", "PK_GA/60"):
            if col not in df.columns:
                df[col] = np.nan
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["pp_attack"] = (df["PP_xGF/60"] * XG_WEIGHT) + (df["PP_GF/60"] * ACTUAL_GOALS_WEIGHT)
        df["pk_allowed"] = (df["PK_xGA/60"] * XG_WEIGHT) + (df["PK_GA/60"] * ACTUAL_GOALS_WEIGHT)

    _special_teams_cache[db_path] = df
    return df


def get_special_teams_profile(team, db_path):
    df = _load_special_teams_table(db_path)
    if df.empty or "Team" not in df.columns:
        return _empty_profile(team)

    match = df[df["Team"] == team]
    if match.empty:
        return _empty_profile(team)

    row = match.iloc[0]
    return {
        "Team": team,
        "pp_attack": row.get("pp_attack", np.nan),
        "pk_allowed": row.get("pk_allowed", np.nan),
    }


def _league_baseline(db_path):
    if db_path in _league_cache:
        return _league_cache[db_path]

    df = _load_special_teams_table(db_path)
    if df.empty or "pp_attack" not in df.columns or "pk_allowed" not in df.columns:
        baseline = None
    else:
        pp_mean = pd.to_numeric(df["pp_attack"], errors="coerce").replace(0, np.nan).mean()
        pk_mean = pd.to_numeric(df["pk_allowed"], errors="coerce").replace(0, np.nan).mean()
        baseline = (float(pp_mean), float(pk_mean)) if pd.notna(pp_mean) and pd.notna(pk_mean) else None

    _league_cache[db_path] = baseline
    return baseline


def _edge_to_multiplier(edge):
    raw = 1.0 + (edge * SPECIAL_TEAMS_MATCHUP_WEIGHT)
    low = 1.0 - SPECIAL_TEAMS_MAX_XG_ADJUSTMENT
    high = 1.0 + SPECIAL_TEAMS_MAX_XG_ADJUSTMENT
    return float(np.clip(raw, low, high))


def calculate_special_teams_multipliers(home, away, db_path):
    """
    Return xG multipliers from PP/PK matchup quality.

    This is intentionally a small overlay. The current player baseline uses
    NST all-situations data, so this layer should reshape matchup context
    without double-counting special teams as full additive goals.
    """
    if not ENABLE_SPECIAL_TEAMS_ADJUSTMENTS:
        return 1.0, 1.0

    baseline = _league_baseline(db_path)
    if baseline is None:
        return 1.0, 1.0

    league_pp, league_pk_allowed = baseline
    if league_pp <= 0 or league_pk_allowed <= 0:
        return 1.0, 1.0

    home_st = get_special_teams_profile(home, db_path)
    away_st = get_special_teams_profile(away, db_path)

    if any(pd.isna(v) for v in (
        home_st["pp_attack"], home_st["pk_allowed"],
        away_st["pp_attack"], away_st["pk_allowed"],
    )):
        return 1.0, 1.0

    home_edge = ((home_st["pp_attack"] / league_pp) + (away_st["pk_allowed"] / league_pk_allowed)) / 2 - 1
    away_edge = ((away_st["pp_attack"] / league_pp) + (home_st["pk_allowed"] / league_pk_allowed)) / 2 - 1

    return _edge_to_multiplier(home_edge), _edge_to_multiplier(away_edge)
