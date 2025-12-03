# nhl_rosters.py
# Player roster and stats scraping from Natural Stat Trick with recent form weighting

import pandas as pd
import numpy as np
import sqlite3
import requests
from bs4 import BeautifulSoup
from io import StringIO
from config import TEAM_ABBREV_FIXES, MIN_TOI_MINUTES, RECENT_FORM_WEIGHT, SHOW_ROSTER_DUMP

# Team mappings (consistent with schedule module)
TEAM_MAP = {
    "ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres",
    "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks",
    "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets", "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings", "L.A": "Los Angeles Kings",
    "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens", "NSH": "Nashville Predators",
    "NJD": "New Jersey Devils", "N.J": "New Jersey Devils",
    "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins",
    "SJS": "San Jose Sharks", "S.J": "San Jose Sharks",
    "SEA": "Seattle Kraken", "STL": "St. Louis Blues",
    "TBL": "Tampa Bay Lightning", "T.B": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs", "UTA": "Utah Mammoth",
    "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights",
    "WSH": "Washington Capitals", "WPG": "Winnipeg Jets"
}

# Apply config fixes
TEAM_MAP.update(TEAM_ABBREV_FIXES)


def clean_team_name(team_str):
    """
    Clean team name from NST format (handles trades).

    Args:
        team_str (str): Team string from NST (may contain multiple teams for traded players)

    Returns:
        str: Normalized team name (uses last team for traded players)
    """
    if pd.isna(team_str):
        return np.nan

    parts = [p.strip().replace('.', '') for p in str(team_str).replace('/', ',').split(',')]
    parts = [p for p in parts if p]
    return TEAM_MAP.get(parts[-1].upper(), team_str) if parts else team_str


def download_nst_stats(url, headers, dataset_name):
    """
    Download stats from a single NST URL.

    Args:
        url (str): NST URL
        headers (dict): Request headers
        dataset_name (str): Name for logging

    Returns:
        pd.DataFrame: Player stats or empty DataFrame on failure
    """
    try:
        r = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        csv_link = soup.find("a", string=lambda t: t and "CSV" in t)

        if csv_link:
            df = pd.read_csv("https://www.naturalstattrick.com" + csv_link["href"])
        else:
            df = pd.read_html(StringIO(r.text))[0]

        # NST's first column is player ID (unnamed) - rename it for unique identification
        if df.columns[0] in [0, '', 'Unnamed: 0']:
            df.rename(columns={df.columns[0]: 'Player_ID'}, inplace=True)

        print(f"   ✓ {dataset_name}: {len(df)} players")
        return df

    except Exception as e:
        print(f"   ✗ {dataset_name} failed: {e}")
        return pd.DataFrame()


def merge_and_weight_stats(full_df, recent_df, recent_weight=0.70):
    """
    Merge full-season and recent stats with weighted averaging.

    Args:
        full_df (pd.DataFrame): Full season stats
        recent_df (pd.DataFrame): Last 10 games stats
        recent_weight (float): Weight for recent stats (0-1), default 0.70

    Returns:
        pd.DataFrame: Weighted player stats
    """
    if full_df.empty:
        return full_df
    if recent_df.empty:
        print("   ⚠ No recent stats available, using full season only")
        return full_df

    full_weight = 1 - recent_weight

    # Clean team names for both datasets
    full_df = full_df.copy()
    recent_df = recent_df.copy()
    full_df["Team"] = full_df["Team"].apply(clean_team_name)
    recent_df["Team"] = recent_df["Team"].apply(clean_team_name)

    # Merge on Player_ID + Team (unique identification)
    merged = full_df.merge(
        recent_df,
        on=["Player_ID", "Team"],
        how="left",
        suffixes=("_full", "_recent")
    )

    # Identify columns to keep as-is (non-numeric or special columns)
    keep_as_is = ["Player_ID", "Player", "Team", "Position", "GP", "Games Played"]
    
    # Identify numeric columns to weight
    stats_to_weight = []
    for col in full_df.columns:
        if col not in keep_as_is:
            # Try to convert to numeric to see if it's a stat column
            try:
                pd.to_numeric(full_df[col], errors='coerce')
                if full_df[col].dtype in ['int64', 'float64'] or pd.to_numeric(full_df[col], errors='coerce').notna().any():
                    stats_to_weight.append(col)
            except:
                continue

    # Build weighted dataframe
    weighted = pd.DataFrame()
    weighted["Player_ID"] = merged["Player_ID"]
    weighted["Player"] = merged.get("Player_full", merged.get("Player"))
    weighted["Team"] = merged["Team"]

    # Keep GP from full season (accurate games played)
    gp_col = None
    if "GP" in full_df.columns:
        gp_col = "GP"
    elif "Games Played" in full_df.columns:
        gp_col = "Games Played"
    
    if gp_col:
        weighted[gp_col] = merged[f"{gp_col}_full"]

    # Keep Position if available
    if "Position" in full_df.columns:
        weighted["Position"] = merged.get("Position_full", merged.get("Position"))

    # Weight all numeric stats
    for stat in stats_to_weight:
        full_col = f"{stat}_full"
        recent_col = f"{stat}_recent"

        # Convert to numeric, coercing errors to NaN
        full_vals = pd.to_numeric(merged[full_col], errors='coerce')
        recent_vals = pd.to_numeric(merged.get(recent_col, pd.Series([np.nan] * len(merged))), errors='coerce')

        # Weighted average: use recent if available, otherwise full season
        weighted[stat] = full_vals.where(
            recent_vals.isna(),
            full_vals * full_weight + recent_vals * recent_weight
        )

    return weighted


def download_nst_data(db_path, recent_weight=None):
    """
    Download live player stats from Natural Stat Trick with recent form weighting.

    Args:
        db_path (str): Path to SQLite database file
        recent_weight (float): Weight for last 10 games (0-1), uses RECENT_FORM_WEIGHT from config if None

    Returns:
        pd.DataFrame: Weighted player data (skaters + goalies)
    """
    if recent_weight is None:
        recent_weight = RECENT_FORM_WEIGHT  # Use config value

    print(f"Downloading live 2025-26 player stats from Natural Stat Trick...")
    print(f"   Weighting: {recent_weight:.0%} recent form, {(1-recent_weight):.0%} full season")

    headers = {"User-Agent": "Mozilla/5.0"}

    # URLs for full season (rate=y for per-60 stats)
    skaters_full_url = "https://www.naturalstattrick.com/playerteams.php?fromseason=20252026&thruseason=20252026&stype=2&sit=5v5&score=all&stdoi=oi&rate=y&team=ALL&pos=S&loc=B&toi=0&gpfilt=none&fd=&td=&tgp=410&lines=single&draftteam=ALL"
    goalies_full_url = skaters_full_url.replace("&pos=S", "&pos=G").replace("stdoi=oi", "stdoi=g")

    # URLs for last 10 games (rate=y for per-60 stats)
    skaters_recent_url = "https://www.naturalstattrick.com/playerteams.php?fromseason=20252026&thruseason=20252026&stype=2&sit=5v5&score=all&stdoi=oi&rate=y&team=ALL&pos=S&loc=B&toi=0&gpfilt=gpteam&fd=&td=&tgp=10&lines=single&draftteam=ALL"
    goalies_recent_url = "https://www.naturalstattrick.com/playerteams.php?fromseason=20252026&thruseason=20252026&stype=2&sit=5v5&score=all&stdoi=g&rate=y&team=ALL&pos=S&loc=B&toi=0&gpfilt=gpteam&fd=&td=&tgp=10&lines=single&draftteam=ALL"

    # Download all datasets
    skaters_full = download_nst_stats(skaters_full_url, headers, "Full season skaters")
    goalies_full = download_nst_stats(goalies_full_url, headers, "Full season goalies")
    skaters_recent = download_nst_stats(skaters_recent_url, headers, "Last 10 games skaters")
    goalies_recent = download_nst_stats(goalies_recent_url, headers, "Last 10 games goalies")

    # Add Position='G' to goalies (they don't have position column from NST)
    if not goalies_full.empty:
        goalies_full['Position'] = 'G'
    if not goalies_recent.empty:
        goalies_recent['Position'] = 'G'

    # Check if we got any data
    if skaters_full.empty and goalies_full.empty:
        print("   ⚠ NST download failed completely → using league averages")
        return pd.DataFrame()

    # Merge and weight stats
    print("   Merging and weighting stats...")
    skaters_weighted = merge_and_weight_stats(skaters_full, skaters_recent, recent_weight)
    goalies_weighted = merge_and_weight_stats(goalies_full, goalies_recent, recent_weight)

    # Combine skaters and goalies
    all_players = pd.concat([skaters_weighted, goalies_weighted], ignore_index=True, sort=False)

    if not all_players.empty:
        conn = sqlite3.connect(db_path)
        all_players.to_sql("players", conn, if_exists="replace", index=False)
        conn.close()
        print(f"   ✓ Success: {len(all_players)} weighted players saved to {db_path}")

    return all_players

def view_team_rosters(db_path, min_toi=None):
    """
    Display individual player stats organized by team with position groups.

    Args:
        db_path (str): Path to SQLite database
        min_toi (int, optional): Minimum TOI filter, defaults to MIN_TOI_MINUTES
    """
    from team_strength import get_team_strength

    if min_toi is None:
        min_toi = MIN_TOI_MINUTES

    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql("SELECT * FROM players", conn)
        conn.close()
    except Exception as e:
        print(f"   ✗ Could not load player data: {e}")
        return

    if df.empty:
        print("   No player data available")
        return

    print("\n" + "=" * 140)
    print("PLAYER STATS BY TEAM (70% xG + 30% Actual Goals, 60% Recent Form + 40% Full Season)")
    print("=" * 140)

    # Group by team
    for team in sorted(df["Team"].unique()):
        team_players = df[df["Team"] == team].copy()

        # Filter by TOI if column exists
        if "TOI" in team_players.columns:
            team_players = team_players[team_players["TOI"] > min_toi]

        if team_players.empty:
            continue

        # Calculate team strength
        team_offense, team_defense = get_team_strength(team, db_path)

        print(f"\n{team}")
        print("-" * 140)
        print(f"TEAM STRENGTH (Position-Weighted):")
        print(f"  Offensive Rating: {team_offense:.2f} xGF/60")
        print(f"  Defensive Rating: {team_defense:.2f} xGA/60")
        print()

        # Split by position
        forwards = team_players[team_players['Position'].isin(['C', 'L', 'R'])].copy() if 'Position' in team_players.columns else pd.DataFrame()
        defensemen = team_players[team_players['Position'] == 'D'].copy() if 'Position' in team_players.columns else pd.DataFrame()
        goalies = team_players[team_players['Position'] == 'G'].copy() if 'Position' in team_players.columns else pd.DataFrame()

        # Calculate contributions if we have the required columns
        if not team_players.empty and 'xGF/60' in team_players.columns and 'xGA/60' in team_players.columns and 'TOI' in team_players.columns:
            from config import XG_WEIGHT, ACTUAL_GOALS_WEIGHT

            total_toi = team_players['TOI'].sum()

            # Calculate weighted values for ALL players first (for accurate team averages)
            if 'GF/60' in team_players.columns and 'GA/60' in team_players.columns:
                team_players['Weighted xGF/60'] = (team_players['xGF/60'] * XG_WEIGHT + team_players['GF/60'] * ACTUAL_GOALS_WEIGHT)
                team_players['Weighted xGA/60'] = (team_players['xGA/60'] * XG_WEIGHT + team_players['GA/60'] * ACTUAL_GOALS_WEIGHT)

            # Forwards
            if not forwards.empty and 'GF/60' in forwards.columns and 'GA/60' in forwards.columns:
                # Calculate weighted (blended) values
                forwards['Weighted xGF/60'] = (forwards['xGF/60'] * XG_WEIGHT + forwards['GF/60'] * ACTUAL_GOALS_WEIGHT).round(2)
                forwards['Weighted xGA/60'] = (forwards['xGA/60'] * XG_WEIGHT + forwards['GA/60'] * ACTUAL_GOALS_WEIGHT).round(2)

                # Use weighted values for contribution calculations
                forward_avg_weighted_xgf = forwards['Weighted xGF/60'].mean()
                team_avg_weighted_xga = team_players['Weighted xGA/60'].mean()

                forwards['Off_Contrib'] = ((forwards['Weighted xGF/60'] - forward_avg_weighted_xgf) * (forwards['TOI'] / total_toi) * 0.85).round(2)
                forwards['Def_Contrib'] = ((team_avg_weighted_xga - forwards['Weighted xGA/60']) * (forwards['TOI'] / total_toi) * 0.20).round(2)
                forwards = forwards.sort_values('Off_Contrib', ascending=False)

            # Defensemen
            if not defensemen.empty and 'GF/60' in defensemen.columns and 'GA/60' in defensemen.columns:
                # Calculate weighted (blended) values
                defensemen['Weighted xGF/60'] = (defensemen['xGF/60'] * XG_WEIGHT + defensemen['GF/60'] * ACTUAL_GOALS_WEIGHT).round(2)
                defensemen['Weighted xGA/60'] = (defensemen['xGA/60'] * XG_WEIGHT + defensemen['GA/60'] * ACTUAL_GOALS_WEIGHT).round(2)

                # Use weighted values for contribution calculations
                defense_avg_weighted_xgf = defensemen['Weighted xGF/60'].mean()
                team_avg_weighted_xga = team_players['Weighted xGA/60'].mean()

                defensemen['Off_Contrib'] = ((defensemen['Weighted xGF/60'] - defense_avg_weighted_xgf) * (defensemen['TOI'] / total_toi) * 0.15).round(2)
                defensemen['Def_Contrib'] = ((team_avg_weighted_xga - defensemen['Weighted xGA/60']) * (defensemen['TOI'] / total_toi) * 0.30).round(2)
                defensemen = defensemen.sort_values('Def_Contrib', ascending=False)

            # Goalies - use goalie-specific xG Against/60 stat
            if not goalies.empty and 'xG Against/60' in goalies.columns and 'GAA' in goalies.columns:
                # Calculate weighted (blended) value
                goalies['Weighted xGA/60'] = (goalies['xG Against/60'] * XG_WEIGHT + goalies['GAA'] * ACTUAL_GOALS_WEIGHT).round(2)

                # Use weighted values for contribution calculations
                goalie_avg_weighted_xga = goalies['Weighted xGA/60'].mean()

                goalies['Off_Contrib'] = 0.0
                goalies['Def_Contrib'] = ((goalie_avg_weighted_xga - goalies['Weighted xGA/60']) * (goalies['TOI'] / total_toi) * 0.50).round(2)
                goalies = goalies.sort_values('Def_Contrib', ascending=False)

        # Display columns - need to check each position dataframe for available columns
        # Include both expected (xG), actual (G), and weighted (blended) stats
        base_cols = ['Player_ID', 'Player', 'Position', 'TOI', 'xGF/60', 'GF/60', 'xGA/60', 'GA/60', 'Weighted xGF/60', 'Weighted xGA/60']
        contrib_cols = ['Off_Contrib', 'Def_Contrib']

        # Display each position group
        if not forwards.empty:
            print("FORWARDS (sorted by offensive contribution)")
            # Build display columns from what's available in forwards dataframe
            forwards_display_cols = [c for c in base_cols + contrib_cols if c in forwards.columns]
            forwards_display = forwards[forwards_display_cols].copy()
            for col in forwards_display.columns:
                if col not in ['Player_ID', 'Player', 'Position'] and pd.api.types.is_numeric_dtype(forwards_display[col]):
                    forwards_display[col] = forwards_display[col].round(2)
            print(forwards_display.to_string(index=False))
            print()

        if not defensemen.empty:
            print("DEFENSEMEN (sorted by defensive contribution)")
            # Build display columns from what's available in defensemen dataframe
            defensemen_display_cols = [c for c in base_cols + contrib_cols if c in defensemen.columns]
            defensemen_display = defensemen[defensemen_display_cols].copy()
            for col in defensemen_display.columns:
                if col not in ['Player_ID', 'Player', 'Position'] and pd.api.types.is_numeric_dtype(defensemen_display[col]):
                    defensemen_display[col] = defensemen_display[col].round(2)
            print(defensemen_display.to_string(index=False))
            print()

        if not goalies.empty:
            print("GOALIES (sorted by defensive contribution)")
            # For goalies, use their specific columns (xG Against/60, GAA, and weighted)
            goalie_base_cols = ['Player_ID', 'Player', 'Position', 'TOI', 'xG Against/60', 'GAA', 'Weighted xGA/60']
            goalies_display_cols = [c for c in goalie_base_cols + contrib_cols if c in goalies.columns]
            goalies_display = goalies[goalies_display_cols].copy()
            for col in goalies_display.columns:
                if col not in ['Player_ID', 'Player', 'Position'] and pd.api.types.is_numeric_dtype(goalies_display[col]):
                    goalies_display[col] = goalies_display[col].round(2)
            print(goalies_display.to_string(index=False))
            print()
        
        print()  # Extra line between teams
    
    print("=" * 120 + "\n")