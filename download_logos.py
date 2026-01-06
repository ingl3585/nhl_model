# download_logos.py
# Script to download NHL team logos

import requests
from pathlib import Path
from season_simulation import DIVISIONS
try:
    import cairosvg
    from PIL import Image
    import io
    HAS_CONVERSION = True
except ImportError:
    HAS_CONVERSION = False
    print("Warning: cairosvg or Pillow not installed. Run: pip install cairosvg Pillow")

# Create logos directory
LOGO_DIR = Path("data/logos")
LOGO_DIR.mkdir(parents=True, exist_ok=True)

# NHL team abbreviations mapping (for logo URLs)
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
    "Utah Mammoth": "UTA",  # Utah Hockey Club
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

def svg_to_png(svg_path, png_path, size=200):
    """Convert SVG to PNG."""
    if not HAS_CONVERSION:
        return False

    try:
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path),
                        output_width=size, output_height=size)
        return True
    except Exception as e:
        print(f"  ⚠️  Error converting {svg_path.name} to PNG: {e}")
        return False


def download_logos():
    """Download NHL team logos from NHL.com and convert to PNG."""
    print("Downloading NHL team logos...")

    all_teams = (DIVISIONS["Atlantic"] + DIVISIONS["Metropolitan"] +
                 DIVISIONS["Central"] + DIVISIONS["Pacific"])

    success_count = 0
    for team in all_teams:
        abbrev = TEAM_ABBREVS.get(team)
        if not abbrev:
            print(f"  ⚠️  No abbreviation found for {team}")
            continue

        # Try NHL.com logo URL (dark background version)
        logo_url = f"https://assets.nhle.com/logos/nhl/svg/{abbrev}_dark.svg"
        svg_path = LOGO_DIR / f"{abbrev}.svg"
        png_path = LOGO_DIR / f"{abbrev}.png"

        # Try downloading
        try:
            response = requests.get(logo_url, timeout=10)
            if response.status_code == 200:
                # Save SVG
                with open(svg_path, 'wb') as f:
                    f.write(response.content)

                # Convert to PNG
                if HAS_CONVERSION and svg_to_png(svg_path, png_path, size=200):
                    print(f"  ✓ Downloaded & converted {abbrev} ({team})")
                    success_count += 1
                else:
                    print(f"  ✓ Downloaded {abbrev} SVG ({team}) - PNG conversion skipped")
                    success_count += 1
            else:
                # Try alternate URL format
                alt_url = f"https://assets.nhle.com/logos/nhl/svg/{abbrev}.svg"
                response = requests.get(alt_url, timeout=10)
                if response.status_code == 200:
                    with open(svg_path, 'wb') as f:
                        f.write(response.content)

                    if HAS_CONVERSION and svg_to_png(svg_path, png_path, size=200):
                        print(f"  ✓ Downloaded & converted {abbrev} ({team}) [alt URL]")
                        success_count += 1
                    else:
                        print(f"  ✓ Downloaded {abbrev} SVG ({team}) [alt URL] - PNG conversion skipped")
                        success_count += 1
                else:
                    print(f"  ✗ Failed to download {abbrev} ({team})")
        except Exception as e:
            print(f"  ✗ Error downloading {abbrev}: {e}")

    print(f"\n✓ Downloaded {success_count}/{len(all_teams)} team logos")
    print(f"Logos saved to: {LOGO_DIR.absolute()}")
    if HAS_CONVERSION:
        print("✓ SVG logos converted to PNG for use in charts")

if __name__ == "__main__":
    download_logos()
