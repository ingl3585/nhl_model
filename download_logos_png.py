# download_logos_png.py
# Script to download NHL team logos in PNG format (Windows-friendly, no cairosvg needed)

import requests
from pathlib import Path
from season_simulation import DIVISIONS

# Create logos directory
LOGO_DIR = Path("data/logos")
LOGO_DIR.mkdir(parents=True, exist_ok=True)

# NHL team abbreviations mapping
TEAM_ABBREVS = {
    # Atlantic Division
    "Boston Bruins": "BOS",
    "Buffalo Sabres": "BUF",
    "Detroit Red Wings": "DET",
    "Florida Panthers": "FLA",
    "Montreal Canadiens": "MTL",
    "Ottawa Senators": "OTT",
    "Tampa Bay Lightning": "TBL",
    "Toronto Maple Leafs": "TOR",

    # Metropolitan Division
    "Carolina Hurricanes": "CAR",
    "Columbus Blue Jackets": "CBJ",
    "New Jersey Devils": "NJD",
    "New York Islanders": "NYI",
    "New York Rangers": "NYR",
    "Philadelphia Flyers": "PHI",
    "Pittsburgh Penguins": "PIT",
    "Washington Capitals": "WSH",

    # Central Division
    "Chicago Blackhawks": "CHI",
    "Colorado Avalanche": "COL",
    "Dallas Stars": "DAL",
    "Minnesota Wild": "MIN",
    "Nashville Predators": "NSH",
    "St. Louis Blues": "STL",
    "Utah Mammoth": "UTA",
    "Winnipeg Jets": "WPG",

    # Pacific Division
    "Anaheim Ducks": "ANA",
    "Calgary Flames": "CGY",
    "Edmonton Oilers": "EDM",
    "Los Angeles Kings": "LAK",
    "San Jose Sharks": "SJS",
    "Seattle Kraken": "SEA",
    "Vancouver Canucks": "VAN",
    "Vegas Golden Knights": "VGK"
}

# NHL team IDs for API (used in NHL.com URLs)
TEAM_IDS = {
    "BOS": 6, "BUF": 7, "DET": 17, "FLA": 13, "MTL": 8, "OTT": 9, "TBL": 14, "TOR": 10,
    "CAR": 12, "CBJ": 29, "NJD": 1, "NYI": 2, "NYR": 3, "PHI": 4, "PIT": 5, "WSH": 15,
    "CHI": 16, "COL": 21, "DAL": 25, "MIN": 30, "NSH": 18, "STL": 19, "UTA": 59, "WPG": 52,
    "ANA": 24, "CGY": 20, "EDM": 22, "LAK": 26, "SJS": 28, "SEA": 55, "VAN": 23, "VGK": 54
}

def download_logos_png():
    """Download NHL team logos in PNG format from ESPN CDN."""
    print("Downloading NHL team logos (PNG format)...")

    all_teams = (DIVISIONS["Atlantic"] + DIVISIONS["Metropolitan"] +
                 DIVISIONS["Central"] + DIVISIONS["Pacific"])

    success_count = 0
    for team in all_teams:
        abbrev = TEAM_ABBREVS.get(team)
        if not abbrev:
            print(f"  ⚠️  No abbreviation found for {team}")
            continue

        png_path = LOGO_DIR / f"{abbrev}.png"

        # ESPN uses different abbreviations for some teams
        espn_abbrev_map = {
            "TBL": "TB",   # Tampa Bay Lightning
            "LAK": "LA",   # Los Angeles Kings
            "SJS": "SJ",   # San Jose Sharks
        }
        espn_abbrev = espn_abbrev_map.get(abbrev, abbrev)

        # Try multiple sources for PNG logos
        sources = [
            # ESPN CDN (500x500 PNG) - try ESPN abbreviation
            f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/{espn_abbrev}.png",
            # ESPN CDN - try our abbreviation as fallback
            f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/{abbrev}.png",
            # NHL Stats API (older but reliable)
            f"https://www-league.nhlstatic.com/images/logos/teams-current-primary-light/{TEAM_IDS.get(abbrev, 0)}.svg",
        ]

        downloaded = False
        for idx, logo_url in enumerate(sources):
            try:
                response = requests.get(logo_url, timeout=10)
                if response.status_code == 200 and len(response.content) > 1000:  # Valid image
                    # Save the file
                    with open(png_path, 'wb') as f:
                        f.write(response.content)

                    source_name = "ESPN" if idx == 0 else "NHL API"
                    print(f"  ✓ Downloaded {abbrev} ({team}) from {source_name}")
                    success_count += 1
                    downloaded = True
                    break
            except Exception as e:
                continue

        if not downloaded:
            print(f"  ✗ Failed to download {abbrev} ({team})")

    print(f"\n✓ Downloaded {success_count}/{len(all_teams)} team logos")
    print(f"Logos saved to: {LOGO_DIR.absolute()}")

if __name__ == "__main__":
    download_logos_png()
