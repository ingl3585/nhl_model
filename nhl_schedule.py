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
    "TOR": "Toronto Maple Leafs", "UTA": "Utah Hockey Club",
    "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights",
    "WSH": "Washington Capitals", "WPG": "Winnipeg Jets",
}

# Reverse mapping: full name → code
NAME_TO_CODE = {v: k for k, v in TEAM_MAP.items()}

# NST dotted versions → clean code
NST_DOTS = {"L.A": "LAK", "N.J": "NJD", "S.J": "SJS", "T.B": "TBL"}


def scrape_schedule(output_path=None):
    url = f"https://www.hockey-reference.com/leagues/NHL_{SEASON_CODE}_games.html"
    print(f"Scraping {CURRENT_SEASON_FULL} schedule from Hockey-Reference...")

    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    
    # Robust table finder with fallbacks
    table = soup.find("table", {"id": "schedule"})
    if not table:
        table = soup.find("table", class_="stats_table")
    if not table:
        # Fallback: Grab the largest table (schedules have 100+ rows)
        tables = soup.find_all("table")
        table = next((t for t in tables if len(t.find_all("tr")) > 50), None)
        if table:
            print("   Debug: Using fallback table (largest one found).")
    if not table:
        raise RuntimeError("Schedule table not found — page may be loading dynamically or layout changed.")

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

        # Clean, reliable mapping — no more Columbus bugs!
        visitor_code = NAME_TO_CODE.get(raw_visitor, raw_visitor[:3].upper())
        home_code = NAME_TO_CODE.get(raw_home, raw_home[:3].upper())

        visitor = TEAM_MAP[visitor_code]
        home = TEAM_MAP[home_code]

        vg = int(cells[3].get_text(strip=True) or 0)
        hg = int(cells[5].get_text(strip=True) or 0)
        ot = cells[6].get_text(strip=True)
        ot = ot if ot in ["OT", "SO"] else ""
        played = vg > 0 and hg > 0

        games.append({
            "date": date_str,
            "visitor": visitor,
            "home": home,
            "visitor_code": visitor_code,
            "home_code": home_code,
            "vg": vg, "hg": hg, "ot": ot, "played": played
        })

    df = pd.DataFrame(games).sort_values("date").reset_index(drop=True)

    if output_path:
        df.to_csv(output_path, index=False)
        print(f"   Success: {len(df)} games scraped ({df['played'].sum()} played)")

    return df


def get_todays_games(schedule_df, today_str):
    """
    Get today's games from the full schedule.
    """
    today_games = schedule_df[schedule_df["date"] == today_str].copy()

    if today_games.empty:
        print(f"   No games scheduled for {today_str}")
        return today_games

    return today_games