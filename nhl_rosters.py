# nhl_rosters.py
# Player roster and stats scraping from Natural Stat Trick

import pandas as pd
import numpy as np
import sqlite3
import requests
from bs4 import BeautifulSoup
from io import StringIO
from config import TEAM_ABBREV_FIXES

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
    "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club",
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


def download_nst_data(db_path):
    """
    Download live player stats from Natural Stat Trick and save to SQLite.

    Args:
        db_path (str): Path to SQLite database file

    Returns:
        pd.DataFrame: All players data (skaters + goalies)
    """
    print("Downloading live 2025-26 player stats from Natural Stat Trick...")

    skaters_url = "https://www.naturalstattrick.com/playerteams.php?fromseason=20252026&thruseason=20252026&stype=2&sit=5v5&score=all&stdoi=oi&rate=n&team=ALL&pos=S&loc=B&toi=0&gpfilt=none&fd=&td=&tgp=410&lines=single&draftteam=ALL"
    goalies_url = skaters_url.replace("&pos=S", "&pos=G")
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        # Skaters
        r = requests.get(skaters_url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        csv_link = soup.find("a", string=lambda t: t and "CSV" in t)

        if csv_link:
            skaters = pd.read_csv("https://www.naturalstattrick.com" + csv_link["href"])
        else:
            skaters = pd.read_html(StringIO(r.text))[0]

        # Goalies
        r = requests.get(goalies_url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        csv_link = soup.find("a", string=lambda t: t and "CSV" in t)

        if csv_link:
            goalies = pd.read_csv("https://www.naturalstattrick.com" + csv_link["href"])
        else:
            goalies = pd.read_html(StringIO(r.text))[0]

        print(f"   Success: {len(skaters)} skaters + {len(goalies)} goalies loaded")

    except Exception as e:
        print(f"   NST download failed ({e}) → using league averages")
        skaters = goalies = pd.DataFrame()

    # Clean team names
    if not skaters.empty:
        skaters["Team"] = skaters["Team"].apply(clean_team_name)
    if not goalies.empty:
        goalies["Team"] = goalies["Team"].apply(clean_team_name)

    # Combine and save
    all_players = pd.concat([skaters, goalies], ignore_index=True, sort=False)

    if not all_players.empty:
        conn = sqlite3.connect(db_path)
        all_players.to_sql("players", conn, if_exists="replace", index=False)
        conn.close()
        print(f"   Success: {len(all_players)} players saved to {db_path}")

    return all_players
