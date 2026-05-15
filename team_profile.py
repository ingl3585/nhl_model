# team_profile.py
# Derived team profile traits from the existing NST player database.

import sqlite3

import numpy as np
import pandas as pd

from config import (
    ACTUAL_GOALS_WEIGHT, DEPTH_STABILITY_WEIGHT, ELITE_DEFENSE_PREMIUM_WEIGHT,
    LEAGUE_AVG_XG_PER_60, MIN_GP_PERCENTAGE, TEAM_PROFILE_MAX_XG_ADJUSTMENT,
    TOP_SKATER_PREMIUM_WEIGHT, XG_WEIGHT
)
from team_strength import get_team_strength

_profile_cache = {}


def clear_profile_cache():
    """Clear cached team profile calculations."""
    global _profile_cache
    _profile_cache = {}


def _position_tokens(position):
    if pd.isna(position):
        return set()
    return {p.strip().upper() for p in str(position).replace("/", ",").split(",") if p.strip()}


def _positions_overlap(left, right):
    return bool(_position_tokens(left) & _position_tokens(right))


def _is_forward(position):
    return bool(_position_tokens(position) & {"C", "L", "R"})


def _is_defense(position):
    return "D" in _position_tokens(position)


def _is_goalie(position):
    return "G" in _position_tokens(position)


def _load_team_players(team, db_path):
    conn = sqlite3.connect(db_path)
    players = pd.read_sql("SELECT * FROM players WHERE Team = ?", conn, params=(team,))
    tables = pd.read_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='active_roster'",
        conn
    )
    active = pd.read_sql(
        "SELECT Player, Team, Position FROM active_roster WHERE Team = ?",
        conn,
        params=(team,)
    ) if not tables.empty else pd.DataFrame()
    conn.close()
    return players, active


def _eligible_players(players, active):
    if players.empty:
        return players
    if active.empty:
        return players

    skater_mask = players["Position"].apply(lambda p: _is_forward(p) or _is_defense(p))
    team_max_gp = players.loc[skater_mask, "GP"].max() if "GP" in players.columns else np.nan
    established_min_gp = team_max_gp * MIN_GP_PERCENTAGE if pd.notna(team_max_gp) else np.inf

    def keep(row):
        active_candidates = active[active["Player"] == row["Player"]]
        active_match = any(
            _positions_overlap(row["Position"], pos)
            for pos in active_candidates["Position"]
        )
        established_skater = (
            not _is_goalie(row["Position"])
            and pd.notna(row.get("GP"))
            and row["GP"] >= established_min_gp
        )
        return active_match or established_skater

    return players[players.apply(keep, axis=1)].copy()


def _weighted_average(df, value_col, weight_col):
    valid = df[[value_col, weight_col]].dropna()
    valid = valid[valid[weight_col] > 0]
    if valid.empty:
        return 0.0
    return float(np.average(valid[value_col], weights=valid[weight_col]))


def get_team_profile(team, db_path, location):
    """
    Return transparent profile traits and a capped xG modifier.

    The modifier is intentionally small. It captures playoff-relevant roster
    shape from the same NST data: high-minute top skaters, top-pair defensemen,
    and depth quality.
    """
    cache_key = (team, db_path, location)
    if cache_key in _profile_cache:
        return _profile_cache[cache_key]

    players, active = _load_team_players(team, db_path)
    players = _eligible_players(players, active)

    toi_col = f"TOI_{location}"
    xgf_col = f"xGF/60_{location}"
    gf_col = f"GF/60_{location}"
    xga_col = f"xGA/60_{location}"
    ga_col = f"GA/60_{location}"

    needed = {toi_col, xgf_col, gf_col, xga_col, ga_col, "Position"}
    if players.empty or not needed.issubset(players.columns):
        profile = {
            "top_skater_signal": 0.0,
            "elite_defense_signal": 0.0,
            "depth_signal": 0.0,
            "xg_modifier": 0.0,
            "offense_multiplier": 1.0,
            "defense_multiplier": 1.0,
        }
        _profile_cache[cache_key] = profile
        return profile

    skaters = players[
        players["Position"].apply(lambda p: _is_forward(p) or _is_defense(p))
    ].copy()
    skaters = skaters[pd.to_numeric(skaters[toi_col], errors="coerce").fillna(0) > 0]

    if skaters.empty:
        profile = {
            "top_skater_signal": 0.0,
            "elite_defense_signal": 0.0,
            "depth_signal": 0.0,
            "xg_modifier": 0.0,
            "offense_multiplier": 1.0,
            "defense_multiplier": 1.0,
        }
        _profile_cache[cache_key] = profile
        return profile

    skaters["profile_off"] = (skaters[xgf_col] * XG_WEIGHT) + (skaters[gf_col] * ACTUAL_GOALS_WEIGHT)
    skaters["profile_def"] = (skaters[xga_col] * XG_WEIGHT) + (skaters[ga_col] * ACTUAL_GOALS_WEIGHT)
    skaters["profile_impact"] = (
        ((skaters["profile_off"] - LEAGUE_AVG_XG_PER_60) / LEAGUE_AVG_XG_PER_60)
        + ((LEAGUE_AVG_XG_PER_60 - skaters["profile_def"]) / LEAGUE_AVG_XG_PER_60)
    ) / 2

    top_skaters = skaters.sort_values(toi_col, ascending=False).head(6)
    defensemen = skaters[skaters["Position"].apply(_is_defense)]
    top_defense = defensemen.sort_values(toi_col, ascending=False).head(2)
    depth = skaters.sort_values(toi_col, ascending=False).iloc[8:]

    top_signal = _weighted_average(top_skaters, "profile_impact", toi_col)
    elite_d_signal = _weighted_average(top_defense, "profile_impact", toi_col)
    depth_signal = _weighted_average(depth, "profile_impact", toi_col)

    modifier = (
        top_signal * TOP_SKATER_PREMIUM_WEIGHT
        + elite_d_signal * ELITE_DEFENSE_PREMIUM_WEIGHT
        + depth_signal * DEPTH_STABILITY_WEIGHT
    )
    modifier = float(np.clip(modifier, -TEAM_PROFILE_MAX_XG_ADJUSTMENT, TEAM_PROFILE_MAX_XG_ADJUSTMENT))

    profile = {
        "top_skater_signal": top_signal,
        "elite_defense_signal": elite_d_signal,
        "depth_signal": depth_signal,
        "xg_modifier": modifier,
        "offense_multiplier": 1.0 + modifier,
        "defense_multiplier": 1.0 - modifier,
    }
    _profile_cache[cache_key] = profile
    return profile


def build_team_profile_report(db_path, teams=None):
    """Build a compact audit table for base strength and profile modifiers."""
    conn = sqlite3.connect(db_path)
    if teams is None:
        teams = pd.read_sql(
            "SELECT DISTINCT Team FROM players WHERE Team IS NOT NULL ORDER BY Team",
            conn
        )["Team"].tolist()
    conn.close()

    rows = []
    for team in teams:
        home_off, home_def = get_team_strength(team, db_path, "home")
        away_off, away_def = get_team_strength(team, db_path, "away")
        home_profile = get_team_profile(team, db_path, "home")
        away_profile = get_team_profile(team, db_path, "away")
        avg_modifier = (home_profile["xg_modifier"] + away_profile["xg_modifier"]) / 2

        rows.append({
            "Team": team,
            "Home Off": float(home_off),
            "Home Def": float(home_def),
            "Away Off": float(away_off),
            "Away Def": float(away_def),
            "Top Home": home_profile["top_skater_signal"],
            "Top Away": away_profile["top_skater_signal"],
            "Elite D Home": home_profile["elite_defense_signal"],
            "Elite D Away": away_profile["elite_defense_signal"],
            "Depth Home": home_profile["depth_signal"],
            "Depth Away": away_profile["depth_signal"],
            "Profile Adj": avg_modifier,
        })

    report = pd.DataFrame(rows)
    if report.empty:
        return report
    return report.sort_values("Profile Adj", ascending=False).reset_index(drop=True)


def display_team_profile_report(db_path, teams=None, top_n=None):
    """Print the team profile report used by the xG adjustment layer."""
    report = build_team_profile_report(db_path, teams=teams)
    if report.empty:
        print("\nNo team profile data available.")
        return report

    display = report.copy()
    if top_n is not None:
        display = display.head(top_n)

    for col in display.columns:
        if col != "Team" and pd.api.types.is_numeric_dtype(display[col]):
            display[col] = display[col].round(3)

    print("\n" + "=" * 120)
    print("TEAM PROFILE REPORT - BASE STRENGTH + TOP-END / ELITE-D / DEPTH MODIFIERS")
    print("=" * 120)
    print(display.to_string(index=False))
    return report
