# nhl_schedule.py
import pandas as pd
import requests
from bs4 import BeautifulSoup
from config import SEASON_CODE, CURRENT_SEASON_FULL

# Forward mapping: code → full name
TEAM_MAP = {
    "ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres",
    "CGY": "Calgary Flames", "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks",
    "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets", "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings",
    "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens", "NSH": "Nashville Predators",
    "NJD": "New Jersey Devils",
    "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins",
    "SJS": "San Jose Sharks",
    "SEA": "Seattle Kraken", "STL": "St. Louis Blues",
    "TBL": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs", "UTA": "Utah Mammoth",
    "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights",
    "WSH": "Washington Capitals", "WPG": "Winnipeg Jets",
}

# Reverse mapping: full name → code
NAME_TO_CODE = {v: k for k, v in TEAM_MAP.items()}

# NST dotted versions → clean code
NST_DOTS = {"L.A": "LAK", "N.J": "NJD", "S.J": "SJS", "T.B": "TBL"}


def _parse_games_table(table):
    """Parse a Hockey-Reference schedule table into a list of game dicts."""
    games = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["th", "td"])
        if len(cells) < 8:
            continue

        date_cell = cells[0].get_text(strip=True)
        if not date_cell or "-" not in date_cell:
            continue
        date_str = date_cell[:10]

        raw_visitor = cells[2].get_text(strip=True)
        raw_home = cells[4].get_text(strip=True)

        visitor_code = NAME_TO_CODE.get(raw_visitor, raw_visitor[:3].upper())
        home_code = NAME_TO_CODE.get(raw_home, raw_home[:3].upper())

        visitor = TEAM_MAP[visitor_code]
        home = TEAM_MAP[home_code]

        vg_text = cells[3].get_text(strip=True)
        hg_text = cells[5].get_text(strip=True)
        vg = int(vg_text or 0)
        hg = int(hg_text or 0)
        ot = cells[6].get_text(strip=True)
        ot = ot if ot in ["OT", "SO"] else ""
        played = bool(vg_text) and bool(hg_text)

        games.append({
            "date": date_str,
            "visitor": visitor,
            "home": home,
            "visitor_code": visitor_code,
            "home_code": home_code,
            "vg": vg, "hg": hg, "ot": ot, "played": played
        })
    return games


def scrape_schedule(output_path=None):
    """
    Scrape both regular season and playoff tables from Hockey-Reference.

    Returns:
        tuple: (regular_df, playoff_df). playoff_df is empty if playoffs haven't started.
    """
    url = f"https://www.hockey-reference.com/leagues/NHL_{SEASON_CODE}_games.html"
    print(f"Scraping {CURRENT_SEASON_FULL} schedule from Hockey-Reference...")

    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    regular_table = soup.find("table", {"id": "games"})
    if not regular_table:
        # Fallbacks for unexpected layout changes
        regular_table = soup.find("table", {"id": "schedule"})
    if not regular_table:
        tables = soup.find_all("table")
        regular_table = next((t for t in tables if len(t.find_all("tr")) > 50), None)
        if regular_table:
            print("   Debug: Using fallback table (largest one found).")
    if not regular_table:
        raise RuntimeError("Schedule table not found — page may be loading dynamically or layout changed.")

    regular_df = pd.DataFrame(_parse_games_table(regular_table)).sort_values("date").reset_index(drop=True)

    playoff_table = soup.find("table", {"id": "games_playoffs"})
    if playoff_table:
        playoff_df = pd.DataFrame(_parse_games_table(playoff_table)).sort_values("date").reset_index(drop=True)
        print(f"   Success: {len(regular_df)} regular-season games ({regular_df['played'].sum()} played)")
        print(f"   Playoffs detected: {len(playoff_df)} games ({playoff_df['played'].sum()} played)")
    else:
        playoff_df = pd.DataFrame(columns=regular_df.columns)
        print(f"   Success: {len(regular_df)} regular-season games ({regular_df['played'].sum()} played)")

    if output_path:
        regular_df.to_csv(output_path, index=False)

    return regular_df, playoff_df


def get_todays_games(schedule_df, today_str):
    """
    Get today's games from the full schedule.
    """
    today_games = schedule_df[schedule_df["date"] == today_str].copy()

    if today_games.empty:
        print(f"   No games scheduled for {today_str}")
        return today_games

    return today_games