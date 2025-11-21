# nhl_schedule.py
# Schedule scraping from Hockey-Reference

import pandas as pd
import requests
from bs4 import BeautifulSoup
from config import SEASON_CODE, CURRENT_SEASON_FULL

# Team mappings
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


def scrape_schedule(output_path=None):
    """
    Scrape NHL schedule from Hockey-Reference.

    Args:
        output_path (str, optional): Path to save CSV. If None, doesn't save.

    Returns:
        pd.DataFrame: Schedule with columns: date, visitor, home, vg, hg, ot, played
    """
    url = f"https://www.hockey-reference.com/leagues/NHL_{SEASON_CODE}_games.html"
    print(f"Scraping {CURRENT_SEASON_FULL} schedule from Hockey-Reference...")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=30)

    if r.status_code != 200:
        raise Exception(f"Failed to load schedule: HTTP {r.status_code}")

    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", {"id": "schedule"}) or soup.find("table", class_="stats_table")

    if not table:
        raise Exception("Schedule table not found — Hockey-Reference layout changed")

    games = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["th", "td"])
        if len(cells) < 8:
            continue

        date_cell = cells[0].get_text(strip=True)
        if not date_cell or "-" not in date_cell:
            continue
        date_str = date_cell[:10]

        visitor = cells[2].get_text(strip=True)
        home = cells[4].get_text(strip=True)
        vg = int(cells[3].get_text(strip=True) or 0)
        hg = int(cells[5].get_text(strip=True) or 0)
        ot = cells[6].get_text(strip=True)
        ot = ot if ot in ["OT", "SO"] else ""
        played = vg > 0 and hg > 0

        visitor = TEAM_MAP.get(visitor[:3].upper(), visitor)
        home = TEAM_MAP.get(home[:3].upper(), home)

        games.append({
            "date": date_str,
            "visitor": visitor,
            "home": home,
            "vg": vg,
            "hg": hg,
            "ot": ot,
            "played": played
        })

    df = pd.DataFrame(games).sort_values("date").reset_index(drop=True)

    if output_path:
        df.to_csv(output_path, index=False)
        print(f"   Success: {len(df)} games scraped ({df['played'].sum()} played)")

    return df


def get_todays_games(schedule_df, today_str):
    """
    Filter schedule for today's games.

    Args:
        schedule_df (pd.DataFrame): Full schedule
        today_str (str): Date string in YYYY-MM-DD format

    Returns:
        pd.DataFrame: Today's games
    """
    return schedule_df[schedule_df["date"] == today_str]
