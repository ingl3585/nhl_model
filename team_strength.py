# team_strength.py
# Team strength calculations from player xGF/xGA data

import pandas as pd
import sqlite3
from config import FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING, ACTUAL_GOALS_WEIGHT, XG_WEIGHT


def get_team_strength(team, db_path, location):
    """
    Calculate team offensive and defensive strength from player data.

    Args:
        team (str): Team name
        db_path (str): Path to SQLite database with player stats
        location (str): "home" or "away"

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

    # Check if active_roster table exists
    # Active roster = skaters with >= ACTIVE_ROSTER_MIN_GP_PCT of last ACTIVE_ROSTER_WINDOW games
    # This correctly identifies currently-active players and resolves traded player team assignments
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='active_roster'")
    has_active_roster = cursor.fetchone() is not None

    # Position-weighted queries with xG and actual goals blending
    # Calculate separate averages for each position (both expected and actual)
    # Then blend: 70% xG + 30% actual goals
    # Offense: Forwards 85%, Defense 15%, Goalies 0%
    # Defense: Forwards 20%, Defense 30%, Goalies 50%

    # Build column names with location suffix
    toi_col = f"TOI_{location}"
    xgf_col = f"xGF/60_{location}"
    gf_col = f"GF/60_{location}"
    xga_col = f"xGA/60_{location}"
    ga_col = f"GA/60_{location}"
    xga_goalie_col = f"xG Against/60_{location}"
    gaa_col = f"GAA_{location}"

    if has_active_roster:
        from_clause = '''FROM players p
            INNER JOIN active_roster ar ON p.Player = ar.Player AND p.Team = ar.Team AND p.Position = ar.Position'''
        where_clause = "WHERE p.Team = ?"
        pos_prefix = "p."
    else:
        from_clause = "FROM players"
        where_clause = "WHERE Team = ?"
        pos_prefix = ""

    query = f'''
        SELECT
            -- Forward offense (xGF/60)
            COALESCE(SUM(CASE WHEN {pos_prefix}Position IN ('C', 'L', 'R') THEN {pos_prefix}"{xgf_col}" * {pos_prefix}"{toi_col}" END), 0) /
            NULLIF(SUM(CASE WHEN {pos_prefix}Position IN ('C', 'L', 'R') THEN {pos_prefix}"{toi_col}" END), 0) as forward_xgf,
            -- Forward offense (actual GF/60)
            COALESCE(SUM(CASE WHEN {pos_prefix}Position IN ('C', 'L', 'R') THEN {pos_prefix}"{gf_col}" * {pos_prefix}"{toi_col}" END), 0) /
            NULLIF(SUM(CASE WHEN {pos_prefix}Position IN ('C', 'L', 'R') THEN {pos_prefix}"{toi_col}" END), 0) as forward_gf,

            -- Defense offense (xGF/60)
            COALESCE(SUM(CASE WHEN {pos_prefix}Position = 'D' THEN {pos_prefix}"{xgf_col}" * {pos_prefix}"{toi_col}" END), 0) /
            NULLIF(SUM(CASE WHEN {pos_prefix}Position = 'D' THEN {pos_prefix}"{toi_col}" END), 0) as defense_xgf,
            -- Defense offense (actual GF/60)
            COALESCE(SUM(CASE WHEN {pos_prefix}Position = 'D' THEN {pos_prefix}"{gf_col}" * {pos_prefix}"{toi_col}" END), 0) /
            NULLIF(SUM(CASE WHEN {pos_prefix}Position = 'D' THEN {pos_prefix}"{toi_col}" END), 0) as defense_gf,

            -- Forward defense (xGA/60)
            COALESCE(SUM(CASE WHEN {pos_prefix}Position IN ('C', 'L', 'R') THEN {pos_prefix}"{xga_col}" * {pos_prefix}"{toi_col}" END), 0) /
            NULLIF(SUM(CASE WHEN {pos_prefix}Position IN ('C', 'L', 'R') THEN {pos_prefix}"{toi_col}" END), 0) as forward_xga,
            -- Forward defense (actual GA/60)
            COALESCE(SUM(CASE WHEN {pos_prefix}Position IN ('C', 'L', 'R') THEN {pos_prefix}"{ga_col}" * {pos_prefix}"{toi_col}" END), 0) /
            NULLIF(SUM(CASE WHEN {pos_prefix}Position IN ('C', 'L', 'R') THEN {pos_prefix}"{toi_col}" END), 0) as forward_ga,

            -- Defense defense (xGA/60)
            COALESCE(SUM(CASE WHEN {pos_prefix}Position = 'D' THEN {pos_prefix}"{xga_col}" * {pos_prefix}"{toi_col}" END), 0) /
            NULLIF(SUM(CASE WHEN {pos_prefix}Position = 'D' THEN {pos_prefix}"{toi_col}" END), 0) as defense_xga,
            -- Defense defense (actual GA/60)
            COALESCE(SUM(CASE WHEN {pos_prefix}Position = 'D' THEN {pos_prefix}"{ga_col}" * {pos_prefix}"{toi_col}" END), 0) /
            NULLIF(SUM(CASE WHEN {pos_prefix}Position = 'D' THEN {pos_prefix}"{toi_col}" END), 0) as defense_ga,

            -- Goalie defense (xG Against/60)
            COALESCE(SUM(CASE WHEN {pos_prefix}Position = 'G' THEN {pos_prefix}"{xga_goalie_col}" * {pos_prefix}"{toi_col}" END), 0) /
            NULLIF(SUM(CASE WHEN {pos_prefix}Position = 'G' THEN {pos_prefix}"{toi_col}" END), 0) as goalie_xga,
            -- Goalie defense (actual GAA)
            COALESCE(SUM(CASE WHEN {pos_prefix}Position = 'G' THEN {pos_prefix}"{gaa_col}" * {pos_prefix}"{toi_col}" END), 0) /
            NULLIF(SUM(CASE WHEN {pos_prefix}Position = 'G' THEN {pos_prefix}"{toi_col}" END), 0) as goalie_gaa
        {from_clause}
        {where_clause}
    '''

    try:
        df = pd.read_sql(query, conn, params=(team,))
        conn.close()
    except Exception as e:
        conn.close()
        print(f"   ⚠ Error querying team strength for {team} ({location}): {e}")
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
