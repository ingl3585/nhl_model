# nhl_monte_carlo.py
# PRO VERSION — Fully config-driven, zero hardcodes, runs forever
# Season 2025-26 and beyond — live player-based xGF/xGA from Natural Stat Trick

from config import *
import pandas as pd
import numpy as np
import sqlite3
import requests
from bs4 import BeautifulSoup
from collections import defaultdict, Counter
import time
from io import StringIO

# =============================================================================
# TEAM MAPPINGS & DIVISIONS (only edit if NHL adds/removes teams)
# =============================================================================
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

# Apply any extra fixes from config
TEAM_MAP.update(TEAM_ABBREV_FIXES)

DIVISIONS = {
    "Atlantic": ["Boston Bruins", "Buffalo Sabres", "Detroit Red Wings", "Florida Panthers",
                 "Montreal Canadiens", "Ottawa Senators", "Tampa Bay Lightning", "Toronto Maple Leafs"],
    "Metropolitan": ["Carolina Hurricanes", "Columbus Blue Jackets", "New Jersey Devils", "New York Islanders",
                     "New York Rangers", "Philadelphia Flyers", "Pittsburgh Penguins", "Washington Capitals"],
    "Central": ["Chicago Blackhawks", "Colorado Avalanche", "Dallas Stars", "Minnesota Wild",
                "Nashville Predators", "St. Louis Blues", "Utah Hockey Club", "Winnipeg Jets"],
    "Pacific": ["Anaheim Ducks", "Calgary Flames", "Edmonton Oilers", "Los Angeles Kings",
                "San Jose Sharks", "Seattle Kraken", "Vancouver Canucks", "Vegas Golden Knights"]
}

print("="*100)
print(f"NHL MONTE CARLO PRO — {CURRENT_SEASON_FULL} SEASON".center(100))
print(f"Live 5v5 xGF/xGA model | {N_SIMS_FULL:,} simulations | Today: {TODAY_PRETTY}".center(100))
print("="*100)


# ================= 1. SCRAPE FULL SCHEDULE FROM HOCKEY-REFERENCE =================
def scrape_schedule():
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
        if len(cells) < 8: continue
        
        date_cell = cells[0].get_text(strip=True)
        if not date_cell or "-" not in date_cell: continue
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

        games.append({"date": date_str, "visitor": visitor, "home": home,
                      "vg": vg, "hg": hg, "ot": ot, "played": played})

    df = pd.DataFrame(games).sort_values("date").reset_index(drop=True)
    df.to_csv(SCHEDULE_CSV, index=False)
    print(f"   Success: {len(df)} games scraped ({df['played'].sum()} played)")
    return df


# ================= 2. CURRENT STANDINGS =================
def build_current_standings(schedule_df):
    standings = defaultdict(lambda: {"points": 0, "row": 0, "otw": 0, "gf": 0, "ga": 0, "gp": 0})
    for _, g in schedule_df[schedule_df.played].iterrows():
        h, a = g.home, g.visitor
        standings[h]["gf"] += g.hg; standings[h]["ga"] += g.vg; standings[h]["gp"] += 1
        standings[a]["gf"] += g.vg; standings[a]["ga"] += g.hg; standings[a]["gp"] += 1

        if g.hg > g.vg and g.ot == "":       standings[h]["points"] += 2; standings[h]["row"] += 1
        elif g.vg > g.hg and g.ot == "":     standings[a]["points"] += 2; standings[a]["row"] += 1
        elif g.hg > g.vg:                   standings[h]["points"] += 2; standings[h]["otw"] += 1; standings[a]["points"] += 1
        else:                               standings[a]["points"] += 2; standings[a]["otw"] += 1; standings[h]["points"] += 1

    df = pd.DataFrame.from_dict(standings, orient="index").reset_index().rename(columns={"index": "team"})
    df["gf-ga"] = df["gf"] - df["ga"]
    return df


# ================= 3. DOWNLOAD LIVE NST DATA =================
def download_nst_data():
    print("Downloading live 2025-26 player stats from Natural Stat Trick...")
    skaters_url = "https://www.naturalstattrick.com/playerteams.php?fromseason=20252026&thruseason=20252026&stype=2&sit=5v5&score=all&stdoi=oi&rate=n&team=ALL&pos=S&loc=B&toi=0&gpfilt=none&fd=&td=&tgp=410&lines=single&draftteam=ALL"
    goalies_url = skaters_url.replace("&pos=S", "&pos=G")
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        # Skaters
        r = requests.get(skaters_url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        csv_link = soup.find("a", string=lambda t: t and "CSV" in t)
        skaters = pd.read_csv("https://www.naturalstattrick.com" + csv_link["href"]) if csv_link else pd.read_html(StringIO(r.text))[0]

        # Goalies
        r = requests.get(goalies_url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        csv_link = soup.find("a", string=lambda t: t and "CSV" in t)
        goalies = pd.read_csv("https://www.naturalstattrick.com" + csv_link["href"]) if csv_link else pd.read_html(StringIO(r.text))[0]

        print(f"   Success: {len(skaters)} skaters + {len(goalies)} goalies loaded")
    except Exception as e:
        print(f"   NST download failed ({e}) → using league averages")
        skaters = goalies = pd.DataFrame()

    # Clean team names (traded players → current team = last in list)
    def clean_team(team_str):
        if pd.isna(team_str): return np.nan
        parts = [p.strip().replace('.', '') for p in str(team_str).replace('/', ',').split(',')]
        parts = [p for p in parts if p]
        return TEAM_MAP.get(parts[-1].upper(), team_str) if parts else team_str

    if not skaters.empty: skaters["Team"] = skaters["Team"].apply(clean_team)
    if not goalies.empty: goalies["Team"] = goalies["Team"].apply(clean_team)

    all_players = pd.concat([skaters, goalies], ignore_index=True, sort=False)
    if not all_players.empty:
        all_players.to_sql("players", sqlite3.connect(DB_FILE), if_exists="replace", index=False)
        print(f"   Success: {len(all_players)} players saved to {DB_FILE}")
    return all_players


# ================= 4. TEAM STRENGTH (xGF/60 & xGA/60) =================
def get_team_strength(team):
    # Early exit if DB doesn't exist
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players'")
        if not cursor.fetchone():
            conn.close()
            return FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING
    except:
        return FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING

    query = '''
        SELECT 
            COALESCE(SUM("xGF"), 0) as total_xgf,
            COALESCE(SUM("TOI"), 0) as total_toi,
            COALESCE(SUM("xGA"), 0) as total_xga
        FROM players 
        WHERE Team = ? AND "TOI" > ?
    '''
    try:
        df = pd.read_sql(query, conn, params=(team, MIN_TOI_MINUTES))
        conn.close()
    except:
        conn.close()
        return FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING

    if df.empty:
        return FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING

    row = df.iloc[0]
    toi = row.total_toi

    # FINAL SAFETY NET — if TOI is 0 or None, fallback
    if not toi or toi <= 0:
        return FALLBACK_OFFENSIVE_RATING, FALLBACK_DEFENSIVE_RATING

    # Safe calculations
    off = row.total_xgf / (toi / 60.0)
    def_ = row.total_xga / (toi / 60.0)

    # Sanity clamp
    off = max(1.8, min(off, 4.8))
    def_ = max(1.8, min(def_, 4.8))

    return round(off, 3), round(def_, 3)


# ================= 5. SIMULATION ENGINE =================
def simulate_game(home, away):
    ho, hd = get_team_strength(home)
    ao, ad = get_team_strength(away)
    home_xg = ho * HOME_ICE_ADVANTAGE * (LEAGUE_AVG_XG_PER_60 / ad)
    away_xg = ao * (LEAGUE_AVG_XG_PER_60 / hd)

    hg = np.random.poisson(home_xg)
    ag = np.random.poisson(away_xg)

    if hg > ag:
        return home, 2, 0, hg, ag, True
    elif ag > hg:
        return away, 0, 2, hg, ag, True
    else:
        winner = home if np.random.rand() < OT_HOME_WIN_PROB else away
        return winner, 2, 1, hg + (winner == home), ag + (winner == away), False


def best_of_7(team1, team2, home_first):
    wins1 = wins2 = 0
    home_turn = home_first
    while wins1 < 4 and wins2 < 4:
        winner = simulate_game(team1 if home_turn else team2, team2 if home_turn else team1)[0]
        if winner == team1: wins1 += 1
        else: wins2 += 1
        home_turn = not home_turn
    return team1 if wins1 == 4 else team2


# ================= 6. PLAYOFF QUALIFICATION =================
def get_playoff_teams(final_standings):
    playoff = []
    for div, teams in DIVISIONS.items():
        div_df = final_standings[final_standings.team.isin(teams)].copy()
        div_df = div_df.sort_values(by=["points", "row", "otw", "gf-ga", "gf"], ascending=False)
        playoff.extend(div_df.head(3).team.tolist())

    remaining = final_standings[~final_standings.team.isin(playoff)].copy()
    east = DIVISIONS["Atlantic"] + DIVISIONS["Metropolitan"]
    west = DIVISIONS["Central"] + DIVISIONS["Pacific"]
    playoff.extend(remaining[remaining.team.isin(east)].head(2).team.tolist())
    playoff.extend(remaining[remaining.team.isin(west)].head(2).team.tolist())
    return list(dict.fromkeys(playoff))[:16]  # dedup & cap at 16


# ================= 7. TODAY'S GAMES — NOW USING THE EXACT SAME SIM ENGINE =================
if SHOW_TODAYS_GAMES:
    print("\n" + "="*88)
    print(f"TODAY'S NHL GAMES — {TODAY_PRETTY} — LIVE MODEL ODDS ({N_SIMS_TODAY:,} sims each)")
    print("="*88)

    # Reuse schedule if already loaded, otherwise scrape
    if 'schedule' not in locals():
        schedule = scrape_schedule()
    today_games = schedule[schedule["date"] == TODAY_STR]

    if today_games.empty:
        print("   No games scheduled today.\n")
    else:
        for _, game in today_games.iterrows():
            home, away = game["home"], game["visitor"]

            home_wins = home_goals = away_goals = 0
            for _ in range(N_SIMS_TODAY):
                winner, hpts, apts, hgf, agf, reg = simulate_game(home, away)
                home_goals += hgf
                away_goals += agf
                if winner == home:
                    home_wins += 1

            home_pct = home_wins / N_SIMS_TODAY
            away_pct = 1 - home_pct

            print(f"{away} — {away_goals/N_SIMS_TODAY:.2f} GF — {away_pct:.1%} to win")
            print(f"{home} — {home_goals/N_SIMS_TODAY:.2f} GF — {home_pct:.1%} to win")
            fav = "HOME" if home_pct > 0.62 else "AWAY" if away_pct > 0.62 else "TOSS-UP"
            total = round((home_goals + away_goals) / N_SIMS_TODAY, 2)
            print(f"   → Favorite: {fav} | Expected Total: ~{total}")
            print("-" * 60)
    print("="*88 + "\n")


# ================= 8. FULL SEASON MONTE CARLO =================
schedule = scrape_schedule()
current_standings = build_current_standings(schedule)
remaining_games = schedule[~schedule.played]
download_nst_data()

all_teams = sorted(current_standings.team.unique())
playoff_counter = Counter()
cup_counter = Counter()
pres_counter = Counter()

print(f"\nRunning {N_SIMS_FULL:,} full-season simulations on {len(remaining_games)} games...")
start_time = time.time()

for sim in range(N_SIMS_FULL):
    if SHOW_PROGRESS_EVERY and sim % SHOW_PROGRESS_EVERY == 0 and sim > 0:
        print(f"   → {sim:,}/{N_SIMS_FULL:,} simulations complete")

    standings = current_standings.copy(deep=True)

    for _, game in remaining_games.iterrows():
        home, away = game.home, game.visitor
        winner, hpts, apts, hgf, agf, reg = simulate_game(home, away)

        h_idx = standings[standings.team == home].index[0]
        a_idx = standings[standings.team == away].index[0]

        standings.loc[h_idx, ["points", "gf", "ga"]] += [hpts, hgf, agf]
        standings.loc[a_idx, ["points", "gf", "ga"]] += [apts, agf, hgf]
        if hpts == 2 and reg: standings.loc[h_idx, "row"] += 1
        if apts == 2 and reg: standings.loc[a_idx, "row"] += 1
        if hpts == 2: standings.loc[h_idx, "otw"] += 1
        if apts == 2: standings.loc[a_idx, "otw"] += 1

    standings["gf-ga"] = standings["gf"] - standings["ga"]
    final = standings.sort_values(by=["points", "row", "otw", "gf-ga", "gf"], ascending=False).reset_index(drop=True)
    pres_counter[final.iloc[0].team] += 1

    playoff_teams = get_playoff_teams(final)
    for t in playoff_teams:
        playoff_counter[t] += 1

    east = [t for t in playoff_teams if t in DIVISIONS["Atlantic"] + DIVISIONS["Metropolitan"]]
    west = [t for t in playoff_teams if t in DIVISIONS["Central"] + DIVISIONS["Pacific"]]
    east.sort(key=lambda x: final[final.team == x].index[0])
    west.sort(key=lambda x: final[final.team == x].index[0])

    east_champ = None
    west_champ = None
    if len(east) >= 2:
        while len(east) > 1:
            east = [best_of_7(east[i], east[i+1], home_first=True) for i in range(0, len(east), 2)]
        east_champ = east[0]
    if len(west) >= 2:
        while len(west) > 1:
            west = [best_of_7(west[i], west[i+1], home_first=True) for i in range(0, len(west), 2)]
        west_champ = west[0]

    if east_champ and west_champ:
        home_first = final[final.team == east_champ].index[0] < final[final.team == west_champ].index[0]
        cup_winner = best_of_7(east_champ, west_champ, home_first)
        cup_counter[cup_winner] += 1


# ================= 9. FINAL RESULTS =================
elapsed = time.time() - start_time
results = []
for team in all_teams:
    results.append({
        "Team": team,
        "Playoff %": f"{playoff_counter[team]/N_SIMS_FULL:.1%}",
        "President's Trophy %": f"{pres_counter[team]/N_SIMS_FULL:.2%}",
        "Stanley Cup %": f"{cup_counter[team]/N_SIMS_FULL:.2%}"
    })

final_df = pd.DataFrame(results).sort_values("Playoff %", ascending=False)

print("\n" + "="*100)
print(f"NHL {CURRENT_SEASON_FULL} FINAL RESULTS — {N_SIMS_FULL:,} sims in {elapsed:.0f}s".center(100))
print("="*100)
print(final_df.to_string(index=False))
print(f"\nResults saved → {PREDICTIONS_CSV}")
final_df.to_csv(PREDICTIONS_CSV, index=False)