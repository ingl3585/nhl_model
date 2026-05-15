# visualization.py
# NHL Model Visualization - Static chart generation

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.ticker as mtick
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import seaborn as sns
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from config import *
from season_simulation import DIVISIONS
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Editorial chart style
plt.style.use('default')
sns.set_theme(style="white")

BG_COLOR = "#f7f8fa"
AXIS_TEXT = "#1f2933"
MUTED_TEXT = "#5f6b7a"
GRID_COLOR = "#d8dee8"
BAR_EDGE = "#ffffff"

# Team abbreviations for logo filenames (matches download_logos.py)
TEAM_ABBREVS = {
    "Boston Bruins": "BOS", "Buffalo Sabres": "BUF", "Detroit Red Wings": "DET",
    "Florida Panthers": "FLA", "Montreal Canadiens": "MTL", "Ottawa Senators": "OTT",
    "Tampa Bay Lightning": "TBL", "Toronto Maple Leafs": "TOR",
    "Carolina Hurricanes": "CAR", "Columbus Blue Jackets": "CBJ", "New Jersey Devils": "NJD",
    "New York Islanders": "NYI", "New York Rangers": "NYR", "Philadelphia Flyers": "PHI",
    "Pittsburgh Penguins": "PIT", "Washington Capitals": "WSH",
    "Chicago Blackhawks": "CHI", "Colorado Avalanche": "COL", "Dallas Stars": "DAL",
    "Minnesota Wild": "MIN", "Nashville Predators": "NSH", "St. Louis Blues": "STL",
    "Utah Mammoth": "UTA", "Winnipeg Jets": "WPG",
    "Anaheim Ducks": "ANA", "Calgary Flames": "CGY", "Edmonton Oilers": "EDM",
    "Los Angeles Kings": "LAK", "San Jose Sharks": "SJS", "Seattle Kraken": "SEA",
    "Vancouver Canucks": "VAN", "Vegas Golden Knights": "VGK"
}

# NHL team primary colors (actual team colors for bars)
TEAM_COLORS = {
    # Atlantic Division
    "Boston Bruins": "#FFB81C", "Buffalo Sabres": "#003087", "Detroit Red Wings": "#CE1126",
    "Florida Panthers": "#C8102E", "Montreal Canadiens": "#AF1E2D", "Ottawa Senators": "#C52032",
    "Tampa Bay Lightning": "#002868", "Toronto Maple Leafs": "#003E7E",
    # Metropolitan Division
    "Carolina Hurricanes": "#CE1126", "Columbus Blue Jackets": "#002654", "New Jersey Devils": "#CE1126",
    "New York Islanders": "#00539B", "New York Rangers": "#0038A8", "Philadelphia Flyers": "#F74902",
    "Pittsburgh Penguins": "#FCB514", "Washington Capitals": "#C8102E",
    # Central Division
    "Chicago Blackhawks": "#CF0A2C", "Colorado Avalanche": "#6F263D", "Dallas Stars": "#006847",
    "Minnesota Wild": "#A6192E", "Nashville Predators": "#FFB81C", "St. Louis Blues": "#002F87",
    "Utah Mammoth": "#69B3E7", "Winnipeg Jets": "#041E42",
    # Pacific Division
    "Anaheim Ducks": "#F47A38", "Calgary Flames": "#C8102E", "Edmonton Oilers": "#FF4C00",
    "Los Angeles Kings": "#111111", "San Jose Sharks": "#006D75", "Seattle Kraken": "#001628",
    "Vancouver Canucks": "#00205B", "Vegas Golden Knights": "#B4975A"
}

def get_team_color(team_name):
    """
    Get color for a team based on conference membership.

    Args:
        team_name (str): Full team name

    Returns:
        str: Hex color code
    """
    eastern_teams = DIVISIONS["Atlantic"] + DIVISIONS["Metropolitan"]

    if team_name in eastern_teams:
        return EAST_PRIMARY
    elif team_name in DIVISIONS["Central"] + DIVISIONS["Pacific"]:
        return WEST_PRIMARY
    else:
        return "#808080"  # Gray fallback


def get_team_logo(team_name, zoom=0.15):
    """
    Load team logo image for display in charts.

    Args:
        team_name (str): Full team name
        zoom (float): Scale factor for logo size

    Returns:
        OffsetImage: Logo image ready for matplotlib, or None if not found
    """
    if not HAS_PIL:
        return None

    abbrev = TEAM_ABBREVS.get(team_name)
    if not abbrev:
        return None

    logo_path = Path("data/logos") / f"{abbrev}.png"
    if not logo_path.exists():
        return None

    try:
        img = Image.open(logo_path)
        return OffsetImage(img, zoom=zoom)
    except Exception:
        return None


def ensure_output_dir():
    """
    Create visualization output directory if it doesn't exist.

    Returns:
        Path: Path object for output directory
    """
    output_dir = Path(VIZ_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _clean_probability_columns(df, columns):
    """Normalize probability columns to floats in the 0-1 range."""
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        df[col] = pd.to_numeric(df[col].astype(str).str.rstrip('%'), errors='coerce').fillna(0) / 100
    return df


def _style_probability_axis(ax, max_value=1.0):
    ax.set_facecolor(BG_COLOR)
    ax.grid(axis='x', color=GRID_COLOR, linewidth=0.8, alpha=0.85)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0, decimals=0))
    ax.tick_params(axis='x', colors=MUTED_TEXT, labelsize=9, length=0, pad=8)
    ax.tick_params(axis='y', colors=AXIS_TEXT, labelsize=10, length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xlim(0, max_value)


def _add_chart_header(fig, title, subtitle):
    fig.text(0.06, 0.945, title, fontsize=18, fontweight='bold',
             color=AXIS_TEXT, ha='left', va='top')
    fig.text(0.06, 0.895, subtitle, fontsize=10.5,
             color=MUTED_TEXT, ha='left', va='top')


def create_todays_games_cards(predictions, output_path, sim_count, date_str):
    """
    Generate game card grid for today's matchups.

    Args:
        predictions (list[dict]): List of game predictions with keys:
            home, away, home_pct, away_pct, home_avg_goals, away_avg_goals, favorite
        output_path (str): Full path to save PNG/PDF
        sim_count (int): Number of simulations
        date_str (str): Formatted date string

    Returns:
        str: Path to saved file
    """
    if not predictions or len(predictions) == 0:
        # No games today - create simple message card
        fig, ax = plt.subplots(figsize=(10, 5.5), dpi=VIZ_DPI)
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        ax.text(0.5, 0.58, "No games scheduled today",
                ha='center', va='center', fontsize=24, fontweight='bold',
                color=AXIS_TEXT)
        ax.text(0.5, 0.47, f"{date_str}",
                ha='center', va='center', fontsize=12, color=MUTED_TEXT)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        plt.savefig(output_path, dpi=VIZ_DPI, facecolor=BG_COLOR)
        plt.close(fig)
        return output_path

    n_games = len(predictions)
    n_cols = TODAY_GAMES_GRID_COLS
    n_rows = (n_games + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=TODAY_GAMES_FIGURE_SIZE, dpi=VIZ_DPI)
    if n_rows == 1 and n_cols == 1:
        axes = np.array([axes])
    axes = np.array(axes).flatten()

    for i, pred in enumerate(predictions):
        ax = axes[i]
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')

        # Card background
        rect = patches.Rectangle((0.02, 0.02), 0.96, 0.96, linewidth=2,
                                 edgecolor='#cccccc', facecolor='white')
        ax.add_patch(rect)

        # Team names at top
        ax.text(0.5, 0.82, f"{pred['away']} @ {pred['home']}",
                ha='center', va='center', fontsize=11, fontweight='bold')

        # Away team row (logo + bar + percentage)
        away_pct = pred['away_pct']
        away_color = TEAM_COLORS.get(pred['away'], EAST_PRIMARY)
        bar_y_away = 0.62
        bar_height = 0.08
        bar_start_x = 0.17
        bar_width = 0.60

        # Away logo (inside card, left side)
        away_logo = get_team_logo(pred['away'], zoom=0.038)
        if away_logo:
            ab = AnnotationBbox(away_logo, (0.10, bar_y_away + bar_height/2),
                               frameon=False, box_alignment=(0.5, 0.5))
            ax.add_artist(ab)

        # Away bar
        ax.add_patch(patches.Rectangle((bar_start_x, bar_y_away), away_pct * bar_width, bar_height,
                                       facecolor=away_color, alpha=0.85))

        # Away percentage (right side, no overlap)
        ax.text(0.82, bar_y_away + bar_height/2, f"{away_pct:.1%}",
                ha='left', va='center', fontsize=10, fontweight='bold', color='#333333')

        # Home team row (logo + bar + percentage)
        home_pct = pred['home_pct']
        home_color = TEAM_COLORS.get(pred['home'], WEST_PRIMARY)
        bar_y_home = 0.38

        # Home logo (inside card, left side)
        home_logo = get_team_logo(pred['home'], zoom=0.038)
        if home_logo:
            ab = AnnotationBbox(home_logo, (0.10, bar_y_home + bar_height/2),
                               frameon=False, box_alignment=(0.5, 0.5))
            ax.add_artist(ab)

        # Home bar
        ax.add_patch(patches.Rectangle((bar_start_x, bar_y_home), home_pct * bar_width, bar_height,
                                       facecolor=home_color, alpha=0.85))

        # Home percentage (right side, no overlap)
        ax.text(0.82, bar_y_home + bar_height/2, f"{home_pct:.1%}",
                ha='left', va='center', fontsize=10, fontweight='bold', color='#333333')

        # Info at bottom - cleaner layout
        ax.text(0.5, 0.28, f"Expected: {pred['away_avg_goals']:.1f} - {pred['home_avg_goals']:.1f}",
                ha='center', va='center', fontsize=9, color='#555555')
        ax.text(0.5, 0.16, f"Total: ~{pred['expected_total']:.1f} goals",
                ha='center', va='center', fontsize=9, color='#777777')

    # Hide unused subplots
    for i in range(n_games, len(axes)):
        axes[i].axis('off')

    plt.suptitle(f"Today's NHL Games - {date_str}", fontsize=18, fontweight='bold', y=0.97)
    fig.text(0.5, 0.935, f"Based on {sim_count:,} simulations per game",
             ha='center', fontsize=12, style='italic')
    plt.tight_layout(rect=[0, 0, 1, 0.90])
    plt.savefig(output_path, dpi=VIZ_DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)

    return output_path


def create_playoff_probability_chart(results_df, output_path, n_sims):
    """
    Create horizontal bar chart of playoff probabilities for all 32 teams.

    Args:
        results_df (pd.DataFrame): Results with columns: Team, Playoff % (as float 0-1)
        output_path (str): Full path to save PNG/PDF
        n_sims (int): Number of simulations

    Returns:
        str: Path to saved file
    """
    df = _clean_probability_columns(results_df, ['Playoff %']).copy()
    df = df.sort_values('Playoff %', ascending=True)

    colors = [TEAM_COLORS.get(team, EAST_PRIMARY) for team in df['Team']]
    row_height = max(0.28, min(0.42, 10.0 / max(len(df), 1)))
    fig_height = max(8.5, len(df) * row_height + 1.8)
    fig, ax = plt.subplots(figsize=(12, fig_height), dpi=VIZ_DPI)
    fig.patch.set_facecolor(BG_COLOR)

    y_pos = np.arange(len(df))
    ax.barh(y_pos, df['Playoff %'], color=colors, edgecolor=BAR_EDGE,
            linewidth=1.2, height=0.68, alpha=0.95)

    for i, prob in enumerate(df['Playoff %']):
        label = f"{prob:.1%}"
        if prob >= 0.18:
            ax.text(max(prob - 0.018, 0.015), i, label, va='center', ha='right',
                    fontsize=8.5, color='white', fontweight='bold')
        else:
            ax.text(min(prob + 0.014, 1.01), i, label, va='center', ha='left',
                    fontsize=8.5, color=AXIS_TEXT, fontweight='bold')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(df['Team'], fontsize=9.5)
    _style_probability_axis(ax, 1.03)
    ax.set_xlabel('')

    _add_chart_header(
        fig,
        'NHL Playoff Probabilities',
        f'2025-26 season projection based on {n_sims:,} simulations'
    )
    fig.subplots_adjust(left=0.25, right=0.965, top=0.86, bottom=0.055)
    plt.savefig(output_path, dpi=VIZ_DPI, facecolor=BG_COLOR)
    plt.close(fig)

    return output_path


def create_cup_probability_chart(results_df, output_path, n_sims):
    """
    Create Stanley Cup probability chart for top contenders.

    Args:
        results_df (pd.DataFrame): Results with columns: Team, Stanley Cup % (as float 0-1)
        output_path (str): Full path to save PNG/PDF
        n_sims (int): Number of simulations

    Returns:
        str: Path to saved file
    """
    df = _clean_probability_columns(results_df, ['Stanley Cup %']).copy()
    df = df.sort_values('Stanley Cup %', ascending=False)
    df = df.head(CUP_CHART_TOP_N)
    df = df[df['Stanley Cup %'] > 0.005]
    df = df.sort_values('Stanley Cup %', ascending=True)

    colors = [TEAM_COLORS.get(team, EAST_PRIMARY) for team in df['Team']]
    fig_height = max(4.8, len(df) * 0.62 + 1.5)
    fig, ax = plt.subplots(figsize=(11.5, fig_height), dpi=VIZ_DPI)
    fig.patch.set_facecolor(BG_COLOR)

    y_pos = np.arange(len(df))
    ax.barh(y_pos, df['Stanley Cup %'], color=colors, edgecolor=BAR_EDGE,
            linewidth=1.2, height=0.68, alpha=0.96)

    max_prob = max(float(df['Stanley Cup %'].max()), 0.01)
    x_max = min(1.0, max_prob * 1.22 + 0.015)
    for i, prob in enumerate(df['Stanley Cup %']):
        label = f"{prob:.1%}"
        if prob >= max_prob * 0.42:
            ax.text(prob - x_max * 0.018, i, label, va='center', ha='right',
                    fontsize=10, color='white', fontweight='bold')
        else:
            ax.text(prob + x_max * 0.012, i, label, va='center', ha='left',
                    fontsize=10, color=AXIS_TEXT, fontweight='bold')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(df['Team'], fontsize=10.5)
    _style_probability_axis(ax, x_max)
    ax.set_xlabel('')

    _add_chart_header(
        fig,
        'Stanley Cup Odds',
        f'Top {len(df)} contenders based on {n_sims:,} playoff simulations'
    )
    fig.subplots_adjust(left=0.24, right=0.965, top=0.82, bottom=0.10)
    plt.savefig(output_path, dpi=VIZ_DPI, facecolor=BG_COLOR)
    plt.close(fig)

    return output_path


def create_probability_heatmap(results_df, output_path, n_sims):
    """
    Create probability grid/heatmap showing all playoff stages.

    Args:
        results_df (pd.DataFrame): Results with all probability columns (as float 0-1)
        output_path (str): Full path to save PNG/PDF
        n_sims (int): Number of simulations

    Returns:
        str: Path to saved file
    """
    prob_cols = ['Playoff %', 'Round 2 %', 'Conf Finals %', 'Finals %', 'Stanley Cup %', "President's Trophy %"]
    df = _clean_probability_columns(results_df, prob_cols).copy()
    df = df.sort_values(['Stanley Cup %', 'Finals %', 'Conf Finals %', 'Round 2 %', 'Playoff %'],
                        ascending=False)

    # The playoff picture can be locked late in the season; hide fully empty teams
    # so the heatmap focuses on the field still represented in the simulation.
    visible_mask = df[prob_cols].max(axis=1) > 0
    df = df[visible_mask].copy()

    heatmap_data = df[prob_cols].values
    annot = np.vectorize(lambda value: f'{value:.0%}' if value in (0, 1) else f'{value:.1%}')(heatmap_data)

    fig_height = max(6.0, len(df) * 0.46 + 1.8)
    fig, ax = plt.subplots(figsize=(11.5, fig_height), dpi=VIZ_DPI)
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    sns.heatmap(
        heatmap_data,
        ax=ax,
        cmap=HEATMAP_COLORMAP,
        vmin=0,
        vmax=1,
        annot=annot,
        fmt='',
        linewidths=1.1,
        linecolor=BG_COLOR,
        cbar=True,
        cbar_kws={'format': mtick.PercentFormatter(1.0), 'shrink': 0.76, 'pad': 0.025}
    )

    cbar = ax.collections[0].colorbar
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(colors=MUTED_TEXT, labelsize=8, length=0)

    ax.set_xticks(np.arange(len(prob_cols)) + 0.5)
    ax.set_xticklabels(['Playoff', 'Round 2', 'Conf Finals', 'Finals', 'Cup', "Pres. Trophy"],
                       fontsize=9.5, fontweight='bold', color=AXIS_TEXT, rotation=0)
    ax.xaxis.tick_top()
    ax.tick_params(axis='x', length=0, pad=8)
    ax.set_yticks(np.arange(len(df)) + 0.5)
    ax.set_yticklabels(df['Team'], fontsize=9.5, color=AXIS_TEXT, rotation=0)
    ax.tick_params(axis='y', length=0)
    ax.set_xlabel('')
    ax.set_ylabel('')
    for spine in ax.spines.values():
        spine.set_visible(False)

    for text, value in zip(ax.texts, heatmap_data.flatten()):
        text.set_color('white' if value >= 0.55 else AXIS_TEXT)
        text.set_fontsize(8.2)
        text.set_fontweight('bold')

    _add_chart_header(
        fig,
        'Playoff Advancement Matrix',
        f'Probability by round based on {n_sims:,} simulations'
    )
    fig.subplots_adjust(left=0.23, right=0.91, top=0.82, bottom=0.08)
    plt.savefig(output_path, dpi=VIZ_DPI, facecolor=BG_COLOR)
    plt.close(fig)

    return output_path


def generate_all_visualizations(today_predictions=None, results_df=None,
                                n_sims_full=None, n_sims_today=None, date_str=None):
    """
    Main entry point - orchestrates all chart generation.

    Args:
        today_predictions (list[dict] | None): Today's game predictions
        results_df (pd.DataFrame | None): Final results dataframe
        n_sims_full (int): Number of full season simulations
        n_sims_today (int): Number of simulations per game
        date_str (str): Formatted date string

    Returns:
        dict: Paths to all generated files
    """
    if not ENABLE_VISUALIZATIONS:
        return {}

    paths = {}

    # Ensure output directory exists
    try:
        output_dir = ensure_output_dir()
    except Exception as e:
        print(f"Warning: Could not create visualization directory: {e}")
        return {}

    # Generate date stamp for file naming
    date_stamp = datetime.now().strftime("%Y%m%d")

    # 1. Today's games chart
    if today_predictions is not None and n_sims_today is not None and date_str is not None:
        try:
            output_path = output_dir / f"todays_games_{date_stamp}.{VIZ_FORMAT}"
            paths['today_games'] = create_todays_games_cards(
                today_predictions, str(output_path), n_sims_today, date_str
            )
        except Exception as e:
            print(f"Warning: Could not generate today's games chart: {e}")
            paths['today_games'] = None

    # 2. Playoff probability chart
    if results_df is not None and n_sims_full is not None:
        try:
            output_path = output_dir / f"playoff_probabilities_{date_stamp}.{VIZ_FORMAT}"
            paths['playoff_probs'] = create_playoff_probability_chart(
                results_df, str(output_path), n_sims_full
            )
        except Exception as e:
            print(f"Warning: Could not generate playoff probability chart: {e}")
            paths['playoff_probs'] = None

    # 3. Cup probability chart
    if results_df is not None and n_sims_full is not None:
        try:
            output_path = output_dir / f"cup_probabilities_{date_stamp}.{VIZ_FORMAT}"
            paths['cup_probs'] = create_cup_probability_chart(
                results_df, str(output_path), n_sims_full
            )
        except Exception as e:
            print(f"Warning: Could not generate cup probability chart: {e}")
            paths['cup_probs'] = None

    # 4. Probability heatmap
    if results_df is not None and n_sims_full is not None:
        try:
            output_path = output_dir / f"probability_heatmap_{date_stamp}.{VIZ_FORMAT}"
            paths['heatmap'] = create_probability_heatmap(
                results_df, str(output_path), n_sims_full
            )
        except Exception as e:
            print(f"Warning: Could not generate probability heatmap: {e}")
            paths['heatmap'] = None

    return paths
