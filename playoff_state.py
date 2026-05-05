# playoff_state.py
# Build current playoff bracket state from completed playoff games.
#
# Each series is keyed by frozenset({team_a, team_b}) -> dict:
#   {
#     'team1': str,            # higher seed (home-ice team1)
#     'team2': str,            # lower seed
#     'home_first': bool,      # True if team1 had home ice originally
#     'wins1': int,            # team1 wins so far
#     'wins2': int,            # team2 wins so far
#     'games_played': int,
#     'completed': bool,
#     'winner': str | None,    # filled when completed
#   }


def _series_key(team_a, team_b):
    return frozenset({team_a, team_b})


def _scan_series(playoff_games, team1, team2, home_first):
    """
    Look up all played games between team1 and team2 in playoff_games and
    return the current series state. Order-agnostic on input team1/team2; the
    returned wins are reported relative to the team1 argument.
    """
    if playoff_games is None or playoff_games.empty:
        return {
            'team1': team1, 'team2': team2, 'home_first': home_first,
            'wins1': 0, 'wins2': 0, 'games_played': 0,
            'completed': False, 'winner': None,
        }

    teams = {team1, team2}
    mask = playoff_games.apply(
        lambda g: g.played and {g.home, g.visitor} == teams, axis=1
    )
    series_games = playoff_games[mask].sort_values("date")

    wins1 = wins2 = 0
    for _, g in series_games.iterrows():
        if g.hg > g.vg:
            winner_team = g.home
        elif g.vg > g.hg:
            winner_team = g.visitor
        else:
            continue  # shouldn't happen in playoffs (no ties)
        if winner_team == team1:
            wins1 += 1
        else:
            wins2 += 1

    games_played = wins1 + wins2
    completed = wins1 == 4 or wins2 == 4
    winner = team1 if wins1 == 4 else (team2 if wins2 == 4 else None)

    return {
        'team1': team1, 'team2': team2, 'home_first': home_first,
        'wins1': wins1, 'wins2': wins2, 'games_played': games_played,
        'completed': completed, 'winner': winner,
    }


def get_conference_seeding(conf_name, div1_name, div2_name, final_standings, divisions):
    """
    Build the 8-seed playoff order for a conference using NHL divisional rules.
    Mirrors the logic in season_simulation.py but operates on actual final standings.

    Returns:
        tuple: (seeds, div1_top3, div2_top3, wc_sorted)
    """
    div1 = divisions[div1_name]
    div2 = divisions[div2_name]

    # Top 3 from each division by points
    div1_sorted = final_standings[final_standings.team.isin(div1)].sort_values(
        by=["points", "row", "gf-ga", "gf"], ascending=False
    ).team.tolist()
    div2_sorted = final_standings[final_standings.team.isin(div2)].sort_values(
        by=["points", "row", "gf-ga", "gf"], ascending=False
    ).team.tolist()

    div1_top3 = div1_sorted[:3]
    div2_top3 = div2_sorted[:3]

    div1_winner_pts = final_standings[final_standings.team == div1_top3[0]].iloc[0]["points"]
    div2_winner_pts = final_standings[final_standings.team == div2_top3[0]].iloc[0]["points"]

    # Wildcards: best two remaining conference teams
    conf_teams = div1 + div2
    used = set(div1_top3 + div2_top3)
    wc_pool = final_standings[
        final_standings.team.isin(conf_teams) & ~final_standings.team.isin(used)
    ].sort_values(by=["points", "row", "gf-ga", "gf"], ascending=False).team.tolist()
    wc_sorted = wc_pool[:2]

    # Higher-points division winner is "Division 1" in seeding
    if div1_winner_pts >= div2_winner_pts:
        a_top, b_top = div1_top3, div2_top3
    else:
        a_top, b_top = div2_top3, div1_top3

    # Seeds 1..8: A1, B1, A2, A3, B2, B3, WC1, WC2
    seeds = a_top[:1] + b_top[:1] + a_top[1:3] + b_top[1:3] + wc_sorted
    return seeds, a_top, b_top, wc_sorted


def build_round1_matchups(final_standings, divisions):
    """
    Returns list of matchups for the actual playoff bracket:
    [
      ('east', 'div1_top', team1, team2),  # 1 vs WC2
      ('east', 'div1_bot', team1, team2),  # 3 vs 4 (within Div1)
      ('east', 'div2_top', team1, team2),  # 2 vs WC1
      ('east', 'div2_bot', team1, team2),  # 5 vs 6 (within Div2)
      ('west', ...), ...
    ]
    Each matchup has team1 as the higher seed.
    """
    east_seeds, east_a_top, east_b_top, east_wc = get_conference_seeding(
        'east', 'Atlantic', 'Metropolitan', final_standings, divisions
    )
    west_seeds, west_a_top, west_b_top, west_wc = get_conference_seeding(
        'west', 'Central', 'Pacific', final_standings, divisions
    )

    matchups = []
    for conf, a_top, b_top, wc in [
        ('east', east_a_top, east_b_top, east_wc),
        ('west', west_a_top, west_b_top, west_wc),
    ]:
        # Div1 bracket: A1 vs WC2, A2 vs A3
        matchups.append((conf, 'div1_top', a_top[0], wc[1]))
        matchups.append((conf, 'div1_bot', a_top[1], a_top[2]))
        # Div2 bracket: B1 vs WC1, B2 vs B3
        matchups.append((conf, 'div2_top', b_top[0], wc[0]))
        matchups.append((conf, 'div2_bot', b_top[1], b_top[2]))
    return matchups


def _bracket_seed_priority(team, final_standings):
    """Return the row index (lower = higher seed) for tiebreaking matchup ordering."""
    rows = final_standings.index[final_standings.team == team]
    return rows[0] if len(rows) else 999


def build_playoff_state(playoff_games, final_standings, divisions):
    """
    Build the full bracket state from played playoff games.

    Series that haven't started yet (later rounds) are still seeded as None.
    For in-progress or future series, downstream rounds are set up only when
    upstream series have completed (since matchup pairings depend on winners).

    Returns:
        dict: bracket state with keys:
          'series': { slot_id -> series_state_dict }
          'slots':  ordered list of slot ids
          'r1_matchups': list of (conf, slot_suffix, team1, team2)
          'meta': any debug info
    """
    state = {'series': {}, 'slots': [], 'r1_matchups': []}

    r1 = build_round1_matchups(final_standings, divisions)
    state['r1_matchups'] = r1

    # ROUND 1 — populate from played games. Higher seed is team1, gets home ice.
    for conf, suffix, team1, team2 in r1:
        slot = f"R1_{conf}_{suffix}"
        s = _scan_series(playoff_games, team1, team2, home_first=True)
        state['series'][slot] = s
        state['slots'].append(slot)

    # ROUND 2 — within each conference bracket, top winner plays bot winner
    # Eastern: R1_east_div1_top winner vs R1_east_div1_bot winner
    #          R1_east_div2_top winner vs R1_east_div2_bot winner
    # Same for west.
    for conf in ('east', 'west'):
        for div in ('div1', 'div2'):
            top_slot = f"R1_{conf}_{div}_top"
            bot_slot = f"R1_{conf}_{div}_bot"
            top_winner = state['series'][top_slot]['winner']
            bot_winner = state['series'][bot_slot]['winner']

            slot = f"R2_{conf}_{div}"
            state['slots'].append(slot)

            if top_winner and bot_winner:
                # Higher seed (lower index in standings) is team1
                if _bracket_seed_priority(top_winner, final_standings) <= \
                   _bracket_seed_priority(bot_winner, final_standings):
                    t1, t2 = top_winner, bot_winner
                else:
                    t1, t2 = bot_winner, top_winner
                state['series'][slot] = _scan_series(playoff_games, t1, t2, home_first=True)
            else:
                state['series'][slot] = None  # not yet determined

    # CONFERENCE FINALS — winners of div1 R2 vs div2 R2 within each conf
    for conf in ('east', 'west'):
        d1 = state['series'].get(f"R2_{conf}_div1")
        d2 = state['series'].get(f"R2_{conf}_div2")
        slot = f"CF_{conf}"
        state['slots'].append(slot)

        if d1 and d2 and d1['winner'] and d2['winner']:
            w1, w2 = d1['winner'], d2['winner']
            if _bracket_seed_priority(w1, final_standings) <= \
               _bracket_seed_priority(w2, final_standings):
                t1, t2 = w1, w2
            else:
                t1, t2 = w2, w1
            state['series'][slot] = _scan_series(playoff_games, t1, t2, home_first=True)
        else:
            state['series'][slot] = None

    # STANLEY CUP FINAL — east champ vs west champ
    e_cf = state['series'].get('CF_east')
    w_cf = state['series'].get('CF_west')
    state['slots'].append('SCF')
    if e_cf and w_cf and e_cf['winner'] and w_cf['winner']:
        e, w = e_cf['winner'], w_cf['winner']
        # Home ice in SCF: team with better regular-season standing
        if _bracket_seed_priority(e, final_standings) <= \
           _bracket_seed_priority(w, final_standings):
            t1, t2, hf = e, w, True
        else:
            t1, t2, hf = w, e, True
        state['series']['SCF'] = _scan_series(playoff_games, t1, t2, home_first=hf)
    else:
        state['series']['SCF'] = None

    return state


def round_status(state):
    """
    Classify each round as 'done' (all series completed), 'active' (some games
    played), or 'pending' (no games played yet).

    Used by the display layer to skip sections whose outcomes are already
    determined.
    """
    rounds = {
        'R1':  [s for slot, s in state['series'].items() if slot.startswith('R1_')],
        'R2':  [s for slot, s in state['series'].items() if slot.startswith('R2_')],
        'CF':  [s for slot, s in state['series'].items() if slot.startswith('CF_')],
        'SCF': [state['series'].get('SCF')],
    }

    status = {}
    for r, series_list in rounds.items():
        # Treat None entries (downstream not yet seeded) as pending
        played = [s for s in series_list if s is not None]
        if not played:
            status[r] = 'pending'
        elif all(s['completed'] for s in played):
            status[r] = 'done' if len(played) == len(series_list) else 'active'
        elif any(s['games_played'] > 0 for s in played):
            status[r] = 'active'
        else:
            status[r] = 'pending'
    return status


def describe_state(state):
    """Human-readable summary of current bracket state — used for the run header."""
    lines = []
    for slot in state['slots']:
        s = state['series'].get(slot)
        if s is None:
            lines.append(f"  {slot}: pending (upstream series unfinished)")
            continue
        if s['completed']:
            status = "FINAL"
        elif s['games_played'] == 0:
            status = "not started"
        else:
            status = f"in progress ({s['games_played']} games played)"
        lines.append(
            f"  {slot}: {s['team1']} {s['wins1']}-{s['wins2']} {s['team2']}  [{status}]"
        )
    return "\n".join(lines)
