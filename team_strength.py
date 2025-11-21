# team_strength.py
# Team strength calculations from player xGF/xGA data

import pandas as pd
import sqlite3
from config import MIN_TOI_MINUTES, FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING


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

    query = '''
        SELECT
            COALESCE(SUM("xGF"), 0) as total_xgf,
            COALESCE(SUM("TOI"), 0) as total_toi,
            COALESCE(SUM("xGA"), 0) as total_xga
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
    toi = row.total_toi

    # FINAL SAFETY NET — if TOI is 0 or None, fallback
    if not toi or toi <= 0:
        return FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING

    # Safe calculations
    off = row.total_xgf / (toi / 60.0)
    def_ = row.total_xga / (toi / 60.0)

    # Sanity clamp
    off = max(1.8, min(off, 4.8))
    def_ = max(1.8, min(def_, 4.8))

    return round(off, 3), round(def_, 3)
