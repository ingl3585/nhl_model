# team_strength.py
# Team strength calculations from player xGF/xGA data

import pandas as pd
import sqlite3
from config import MIN_TOI_MINUTES, FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING, ACTUAL_GOALS_WEIGHT, XG_WEIGHT


def get_team_strength(team, db_path):
    """
    Calculate team offensive and defensive strength from player data.

    Args:
        team (str): Team name
        db_path (str): Path to SQLite database with player stats

    Returns:
        tuple: (offensive_rating, defensive_rating) as xGF/60 and xGA/60
    """
    # Early exit if DB doesn't exist
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players'")
        if not cursor.fetchone():
            conn.close()
            return FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING
    except:
        return FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING

    # Position-weighted queries with xG and actual goals blending
    # Calculate separate averages for each position (both expected and actual)
    # Then blend: 70% xG + 30% actual goals
    # Offense: Forwards 85%, Defense 15%, Goalies 0%
    # Defense: Forwards 20%, Defense 30%, Goalies 50%

    query = '''
        SELECT
            -- Forward offense (xGF/60)
            COALESCE(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "xGF/60" * "TOI" END), 0) /
            NULLIF(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "TOI" END), 0) as forward_xgf,
            -- Forward offense (actual GF/60)
            COALESCE(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "GF/60" * "TOI" END), 0) /
            NULLIF(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "TOI" END), 0) as forward_gf,

            -- Defense offense (xGF/60)
            COALESCE(SUM(CASE WHEN Position = 'D' THEN "xGF/60" * "TOI" END), 0) /
            NULLIF(SUM(CASE WHEN Position = 'D' THEN "TOI" END), 0) as defense_xgf,
            -- Defense offense (actual GF/60)
            COALESCE(SUM(CASE WHEN Position = 'D' THEN "GF/60" * "TOI" END), 0) /
            NULLIF(SUM(CASE WHEN Position = 'D' THEN "TOI" END), 0) as defense_gf,

            -- Forward defense (xGA/60)
            COALESCE(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "xGA/60" * "TOI" END), 0) /
            NULLIF(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "TOI" END), 0) as forward_xga,
            -- Forward defense (actual GA/60)
            COALESCE(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "GA/60" * "TOI" END), 0) /
            NULLIF(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "TOI" END), 0) as forward_ga,

            -- Defense defense (xGA/60)
            COALESCE(SUM(CASE WHEN Position = 'D' THEN "xGA/60" * "TOI" END), 0) /
            NULLIF(SUM(CASE WHEN Position = 'D' THEN "TOI" END), 0) as defense_xga,
            -- Defense defense (actual GA/60)
            COALESCE(SUM(CASE WHEN Position = 'D' THEN "GA/60" * "TOI" END), 0) /
            NULLIF(SUM(CASE WHEN Position = 'D' THEN "TOI" END), 0) as defense_ga,

            -- Goalie defense (xG Against/60)
            COALESCE(SUM(CASE WHEN Position = 'G' THEN "xG Against/60" * "TOI" END), 0) /
            NULLIF(SUM(CASE WHEN Position = 'G' THEN "TOI" END), 0) as goalie_xga,
            -- Goalie defense (actual GAA)
            COALESCE(SUM(CASE WHEN Position = 'G' THEN "GAA" * "TOI" END), 0) /
            NULLIF(SUM(CASE WHEN Position = 'G' THEN "TOI" END), 0) as goalie_gaa
        FROM players
        WHERE Team = ? AND "TOI" > ?
    '''

    try:
        df = pd.read_sql(query, conn, params=(team, MIN_TOI_MINUTES))
        conn.close()
    except:
        conn.close()
        return FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING

    if df.empty:
        return FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING

    row = df.iloc[0]

    # Get position-specific averages (handle NaN/None) for both xG and actual
    forward_xgf = row.forward_xgf if pd.notna(row.forward_xgf) else 0
    forward_gf = row.forward_gf if pd.notna(row.forward_gf) else 0
    defense_xgf = row.defense_xgf if pd.notna(row.defense_xgf) else 0
    defense_gf = row.defense_gf if pd.notna(row.defense_gf) else 0
    forward_xga = row.forward_xga if pd.notna(row.forward_xga) else 0
    forward_ga = row.forward_ga if pd.notna(row.forward_ga) else 0
    defense_xga = row.defense_xga if pd.notna(row.defense_xga) else 0
    defense_ga = row.defense_ga if pd.notna(row.defense_ga) else 0
    goalie_xga = row.goalie_xga if pd.notna(row.goalie_xga) else 0
    goalie_gaa = row.goalie_gaa if pd.notna(row.goalie_gaa) else 0

    # Blend expected and actual goals for each position
    forward_off = (forward_xgf * XG_WEIGHT) + (forward_gf * ACTUAL_GOALS_WEIGHT)
    defense_off = (defense_xgf * XG_WEIGHT) + (defense_gf * ACTUAL_GOALS_WEIGHT)
    forward_def = (forward_xga * XG_WEIGHT) + (forward_ga * ACTUAL_GOALS_WEIGHT)
    defense_def = (defense_xga * XG_WEIGHT) + (defense_ga * ACTUAL_GOALS_WEIGHT)
    goalie_def = (goalie_xga * XG_WEIGHT) + (goalie_gaa * ACTUAL_GOALS_WEIGHT)

    # Apply position weights to calculate team ratings
    # Offense: 85% forwards, 15% defense
    off = (forward_off * 0.85) + (defense_off * 0.15)

    # Defense: 20% forwards, 30% defense, 50% goalies
    def_ = (forward_def * 0.20) + (defense_def * 0.30) + (goalie_def * 0.50)

    # Sanity check - if values are unrealistic, use fallback
    if off == 0 or def_ == 0:
        return FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING

    # Sanity clamp
    off = max(1.8, min(off, 4.8))
    def_ = max(1.8, min(def_, 4.8))

    return round(off, 3), round(def_, 3)
