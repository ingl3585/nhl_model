# team_strength.py
# Team strength calculations from player xGF/xGA data

import pandas as pd
import sqlite3
from config import MIN_TOI_MINUTES, FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING, ACTUAL_GOALS_WEIGHT, XG_WEIGHT


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

    # Check if active_roster table exists (players from last game bypass MIN_TOI)
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
        # Include players from last game (no TOI filter needed)
        # Join on (Player, Team, Position) instead of Player_ID since Player_ID is just
        # NST's row number and differs between datasets
        query = f'''
            SELECT
                -- Forward offense (xGF/60)
                COALESCE(SUM(CASE WHEN p.Position IN ('C', 'L', 'R') THEN p."{xgf_col}" * p."{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN p.Position IN ('C', 'L', 'R') THEN p."{toi_col}" END), 0) as forward_xgf,
                -- Forward offense (actual GF/60)
                COALESCE(SUM(CASE WHEN p.Position IN ('C', 'L', 'R') THEN p."{gf_col}" * p."{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN p.Position IN ('C', 'L', 'R') THEN p."{toi_col}" END), 0) as forward_gf,

                -- Defense offense (xGF/60)
                COALESCE(SUM(CASE WHEN p.Position = 'D' THEN p."{xgf_col}" * p."{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN p.Position = 'D' THEN p."{toi_col}" END), 0) as defense_xgf,
                -- Defense offense (actual GF/60)
                COALESCE(SUM(CASE WHEN p.Position = 'D' THEN p."{gf_col}" * p."{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN p.Position = 'D' THEN p."{toi_col}" END), 0) as defense_gf,

                -- Forward defense (xGA/60)
                COALESCE(SUM(CASE WHEN p.Position IN ('C', 'L', 'R') THEN p."{xga_col}" * p."{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN p.Position IN ('C', 'L', 'R') THEN p."{toi_col}" END), 0) as forward_xga,
                -- Forward defense (actual GA/60)
                COALESCE(SUM(CASE WHEN p.Position IN ('C', 'L', 'R') THEN p."{ga_col}" * p."{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN p.Position IN ('C', 'L', 'R') THEN p."{toi_col}" END), 0) as forward_ga,

                -- Defense defense (xGA/60)
                COALESCE(SUM(CASE WHEN p.Position = 'D' THEN p."{xga_col}" * p."{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN p.Position = 'D' THEN p."{toi_col}" END), 0) as defense_xga,
                -- Defense defense (actual GA/60)
                COALESCE(SUM(CASE WHEN p.Position = 'D' THEN p."{ga_col}" * p."{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN p.Position = 'D' THEN p."{toi_col}" END), 0) as defense_ga,

                -- Goalie defense (xG Against/60)
                COALESCE(SUM(CASE WHEN p.Position = 'G' THEN p."{xga_goalie_col}" * p."{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN p.Position = 'G' THEN p."{toi_col}" END), 0) as goalie_xga,
                -- Goalie defense (actual GAA)
                COALESCE(SUM(CASE WHEN p.Position = 'G' THEN p."{gaa_col}" * p."{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN p.Position = 'G' THEN p."{toi_col}" END), 0) as goalie_gaa
            FROM players p
            INNER JOIN active_roster ar ON p.Player = ar.Player AND p.Team = ar.Team AND p.Position = ar.Position
            WHERE p.Team = ?
        '''
    else:
        # Fallback: no active roster table, can't filter reliably
        query = f'''
            SELECT
                -- Forward offense (xGF/60)
                COALESCE(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "{xgf_col}" * "{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "{toi_col}" END), 0) as forward_xgf,
                -- Forward offense (actual GF/60)
                COALESCE(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "{gf_col}" * "{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "{toi_col}" END), 0) as forward_gf,

                -- Defense offense (xGF/60)
                COALESCE(SUM(CASE WHEN Position = 'D' THEN "{xgf_col}" * "{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN Position = 'D' THEN "{toi_col}" END), 0) as defense_xgf,
                -- Defense offense (actual GF/60)
                COALESCE(SUM(CASE WHEN Position = 'D' THEN "{gf_col}" * "{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN Position = 'D' THEN "{toi_col}" END), 0) as defense_gf,

                -- Forward defense (xGA/60)
                COALESCE(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "{xga_col}" * "{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "{toi_col}" END), 0) as forward_xga,
                -- Forward defense (actual GA/60)
                COALESCE(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "{ga_col}" * "{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN Position IN ('C', 'L', 'R') THEN "{toi_col}" END), 0) as forward_ga,

                -- Defense defense (xGA/60)
                COALESCE(SUM(CASE WHEN Position = 'D' THEN "{xga_col}" * "{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN Position = 'D' THEN "{toi_col}" END), 0) as defense_xga,
                -- Defense defense (actual GA/60)
                COALESCE(SUM(CASE WHEN Position = 'D' THEN "{ga_col}" * "{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN Position = 'D' THEN "{toi_col}" END), 0) as defense_ga,

                -- Goalie defense (xG Against/60)
                COALESCE(SUM(CASE WHEN Position = 'G' THEN "{xga_goalie_col}" * "{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN Position = 'G' THEN "{toi_col}" END), 0) as goalie_xga,
                -- Goalie defense (actual GAA)
                COALESCE(SUM(CASE WHEN Position = 'G' THEN "{gaa_col}" * "{toi_col}" END), 0) /
                NULLIF(SUM(CASE WHEN Position = 'G' THEN "{toi_col}" END), 0) as goalie_gaa
            FROM players
            WHERE Team = ?
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
