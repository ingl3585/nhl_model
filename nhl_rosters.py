# nhl_rosters.py
# Player roster and stats scraping from Natural Stat Trick with recent form weighting

import pandas as pd
import numpy as np
import sqlite3
import requests
from bs4 import BeautifulSoup
from io import StringIO
from config import (
    TEAM_ABBREV_FIXES, MIN_TOI_MINUTES, RECENT_FORM_WEIGHT,
    FULL_SEASON_WEIGHT, LAST_YEAR_WEIGHT, SHOW_ROSTER_DUMP
)

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
    "TOR": "Toronto Maple Leafs",
    "UTA": "Utah Mammoth",
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

    # Split by comma or slash for traded players, keep dots for NST abbreviations
    parts = [p.strip() for p in str(team_str).replace('/', ',').split(',')]
    parts = [p for p in parts if p]

    # Use the last team (current team for traded players)
    last_team = parts[-1].upper() if parts else team_str

    # Look up in TEAM_MAP (handles both "LAK", "L.A", etc.)
    return TEAM_MAP.get(last_team, team_str)


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


def merge_and_weight_stats(full_df, recent_df, last_year_df=None,
                          recent_weight=0.55, full_weight=0.30, last_year_weight=0.15):
    """
    Merge current season (full + recent) and last year's stats with three-way weighted averaging.

    Args:
        full_df (pd.DataFrame): Current season full stats
        recent_df (pd.DataFrame): Current season last 10 games stats
        last_year_df (pd.DataFrame): Last year's full season stats (optional)
        recent_weight (float): Weight for recent stats (default 0.55)
        full_weight (float): Weight for current full season (default 0.30)
        last_year_weight (float): Weight for last year (default 0.15)

    Returns:
        pd.DataFrame: Weighted player stats
    """
    if full_df.empty:
        return full_df

    # Handle missing datasets
    has_recent = not recent_df.empty if recent_df is not None else False
    has_last_year = not last_year_df.empty if last_year_df is not None else False

    if not has_recent and not has_last_year:
        print("   ⚠ No recent or last year stats available, using full season only")
        return full_df

    # Normalize weights if datasets are missing
    if not has_recent:
        print("   ⚠ No recent stats available, redistributing weight")
        full_weight = full_weight / (full_weight + last_year_weight) if has_last_year else 1.0
        last_year_weight = 1.0 - full_weight if has_last_year else 0.0
        recent_weight = 0.0
    elif not has_last_year:
        print("   ⚠ No last year stats available, redistributing weight")
        full_weight = full_weight / (full_weight + recent_weight)
        recent_weight = 1.0 - full_weight
        last_year_weight = 0.0

    # Clean team names for all datasets
    full_df = full_df.copy()
    full_df["Team"] = full_df["Team"].apply(clean_team_name)

    if has_recent:
        recent_df = recent_df.copy()
        recent_df["Team"] = recent_df["Team"].apply(clean_team_name)

    if has_last_year:
        last_year_df = last_year_df.copy()
        last_year_df["Team"] = last_year_df["Team"].apply(clean_team_name)

    # Start with full season as base
    merged = full_df.copy()

    # Merge recent stats if available
    if has_recent:
        merged = merged.merge(
            recent_df,
            on=["Player_ID", "Team"],
            how="left",
            suffixes=("_full", "_recent")
        )

    # Merge last year stats if available (match on Player_ID only, not Team - players may have changed teams)
    if has_last_year:
        # Only keep Player_ID and stat columns from last year (not Team, since players may have moved)
        last_year_merge_cols = ["Player_ID"] + [c for c in last_year_df.columns
                                                  if c not in ["Player_ID", "Team", "Player", "Position", "GP", "Games Played"]]
        merged = merged.merge(
            last_year_df[last_year_merge_cols],
            on="Player_ID",
            how="left",
            suffixes=("", "_lastyear")
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

    # Handle Player column (might have _full suffix if recent was merged)
    if "Player_full" in merged.columns:
        weighted["Player"] = merged["Player_full"]
    else:
        weighted["Player"] = merged["Player"]

    weighted["Team"] = merged["Team"]

    # Keep GP from full season (accurate games played)
    gp_col = None
    if "GP" in full_df.columns:
        gp_col = "GP"
    elif "Games Played" in full_df.columns:
        gp_col = "Games Played"

    if gp_col:
        if has_recent and f"{gp_col}_full" in merged.columns:
            weighted[gp_col] = merged[f"{gp_col}_full"]
        else:
            weighted[gp_col] = merged[gp_col]

    # Keep Position if available
    if "Position" in full_df.columns:
        if has_recent and "Position_full" in merged.columns:
            weighted["Position"] = merged["Position_full"]
        else:
            weighted["Position"] = merged["Position"]

    # Weight all numeric stats (three-way blend)
    for stat in stats_to_weight:
        # Determine column names based on what merges happened
        if has_recent:
            full_col = f"{stat}_full"
            recent_col = f"{stat}_recent"
        else:
            full_col = stat
            recent_col = None

        # Last year column (if it exists after merge)
        if has_last_year:
            # The column might be stat_lastyear or just exist without suffix if no conflicts
            if f"{stat}_lastyear" in merged.columns:
                lastyear_col = f"{stat}_lastyear"
            elif has_recent and stat not in merged.columns and f"{stat}_full" not in merged.columns:
                # Edge case: stat only exists in last year
                lastyear_col = stat
            else:
                lastyear_col = None
        else:
            lastyear_col = None

        # Convert to numeric, coercing errors to NaN
        full_vals = pd.to_numeric(merged.get(full_col, pd.Series([np.nan] * len(merged))), errors='coerce')
        recent_vals = pd.to_numeric(merged.get(recent_col, pd.Series([np.nan] * len(merged))), errors='coerce') if recent_col else pd.Series([np.nan] * len(merged))
        lastyear_vals = pd.to_numeric(merged.get(lastyear_col, pd.Series([np.nan] * len(merged))), errors='coerce') if lastyear_col else pd.Series([np.nan] * len(merged))

        # Three-way weighted average
        # Start with zeros, then add each component where available
        weighted[stat] = pd.Series([0.0] * len(merged))

        # Track total weight actually used for each player
        total_weight = pd.Series([0.0] * len(merged))

        # Add full season component
        mask_full = full_vals.notna()
        weighted.loc[mask_full, stat] += full_vals[mask_full] * full_weight
        total_weight[mask_full] += full_weight

        # Add recent component
        if has_recent:
            mask_recent = recent_vals.notna()
            weighted.loc[mask_recent, stat] += recent_vals[mask_recent] * recent_weight
            total_weight[mask_recent] += recent_weight

        # Add last year component
        if has_last_year:
            mask_lastyear = lastyear_vals.notna()
            weighted.loc[mask_lastyear, stat] += lastyear_vals[mask_lastyear] * last_year_weight
            total_weight[mask_lastyear] += last_year_weight

        # Normalize by actual total weight (handles missing data)
        mask_has_data = total_weight > 0
        weighted.loc[mask_has_data, stat] = weighted.loc[mask_has_data, stat] / total_weight[mask_has_data]

        # If no data at all, set to NaN
        weighted.loc[~mask_has_data, stat] = np.nan

    return weighted


def download_nst_data(db_path, recent_weight=None, full_weight=None, last_year_weight=None):
    """
    Download live player stats from Natural Stat Trick with three-way weighting.
    Combines current season (recent + full) with last year's stats.
    Filters rosters to only include skaters who played in their team's last game (injury/trade filtering).

    Args:
        db_path (str): Path to SQLite database file
        recent_weight (float): Weight for last 10 games, uses RECENT_FORM_WEIGHT from config if None
        full_weight (float): Weight for current full season, uses FULL_SEASON_WEIGHT from config if None
        last_year_weight (float): Weight for last year, uses LAST_YEAR_WEIGHT from config if None

    Returns:
        pd.DataFrame: Weighted player data (skaters + goalies)
    """
    if recent_weight is None:
        recent_weight = RECENT_FORM_WEIGHT
    if full_weight is None:
        full_weight = FULL_SEASON_WEIGHT
    if last_year_weight is None:
        last_year_weight = LAST_YEAR_WEIGHT

    print(f"Downloading live 2025-26 player stats from Natural Stat Trick...")
    print(f"   Weighting: {recent_weight:.0%} recent (L10) + {full_weight:.0%} full season + {last_year_weight:.0%} last year")

    headers = {"User-Agent": "Mozilla/5.0"}

    # URLs for CURRENT SEASON (2025-26) full season (rate=y for per-60 stats, sit=all for all situations)
    skaters_full_url = "https://www.naturalstattrick.com/playerteams.php?fromseason=20252026&thruseason=20252026&stype=2&sit=all&score=all&stdoi=oi&rate=y&team=ALL&pos=S&loc=B&toi=0&gpfilt=none&fd=&td=&tgp=410&lines=single&draftteam=ALL"
    goalies_full_url = skaters_full_url.replace("&pos=S", "&pos=G").replace("stdoi=oi", "stdoi=g")

    # URLs for CURRENT SEASON last 10 games (rate=y for per-60 stats, sit=all for all situations)
    skaters_recent_url = "https://www.naturalstattrick.com/playerteams.php?fromseason=20252026&thruseason=20252026&stype=2&sit=all&score=all&stdoi=oi&rate=y&team=ALL&pos=S&loc=B&toi=0&gpfilt=gpteam&fd=&td=&tgp=10&lines=single&draftteam=ALL"
    goalies_recent_url = "https://www.naturalstattrick.com/playerteams.php?fromseason=20252026&thruseason=20252026&stype=2&sit=all&score=all&stdoi=g&rate=y&team=ALL&pos=S&loc=B&toi=0&gpfilt=gpteam&fd=&td=&tgp=10&lines=single&draftteam=ALL"

    # URL for last game rosters (gp=1) - identifies active roster (injuries/trades)
    skaters_last_game_url = "https://www.naturalstattrick.com/playerteams.php?fromseason=20252026&thruseason=20252026&stype=2&sit=all&score=all&stdoi=oi&rate=y&team=ALL&pos=S&loc=B&toi=0&gpfilt=gpteam&fd=&td=&tgp=1&lines=single&draftteam=ALL"

    # URLs for LAST YEAR (2024-25) full season stats
    skaters_lastyear_url = "https://www.naturalstattrick.com/playerteams.php?fromseason=20242025&thruseason=20242025&stype=2&sit=all&score=all&stdoi=oi&rate=y&team=ALL&pos=S&loc=B&toi=0&gpfilt=none&fd=&td=&tgp=410&lines=single&draftteam=ALL"
    goalies_lastyear_url = skaters_lastyear_url.replace("&pos=S", "&pos=G").replace("stdoi=oi", "stdoi=g")

    # Download current season datasets
    skaters_full = download_nst_stats(skaters_full_url, headers, "Full season skaters (2025-26)")
    goalies_full = download_nst_stats(goalies_full_url, headers, "Full season goalies (2025-26)")
    skaters_recent = download_nst_stats(skaters_recent_url, headers, "Last 10 games skaters (2025-26)")
    goalies_recent = download_nst_stats(goalies_recent_url, headers, "Last 10 games goalies (2025-26)")
    skaters_last_game = download_nst_stats(skaters_last_game_url, headers, "Last game rosters (injury/trade filter)")

    # Download last year's datasets (if enabled)
    skaters_lastyear = pd.DataFrame()
    goalies_lastyear = pd.DataFrame()
    if last_year_weight > 0:
        print("   Downloading last year (2024-25) stats for supplemental weighting...")
        skaters_lastyear = download_nst_stats(skaters_lastyear_url, headers, "Last year skaters (2024-25)")
        goalies_lastyear = download_nst_stats(goalies_lastyear_url, headers, "Last year goalies (2024-25)")

    # Add Position='G' to goalies (they don't have position column from NST)
    if not goalies_full.empty:
        goalies_full['Position'] = 'G'
    if not goalies_recent.empty:
        goalies_recent['Position'] = 'G'
    if not goalies_lastyear.empty:
        goalies_lastyear['Position'] = 'G'

    # Check if we got any data
    if skaters_full.empty and goalies_full.empty:
        print("   ⚠ NST download failed completely → using league averages")
        return pd.DataFrame()

    # Use last game roster as the source of truth for current team assignments
    active_player_ids = set()
    if not skaters_last_game.empty and not skaters_full.empty:
        # Filter last game roster to only meaningful ice time (>5 min in that game)
        # Note: TOI in last game data is for THAT GAME ONLY, not full season
        if "TOI" in skaters_last_game.columns:
            skaters_last_game_filtered = skaters_last_game[skaters_last_game["TOI"] > 5].copy()
            print(f"   → Last game roster: {len(skaters_last_game_filtered)} skaters with >5min ice time in last game (from {len(skaters_last_game)} total)")
        else:
            skaters_last_game_filtered = skaters_last_game.copy()
            print(f"   ⚠ No TOI column in last game data - using all {len(skaters_last_game_filtered)} players")

        # Clean team names for last game data (this is the CURRENT team)
        skaters_last_game_filtered["Team"] = skaters_last_game_filtered["Team"].apply(clean_team_name)

        # For traded players: update their team in full-season data to match last game
        # Match by Player name (more reliable than Player_ID for traded players)
        if "Player" in skaters_last_game_filtered.columns and "Player" in skaters_full.columns:
            # Create mapping of Player name -> current team from last game
            current_team_map = dict(zip(skaters_last_game_filtered["Player"], skaters_last_game_filtered["Team"]))

            # Update full-season data: if player is in last game, use their current team
            def update_team(row):
                if row["Player"] in current_team_map:
                    return current_team_map[row["Player"]]
                else:
                    return clean_team_name(row["Team"])

            skaters_full["Team"] = skaters_full.apply(update_team, axis=1)

            # Do the same for recent stats
            if not skaters_recent.empty and "Player" in skaters_recent.columns:
                skaters_recent["Team"] = skaters_recent.apply(update_team, axis=1)

            print(f"   ✓ Updated team assignments for traded players based on last game roster")

        # Filter to only include players from last game roster
        active_player_names = set(skaters_last_game_filtered["Player"])
        skaters_full = skaters_full[skaters_full["Player"].isin(active_player_names)].copy()
        if not skaters_recent.empty:
            skaters_recent = skaters_recent[skaters_recent["Player"].isin(active_player_names)].copy()

        # Track active player IDs for MIN_TOI bypass
        active_player_ids = set(skaters_full["Player_ID"])
        print(f"   ✓ Filtered to {len(skaters_full)} active roster players from last game")
    else:
        print("   ⚠ Could not identify last game roster - using all players")

    # Merge and weight stats (three-way: recent + full + last year)
    print("   Merging and weighting stats...")
    skaters_weighted = merge_and_weight_stats(
        skaters_full, skaters_recent, skaters_lastyear,
        recent_weight, full_weight, last_year_weight
    )
    goalies_weighted = merge_and_weight_stats(
        goalies_full, goalies_recent, goalies_lastyear,
        recent_weight, full_weight, last_year_weight
    )

    # Combine skaters and goalies
    all_players = pd.concat([skaters_weighted, goalies_weighted], ignore_index=True, sort=False)

    if not all_players.empty:
        conn = sqlite3.connect(db_path)
        all_players.to_sql("players", conn, if_exists="replace", index=False)

        # Store active player IDs (from last game) in a separate table to bypass MIN_TOI filter
        if not skaters_last_game.empty and "TOI" in skaters_last_game.columns:
            active_ids_df = pd.DataFrame({
                "Player_ID": list(active_player_ids)
            })
            active_ids_df.to_sql("active_roster", conn, if_exists="replace", index=False)
            print(f"   ✓ Saved {len(active_player_ids)} active roster players (bypass MIN_TOI filter)")

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

        # Check if active_roster table exists
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='active_roster'")
        has_active_roster = cursor.fetchone() is not None

        active_ids = set()
        if has_active_roster:
            active_df = pd.read_sql("SELECT Player_ID FROM active_roster", conn)
            active_ids = set(active_df["Player_ID"])

        conn.close()
    except Exception as e:
        print(f"   ✗ Could not load player data: {e}")
        return

    if df.empty:
        print("   No player data available")
        return

    print("\n" + "=" * 140)
    print("PLAYER STATS BY TEAM (70% xG + 30% Actual Goals, 55% Recent L10 + 30% Full Season + 15% Last Year)")
    print("=" * 140)

    # Group by team
    for team in sorted(df["Team"].unique()):
        team_players = df[df["Team"] == team].copy()

        # Filter by TOI if column exists, BUT keep active roster players regardless
        if "TOI" in team_players.columns:
            if has_active_roster:
                # Keep players with sufficient TOI OR in active roster
                team_players = team_players[
                    (team_players["TOI"] > min_toi) | (team_players["Player_ID"].isin(active_ids))
                ]
            else:
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