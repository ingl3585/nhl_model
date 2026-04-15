# nhl_rosters.py
# Player roster and stats scraping from Natural Stat Trick with recent form weighting

import pandas as pd
import numpy as np
import sqlite3
import os
import time
import tempfile
import datetime
import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

from config import (
    TEAM_ABBREV_FIXES, MIN_TOI_MINUTES, RECENT_FORM_WEIGHT,
    FULL_SEASON_WEIGHT, LAST_YEAR_WEIGHT, SHOW_ROSTER_DUMP, RECENT_GAMES_TGP,
    MIN_GP_PERCENTAGE, ACTIVE_ROSTER_WINDOW, ACTIVE_ROSTER_MIN_GP_PCT
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


def create_nst_driver():
    """
    Create an undetected Chrome driver, configure CSV downloads to a temp dir,
    and clear the Cloudflare challenge on NST. The user only needs to solve it once;
    cf_clearance carries over to all subsequent requests.
    """
    download_dir = tempfile.mkdtemp()

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = uc.Chrome(options=options, headless=False)

    # Route all downloads to our temp dir (no prompt, no browser download bar)
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": download_dir
    })
    driver._nst_download_dir = download_dir

    print("   Opening Natural Stat Trick — solve the Cloudflare check if prompted (up to 60s)...")
    driver.get("https://www.naturalstattrick.com/")
    WebDriverWait(driver, 60).until(lambda d: "Just a moment" not in d.title)
    print("   Cloudflare cleared.")
    return driver


def download_nst_stats(url, driver, dataset_name):
    """
    Download stats from a single NST URL using an undetected Chrome driver.

    Args:
        url (str): NST URL
        driver: undetected_chromedriver instance (reused across calls)
        dataset_name (str): Name for logging

    Returns:
        pd.DataFrame: Player stats or empty DataFrame on failure
    """
    try:
        driver.get(url)
        # Wait for the CSV download link — only present on the real NST page
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "CSV"))
        )

        dl_dir = driver._nst_download_dir

        # Clear download dir before triggering new download
        for f in os.listdir(dl_dir):
            os.remove(os.path.join(dl_dir, f))

        # Click the CSV link directly — browser handles the download natively
        csv_element = driver.find_element(By.PARTIAL_LINK_TEXT, "CSV")
        csv_element.click()

        # Wait for the .csv file to finish downloading
        deadline = time.time() + 20
        csv_file = None
        while time.time() < deadline:
            done = [f for f in os.listdir(dl_dir)
                    if f.endswith(".csv") and not f.endswith(".crdownload")]
            if done:
                csv_file = os.path.join(dl_dir, done[0])
                break
            time.sleep(0.3)

        if not csv_file:
            raise RuntimeError("CSV download timed out")

        df = pd.read_csv(csv_file)

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
        recent_df (pd.DataFrame): Current season last 25 games stats
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
    # IMPORTANT: Use Player name + Team + Position for merge, NOT Player_ID
    # Player_ID is just NST's row number and differs across datasets
    # Using Player + Team + Position handles cases where multiple players have the same name
    if has_recent:
        # Debug: Check merge key columns exist
        merge_keys = ["Player", "Team", "Position"]
        for key in merge_keys:
            if key not in full_df.columns:
                print(f"   ⚠ WARNING: '{key}' not in full_df columns!")
            if key not in recent_df.columns:
                print(f"   ⚠ WARNING: '{key}' not in recent_df columns!")

        before_count = len(merged)
        merged = merged.merge(
            recent_df,
            on=["Player", "Team", "Position"],
            how="left",
            suffixes=("_full", "_recent")
        )
        after_count = len(merged)

        # Check how many rows got recent data
        if "TOI_recent" in merged.columns:
            matched_count = merged["TOI_recent"].notna().sum()
            print(f"   → Recent merge: {matched_count}/{before_count} players matched")
        else:
            print(f"   ⚠ WARNING: No TOI_recent column after merge!")

    # Merge last year stats if available
    # Match on Player + Position (not Team, since players may have changed teams)
    # Position helps distinguish players with the same name
    if has_last_year:
        # Only keep Player, Position and stat columns from last year
        last_year_merge_cols = ["Player", "Position"] + [c for c in last_year_df.columns
                                                  if c not in ["Player_ID", "Team", "Player", "Position", "GP", "Games Played"]]
        merged = merged.merge(
            last_year_df[last_year_merge_cols],
            on=["Player", "Position"],
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

    # Handle Player_ID (might have _full suffix if recent was merged)
    if "Player_ID_full" in merged.columns:
        weighted["Player_ID"] = merged["Player_ID_full"]
    elif "Player_ID" in merged.columns:
        weighted["Player_ID"] = merged["Player_ID"]
    else:
        # Fallback: use Player_ID from full_df
        weighted["Player_ID"] = full_df["Player_ID"]

    # Player, Team, Position were merge keys so they don't have suffixes
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

    # Position was a merge key so it doesn't have a suffix
    if "Position" in merged.columns:
        weighted["Position"] = merged["Position"]
    elif "Position_full" in merged.columns:
        weighted["Position"] = merged["Position_full"]

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
        recent_weight (float): Weight for last N games (RECENT_GAMES_TGP), uses RECENT_FORM_WEIGHT from config if None
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

    # Skip download if db was already updated today
    today = datetime.date.today()
    if os.path.exists(db_path):
        mtime = datetime.date.fromtimestamp(os.path.getmtime(db_path))
        if mtime >= today:
            print(f"Player data already up to date (db last updated: {mtime}). Skipping NST download.")
            conn = sqlite3.connect(db_path)
            df = pd.read_sql("SELECT * FROM players", conn)
            conn.close()
            return df

    print(f"Downloading live 2025-26 player stats from Natural Stat Trick...")
    print(f"   Weighting: {recent_weight:.0%} recent (L{RECENT_GAMES_TGP}) + {full_weight:.0%} full season + {last_year_weight:.0%} last year")

    driver = create_nst_driver()

    # Base URL template for easy home/away generation
    base_url_template = "https://www.naturalstattrick.com/playerteams.php?fromseason={season}&thruseason={season}&stype=2&sit=all&score=all&stdoi={stdoi}&rate=y&team=ALL&pos={pos}&loc={loc}&toi=0&gpfilt={gpfilt}&fd=&td=&tgp={tgp}&lines=single&draftteam=ALL"

    # URLs for CURRENT SEASON (2025-26) - HOME
    skaters_full_home_url = base_url_template.format(season="20252026", stdoi="oi", pos="S", loc="H", gpfilt="none", tgp="410")
    goalies_full_home_url = base_url_template.format(season="20252026", stdoi="g", pos="G", loc="H", gpfilt="none", tgp="410")
    skaters_recent_home_url = base_url_template.format(season="20252026", stdoi="oi", pos="S", loc="H", gpfilt="gpteam", tgp=RECENT_GAMES_TGP)
    goalies_recent_home_url = base_url_template.format(season="20252026", stdoi="g", pos="G", loc="H", gpfilt="gpteam", tgp=RECENT_GAMES_TGP)

    # URLs for CURRENT SEASON (2025-26) - AWAY
    skaters_full_away_url = base_url_template.format(season="20252026", stdoi="oi", pos="S", loc="A", gpfilt="none", tgp="410")
    goalies_full_away_url = base_url_template.format(season="20252026", stdoi="g", pos="G", loc="A", gpfilt="none", tgp="410")
    skaters_recent_away_url = base_url_template.format(season="20252026", stdoi="oi", pos="S", loc="A", gpfilt="gpteam", tgp=RECENT_GAMES_TGP)
    goalies_recent_away_url = base_url_template.format(season="20252026", stdoi="g", pos="G", loc="A", gpfilt="gpteam", tgp=RECENT_GAMES_TGP)

    # URLs for active roster identification
    # Skaters: last ACTIVE_ROSTER_WINDOW games — players with >=50% GP are considered active & on correct team
    # Goalies: last RECENT_GAMES_TGP games — need wider window to capture starter AND backup
    skaters_last_game_url = base_url_template.format(season="20252026", stdoi="oi", pos="S", loc="B", gpfilt="gpteam", tgp=ACTIVE_ROSTER_WINDOW)
    goalies_active_roster_url = base_url_template.format(season="20252026", stdoi="g", pos="G", loc="B", gpfilt="gpteam", tgp=RECENT_GAMES_TGP)

    # URLs for LAST YEAR (2024-25) - HOME
    skaters_lastyear_home_url = base_url_template.format(season="20242025", stdoi="oi", pos="S", loc="H", gpfilt="none", tgp="410")
    goalies_lastyear_home_url = base_url_template.format(season="20242025", stdoi="g", pos="G", loc="H", gpfilt="none", tgp="410")

    # URLs for LAST YEAR (2024-25) - AWAY
    skaters_lastyear_away_url = base_url_template.format(season="20242025", stdoi="oi", pos="S", loc="A", gpfilt="none", tgp="410")
    goalies_lastyear_away_url = base_url_template.format(season="20242025", stdoi="g", pos="G", loc="A", gpfilt="none", tgp="410")

    # Download current season HOME datasets
    print("   Downloading HOME stats...")
    skaters_full_home = download_nst_stats(skaters_full_home_url, driver, "Full season skaters HOME (2025-26)")
    goalies_full_home = download_nst_stats(goalies_full_home_url, driver, "Full season goalies HOME (2025-26)")
    skaters_recent_home = download_nst_stats(skaters_recent_home_url, driver, f"Last {RECENT_GAMES_TGP} games skaters HOME (2025-26)")
    goalies_recent_home = download_nst_stats(goalies_recent_home_url, driver, f"Last {RECENT_GAMES_TGP} games goalies HOME (2025-26)")

    # Download current season AWAY datasets
    print("   Downloading AWAY stats...")
    skaters_full_away = download_nst_stats(skaters_full_away_url, driver, "Full season skaters AWAY (2025-26)")
    goalies_full_away = download_nst_stats(goalies_full_away_url, driver, "Full season goalies AWAY (2025-26)")
    skaters_recent_away = download_nst_stats(skaters_recent_away_url, driver, f"Last {RECENT_GAMES_TGP} games skaters AWAY (2025-26)")
    goalies_recent_away = download_nst_stats(goalies_recent_away_url, driver, f"Last {RECENT_GAMES_TGP} games goalies AWAY (2025-26)")

    # Download active roster data for injury/trade filtering
    # Skaters: last game captures most of the roster
    # Goalies: last N games (RECENT_GAMES_TGP) needed to capture both starter and backup (only 1-2 goalies play per game)
    print("   Downloading active roster data (injury/trade filter)...")
    skaters_last_game = download_nst_stats(skaters_last_game_url, driver, f"Active roster skaters (L{ACTIVE_ROSTER_WINDOW}, ≥{ACTIVE_ROSTER_MIN_GP_PCT:.0%} GP)")
    goalies_active = download_nst_stats(goalies_active_roster_url, driver, f"Last {RECENT_GAMES_TGP} games goalies roster (captures backups)")

    # Download last year's datasets (if enabled)
    skaters_lastyear_home = pd.DataFrame()
    goalies_lastyear_home = pd.DataFrame()
    skaters_lastyear_away = pd.DataFrame()
    goalies_lastyear_away = pd.DataFrame()
    if last_year_weight > 0:
        print("   Downloading last year (2024-25) HOME stats...")
        skaters_lastyear_home = download_nst_stats(skaters_lastyear_home_url, driver, "Last year skaters HOME (2024-25)")
        goalies_lastyear_home = download_nst_stats(goalies_lastyear_home_url, driver, "Last year goalies HOME (2024-25)")
        print("   Downloading last year (2024-25) AWAY stats...")
        skaters_lastyear_away = download_nst_stats(skaters_lastyear_away_url, driver, "Last year skaters AWAY (2024-25)")
        goalies_lastyear_away = download_nst_stats(goalies_lastyear_away_url, driver, "Last year goalies AWAY (2024-25)")

    try:
        driver.quit()
        # Suppress undetected_chromedriver's __del__ from firing a second quit on shutdown
        driver.__class__.__del__ = lambda self: None
    except Exception:
        pass

    # Add Position='G' to goalies (they don't have position column from NST)
    if not goalies_full_home.empty:
        goalies_full_home['Position'] = 'G'
    if not goalies_full_away.empty:
        goalies_full_away['Position'] = 'G'
    if not goalies_recent_home.empty:
        goalies_recent_home['Position'] = 'G'
    if not goalies_recent_away.empty:
        goalies_recent_away['Position'] = 'G'
    if not goalies_lastyear_home.empty:
        goalies_lastyear_home['Position'] = 'G'
    if not goalies_lastyear_away.empty:
        goalies_lastyear_away['Position'] = 'G'

    # Check if we got any data
    if skaters_full_home.empty and goalies_full_home.empty:
        print("   ⚠ NST download failed completely → using league averages")
        return pd.DataFrame()

    # Use last game roster to identify active players and update team assignments for traded players
    # We DON'T filter datasets - let the natural data determine who has home/away stats
    # NOTE: We track active players by (Player, Team, Position) instead of Player_ID because
    # Player_ID is just NST's row number and differs between datasets (home vs away vs last game)
    active_players_list = []

    # Build active roster: players with >= ACTIVE_ROSTER_MIN_GP_PCT of last ACTIVE_ROSTER_WINDOW games
    # NST gpfilt=gpteam anchors to the player's CURRENT team, so traded players appear under their new
    # team once they've accumulated enough games there — no multi-team string parsing needed.
    min_active_gp = round(ACTIVE_ROSTER_WINDOW * ACTIVE_ROSTER_MIN_GP_PCT)
    current_team_map = {}

    if not skaters_last_game.empty and "Player" in skaters_last_game.columns:
        skaters_last_game["Team"] = skaters_last_game["Team"].apply(clean_team_name)

        # Find GP column
        gp_col = "GP" if "GP" in skaters_last_game.columns else \
                 "Games Played" if "Games Played" in skaters_last_game.columns else None

        if gp_col:
            gp_vals = pd.to_numeric(skaters_last_game[gp_col], errors="coerce").fillna(0)
            before = len(skaters_last_game)
            skaters_last_game = skaters_last_game[gp_vals >= min_active_gp].copy()
            print(f"   → Active roster: {len(skaters_last_game)}/{before} skaters with {min_active_gp}+ GP in last {ACTIVE_ROSTER_WINDOW} games")
        else:
            print(f"   → Active roster: {len(skaters_last_game)} skaters (no GP column found, no threshold applied)")

        current_team_map = dict(zip(skaters_last_game["Player"], skaters_last_game["Team"]))
        active_skaters = skaters_last_game[["Player", "Team", "Position"]].copy()
        active_players_list.append(active_skaters)

    def update_team(row):
        if row["Player"] in current_team_map:
            return current_team_map[row["Player"]]
        raw = str(row["Team"]) if pd.notna(row["Team"]) else ""
        if ',' in raw or '/' in raw:
            print(f"   ⚠ Could not resolve current team for {row['Player']} (NST: {raw}) — using alphabetical fallback")
        return clean_team_name(row["Team"])

    # Apply current team to all datasets
    for df in [skaters_full_home, skaters_full_away, skaters_recent_home, skaters_recent_away]:
        if not df.empty and "Player" in df.columns:
            df["Team"] = df.apply(update_team, axis=1)

    # Same for goalies - use last N games (RECENT_GAMES_TGP) to capture both starter and backup
    if not goalies_active.empty:
        goalies_active['Position'] = 'G'
        goalies_active["Team"] = goalies_active["Team"].apply(clean_team_name)
        print(f"   → Active goalies (L{RECENT_GAMES_TGP}): {len(goalies_active)} goalies")

        # Update team assignments for traded goalies
        if "Player" in goalies_active.columns:
            goalie_team_map = dict(zip(goalies_active["Player"], goalies_active["Team"]))

            def update_goalie_team(row):
                if row["Player"] in goalie_team_map:
                    return goalie_team_map[row["Player"]]
                else:
                    return clean_team_name(row["Team"])

            if not goalies_full_home.empty:
                goalies_full_home["Team"] = goalies_full_home.apply(update_goalie_team, axis=1)
            if not goalies_recent_home.empty:
                goalies_recent_home["Team"] = goalies_recent_home.apply(update_goalie_team, axis=1)
            if not goalies_full_away.empty:
                goalies_full_away["Team"] = goalies_full_away.apply(update_goalie_team, axis=1)
            if not goalies_recent_away.empty:
                goalies_recent_away["Team"] = goalies_recent_away.apply(update_goalie_team, axis=1)

        # Track active goalies using (Player, Team, Position) for reliable matching
        active_goalies = goalies_active[["Player", "Team", "Position"]].copy()
        active_players_list.append(active_goalies)
        print(f"   ✓ Identified {len(active_goalies)} active goalies from L{RECENT_GAMES_TGP} (includes backups)")

    # Merge and weight stats separately for HOME and AWAY
    print("   Merging and weighting HOME stats...")
    skaters_home_weighted = merge_and_weight_stats(
        skaters_full_home, skaters_recent_home, skaters_lastyear_home,
        recent_weight, full_weight, last_year_weight
    )
    goalies_home_weighted = merge_and_weight_stats(
        goalies_full_home, goalies_recent_home, goalies_lastyear_home,
        recent_weight, full_weight, last_year_weight
    )

    print("   Merging and weighting AWAY stats...")
    skaters_away_weighted = merge_and_weight_stats(
        skaters_full_away, skaters_recent_away, skaters_lastyear_away,
        recent_weight, full_weight, last_year_weight
    )
    goalies_away_weighted = merge_and_weight_stats(
        goalies_full_away, goalies_recent_away, goalies_lastyear_away,
        recent_weight, full_weight, last_year_weight
    )

    # Add suffixes to stat columns (not Player_ID, Player, Team, Position, GP)
    print("   Adding home/away suffixes...")

    # Identify non-stat columns to keep as-is
    keep_cols = ["Player_ID", "Player", "Team", "Position", "GP"]

    # Add _home suffix to HOME stats
    skaters_home_renamed = skaters_home_weighted.copy()
    goalies_home_renamed = goalies_home_weighted.copy()
    for col in skaters_home_weighted.columns:
        if col not in keep_cols:
            skaters_home_renamed.rename(columns={col: f"{col}_home"}, inplace=True)
    for col in goalies_home_weighted.columns:
        if col not in keep_cols:
            goalies_home_renamed.rename(columns={col: f"{col}_home"}, inplace=True)

    # Add _away suffix to AWAY stats
    skaters_away_renamed = skaters_away_weighted.copy()
    goalies_away_renamed = goalies_away_weighted.copy()
    for col in skaters_away_weighted.columns:
        if col not in keep_cols:
            skaters_away_renamed.rename(columns={col: f"{col}_away"}, inplace=True)
    for col in goalies_away_weighted.columns:
        if col not in keep_cols:
            goalies_away_renamed.rename(columns={col: f"{col}_away"}, inplace=True)

    # Merge HOME and AWAY stats on [Player, Team, Position]
    # CRITICAL: Do NOT use Player_ID - it's just a row number and differs between home/away tables
    # Using Player + Team + Position handles duplicate names (e.g., two Elias Petterssons on VAN)
    print("   Combining home and away stats...")
    merge_keys = ["Player", "Team", "Position"]

    # Check for duplicates before merge
    home_dupes = skaters_home_renamed.duplicated(subset=merge_keys, keep=False).sum()
    away_dupes = skaters_away_renamed.duplicated(subset=merge_keys, keep=False).sum()
    if home_dupes > 0:
        print(f"   ⚠ WARNING: {home_dupes} duplicate players in HOME data!")
    if away_dupes > 0:
        print(f"   ⚠ WARNING: {away_dupes} duplicate players in AWAY data!")

    skaters_combined = skaters_home_renamed.merge(
        skaters_away_renamed,
        on=merge_keys,
        how="outer",  # Keep all players (some may only have home or away games)
        suffixes=("_home_dup", "_away_dup")
    )

    goalies_combined = goalies_home_renamed.merge(
        goalies_away_renamed,
        on=merge_keys,
        how="outer",
        suffixes=("_home_dup", "_away_dup")
    )

    print(f"   → Combined: {len(skaters_home_renamed)} home + {len(skaters_away_renamed)} away = {len(skaters_combined)} total")

    # Handle Player_ID: prefer home, fallback to away
    for df in [skaters_combined, goalies_combined]:
        if "Player_ID_home_dup" in df.columns and "Player_ID_away_dup" in df.columns:
            df["Player_ID"] = df["Player_ID_home_dup"].fillna(df["Player_ID_away_dup"])
            df.drop(columns=["Player_ID_home_dup", "Player_ID_away_dup"], inplace=True)
        elif "Player_ID_home_dup" in df.columns:
            df.rename(columns={"Player_ID_home_dup": "Player_ID"}, inplace=True)
        elif "Player_ID_away_dup" in df.columns:
            df.rename(columns={"Player_ID_away_dup": "Player_ID"}, inplace=True)

    # Don't fill missing home/away data - let NaN values remain for players who truly
    # don't have stats at a given location. Team strength calculations will handle this.

    # Consolidate GP_home_dup / GP_away_dup into a single total GP column
    for df in [skaters_combined, goalies_combined]:
        if "GP_home_dup" in df.columns or "GP_away_dup" in df.columns:
            gp_home = df["GP_home_dup"].fillna(0) if "GP_home_dup" in df.columns else 0
            gp_away = df["GP_away_dup"].fillna(0) if "GP_away_dup" in df.columns else 0
            df["GP"] = gp_home + gp_away
            df.drop(columns=[c for c in ["GP_home_dup", "GP_away_dup"] if c in df.columns], inplace=True)

    # Apply GP% filter to skaters only (goalies play fewer games by design — filter separately via TOI)
    if MIN_GP_PERCENTAGE > 0 and not skaters_combined.empty and "GP" in skaters_combined.columns:
        team_max_gp = skaters_combined.groupby("Team")["GP"].transform("max")
        min_gp = team_max_gp * MIN_GP_PERCENTAGE
        before = len(skaters_combined)
        skaters_combined = skaters_combined[skaters_combined["GP"] >= min_gp].copy()
        print(f"   → GP filter ({MIN_GP_PERCENTAGE:.0%} of team games): removed {before - len(skaters_combined)} skaters, kept {len(skaters_combined)}")

    # Combine skaters and goalies
    all_players = pd.concat([skaters_combined, goalies_combined], ignore_index=True, sort=False)

    if not all_players.empty:
        conn = sqlite3.connect(db_path)
        all_players.to_sql("players", conn, if_exists="replace", index=False)

        # Store active players (from last game) in a separate table using (Player, Team, Position)
        # This allows reliable matching since Player_ID is just NST's row number and differs between datasets
        if active_players_list:
            active_roster_df = pd.concat(active_players_list, ignore_index=True)
            # Remove any duplicates (shouldn't happen, but safety check)
            active_roster_df = active_roster_df.drop_duplicates(subset=["Player", "Team", "Position"])
            active_roster_df.to_sql("active_roster", conn, if_exists="replace", index=False)
            print(f"   ✓ Saved {len(active_roster_df)} active roster players (matched by Player+Team+Position)")

        conn.close()
        print(f"   ✓ Success: {len(all_players)} weighted players saved to {db_path}")

    return all_players

def view_team_rosters(db_path, min_toi=None):
    """
    Display individual player stats organized by team with position groups.
    Shows HOME and AWAY stats separately.

    Args:
        db_path (str): Path to SQLite database
        min_toi (int, optional): Minimum TOI filter (not used with active_roster), defaults to MIN_TOI_MINUTES
    """
    from team_strength import get_team_strength

    if min_toi is None:
        min_toi = MIN_TOI_MINUTES

    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql("SELECT * FROM players", conn)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='active_roster'")
        active_roster_df = pd.read_sql("SELECT Player, Team, Position FROM active_roster", conn) \
            if cursor.fetchone() else None
        conn.close()
    except Exception as e:
        print(f"   ✗ Could not load player data: {e}")
        return

    if df.empty:
        print("   No player data available")
        return

    print("\n" + "=" * 140)
    print(f"PLAYER STATS BY TEAM - HOME/AWAY SPLITS (70% xG + 30% Actual Goals, 55% Recent L{RECENT_GAMES_TGP} + 30% Full Season + 15% Last Year)")
    print("=" * 140)

    for team in sorted(df["Team"].unique()):
        team_players = df[df["Team"] == team].copy()

        if active_roster_df is not None:
            team_players = team_players.merge(
                active_roster_df, on=["Player", "Team", "Position"], how="inner"
            )

        if team_players.empty:
            continue

        # Display HOME stats
        print(f"\n{'='*140}")
        print(f"{team} — HOME STATS")
        print('='*140)
        display_location_stats(team, team_players, "home", db_path)

        # Display AWAY stats
        print(f"\n{team} — AWAY STATS")
        print('-'*140)
        display_location_stats(team, team_players, "away", db_path)
        print()  # Extra spacing between teams


def display_location_stats(team, team_players, location, db_path):
    """
    Helper function to display stats for a specific location (home or away).

    Args:
        team (str): Team name
        team_players (pd.DataFrame): DataFrame of all team players
        location (str): "home" or "away"
        db_path (str): Database path
    """
    from team_strength import get_team_strength
    from config import XG_WEIGHT, ACTUAL_GOALS_WEIGHT

    # Get team strength for this location
    team_offense, team_defense = get_team_strength(team, db_path, location)

    print(f"TEAM STRENGTH (Position-Weighted {location.upper()}):")
    print(f"  Offensive Rating: {team_offense:.2f} xGF/60")
    print(f"  Defensive Rating: {team_defense:.2f} xGA/60")
    print()

    # Build column names with location suffix
    toi_col = f"TOI_{location}"
    xgf_col = f"xGF/60_{location}"
    gf_col = f"GF/60_{location}"
    xga_col = f"xGA/60_{location}"
    ga_col = f"GA/60_{location}"
    xga_goalie_col = f"xG Against/60_{location}"
    gaa_col = f"GAA_{location}"

    # Split by position
    forwards = team_players[team_players['Position'].isin(['C', 'L', 'R'])].copy() if 'Position' in team_players.columns else pd.DataFrame()
    defensemen = team_players[team_players['Position'] == 'D'].copy() if 'Position' in team_players.columns else pd.DataFrame()
    goalies = team_players[team_players['Position'] == 'G'].copy() if 'Position' in team_players.columns else pd.DataFrame()

    # Calculate contributions if we have the required columns
    if not team_players.empty and xgf_col in team_players.columns and xga_col in team_players.columns and toi_col in team_players.columns:
        total_toi = team_players[toi_col].sum()

        # Calculate weighted values for ALL players first (for accurate team averages)
        if gf_col in team_players.columns and ga_col in team_players.columns:
            team_players['Weighted xGF/60'] = (team_players[xgf_col] * XG_WEIGHT + team_players[gf_col] * ACTUAL_GOALS_WEIGHT)
            team_players['Weighted xGA/60'] = (team_players[xga_col] * XG_WEIGHT + team_players[ga_col] * ACTUAL_GOALS_WEIGHT)

        # Forwards
        if not forwards.empty and gf_col in forwards.columns and ga_col in forwards.columns:
            # Calculate weighted (blended) values
            forwards['Weighted xGF/60'] = (forwards[xgf_col] * XG_WEIGHT + forwards[gf_col] * ACTUAL_GOALS_WEIGHT).round(2)
            forwards['Weighted xGA/60'] = (forwards[xga_col] * XG_WEIGHT + forwards[ga_col] * ACTUAL_GOALS_WEIGHT).round(2)

            # Use weighted values for contribution calculations
            forward_avg_weighted_xgf = forwards['Weighted xGF/60'].mean()
            team_avg_weighted_xga = team_players['Weighted xGA/60'].mean()

            forwards['Off_Contrib'] = ((forwards['Weighted xGF/60'] - forward_avg_weighted_xgf) * (forwards[toi_col] / total_toi) * 0.85).round(2)
            forwards['Def_Contrib'] = ((team_avg_weighted_xga - forwards['Weighted xGA/60']) * (forwards[toi_col] / total_toi) * 0.20).round(2)
            forwards = forwards.sort_values('Off_Contrib', ascending=False)

        # Defensemen
        if not defensemen.empty and gf_col in defensemen.columns and ga_col in defensemen.columns:
            # Calculate weighted (blended) values
            defensemen['Weighted xGF/60'] = (defensemen[xgf_col] * XG_WEIGHT + defensemen[gf_col] * ACTUAL_GOALS_WEIGHT).round(2)
            defensemen['Weighted xGA/60'] = (defensemen[xga_col] * XG_WEIGHT + defensemen[ga_col] * ACTUAL_GOALS_WEIGHT).round(2)

            # Use weighted values for contribution calculations
            defense_avg_weighted_xgf = defensemen['Weighted xGF/60'].mean()
            team_avg_weighted_xga = team_players['Weighted xGA/60'].mean()

            defensemen['Off_Contrib'] = ((defensemen['Weighted xGF/60'] - defense_avg_weighted_xgf) * (defensemen[toi_col] / total_toi) * 0.15).round(2)
            defensemen['Def_Contrib'] = ((team_avg_weighted_xga - defensemen['Weighted xGA/60']) * (defensemen[toi_col] / total_toi) * 0.30).round(2)
            defensemen = defensemen.sort_values('Def_Contrib', ascending=False)

        # Goalies - use goalie-specific xG Against/60 stat
        if not goalies.empty and xga_goalie_col in goalies.columns and gaa_col in goalies.columns:
            # Calculate weighted (blended) value
            goalies['Weighted xGA/60'] = (goalies[xga_goalie_col] * XG_WEIGHT + goalies[gaa_col] * ACTUAL_GOALS_WEIGHT).round(2)

            # Use weighted values for contribution calculations
            goalie_avg_weighted_xga = goalies['Weighted xGA/60'].mean()

            goalies['Off_Contrib'] = 0.0
            goalies['Def_Contrib'] = ((goalie_avg_weighted_xga - goalies['Weighted xGA/60']) * (goalies[toi_col] / total_toi) * 0.50).round(2)
            goalies = goalies.sort_values('Def_Contrib', ascending=False)

    # Display columns - need to check each position dataframe for available columns
    # Include both expected (xG), actual (G), and weighted (blended) stats
    base_cols = ['Player_ID', 'Player', 'Position', toi_col, xgf_col, gf_col, xga_col, ga_col, 'Weighted xGF/60', 'Weighted xGA/60']
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
        goalie_base_cols = ['Player_ID', 'Player', 'Position', toi_col, xga_goalie_col, gaa_col, 'Weighted xGA/60']
        goalies_display_cols = [c for c in goalie_base_cols + contrib_cols if c in goalies.columns]
        goalies_display = goalies[goalies_display_cols].copy()
        for col in goalies_display.columns:
            if col not in ['Player_ID', 'Player', 'Position'] and pd.api.types.is_numeric_dtype(goalies_display[col]):
                goalies_display[col] = goalies_display[col].round(2)
        print(goalies_display.to_string(index=False))
        print()