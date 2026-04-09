# visualization.py
# NHL Model Visualization - Static chart generation

import matplotlib.pyplot as plt
import matplotlib.patches as patches
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

# Set matplotlib style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

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
        fig, ax = plt.subplots(figsize=(10, 6), dpi=VIZ_DPI)
        ax.text(0.5, 0.5, "No games scheduled today",
                ha='center', va='center', fontsize=24, fontweight='bold')
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        plt.suptitle(f"Today's NHL Games - {date_str}", fontsize=18, fontweight='bold')
        plt.tight_layout()
        plt.savefig(output_path, dpi=VIZ_DPI, bbox_inches='tight', facecolor='white')
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
    df = results_df.copy()

    # Sort by playoff probability (descending for chart display)
    df = df.sort_values('Playoff %', ascending=True)  # Bottom to top

    # Assign colors based on actual team colors
    colors = [TEAM_COLORS.get(team, EAST_PRIMARY) for team in df['Team']]

    # Create figure
    fig, ax = plt.subplots(figsize=PLAYOFF_BAR_FIGURE_SIZE, dpi=VIZ_DPI)

    # Plot bars
    y_pos = np.arange(len(df))
    bars = ax.barh(y_pos, df['Playoff %'], color=colors, edgecolor='black', linewidth=0.5, alpha=0.8)

    # Add percentage labels
    for i, (team, prob) in enumerate(zip(df['Team'], df['Playoff %'])):
        if prob > 0.15:
            # Label inside bar (white text)
            ax.text(prob - 0.02, i, f"{prob:.1%}", va='center', ha='right',
                   fontsize=8, color='white', fontweight='bold')
        else:
            # Label outside bar (black text)
            ax.text(prob + 0.01, i, f"{prob:.1%}", va='center', ha='left',
                   fontsize=8, color='black', fontweight='bold')

    # Formatting
    ax.set_yticks(y_pos)
    ax.set_xlabel('Playoff Probability', fontsize=12, fontweight='bold')
    ax.xaxis.set_label_position('top')  # Move x-axis label to top
    ax.xaxis.tick_top()  # Move x-axis ticks to top

    # Add team logos on y-axis BEFORE setting xlim
    has_logos = False
    logos_added = 0
    for i, team in enumerate(df['Team']):
        logo = get_team_logo(team, zoom=0.04)  # Small logos to prevent overlap
        if logo:
            ab = AnnotationBbox(logo, (-0.06, i), frameon=False, xycoords='data',
                               box_alignment=(1, 0.5), clip_on=False)  # Don't clip logos
            ax.add_artist(ab)
            has_logos = True
            logos_added += 1

    # Extend xlim to make room for logos on the left
    if has_logos:
        ax.set_xlim(-0.12, 1.05)  # Start at -0.12 to show logos
    else:
        ax.set_xlim(0, 1.05)

    # Set y-axis labels (use team names if logos not available)
    if has_logos:
        ax.set_yticklabels([])  # Hide text labels when using logos
    else:
        ax.set_yticklabels(df['Team'], fontsize=9)

    # Grid
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)

    # Remove spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False) if has_logos else None

    # Add title and subtitle using fig-level functions
    fig.suptitle('NHL Playoff Probabilities - 2025-26 Season', fontsize=16, fontweight='bold', y=0.97)
    fig.text(0.5, 0.935, f'Based on {n_sims:,} simulations',
             ha='center', fontsize=11, style='italic')

    plt.tight_layout(rect=[0, 0, 1, 0.85])
    plt.savefig(output_path, dpi=VIZ_DPI, bbox_inches='tight', facecolor='white')
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
    df = results_df.copy()

    # Filter to top N teams or teams with >0.5% chance
    df = df.sort_values('Stanley Cup %', ascending=False)
    df = df.head(CUP_CHART_TOP_N)
    df = df[df['Stanley Cup %'] > 0.005]  # At least 0.5%

    # Sort for chart display (bottom to top)
    df = df.sort_values('Stanley Cup %', ascending=True)

    # Assign colors based on actual team colors
    colors = [TEAM_COLORS.get(team, EAST_PRIMARY) for team in df['Team']]

    # Create figure
    fig, ax = plt.subplots(figsize=CUP_BAR_FIGURE_SIZE, dpi=VIZ_DPI)

    # Plot bars
    y_pos = np.arange(len(df))
    bars = ax.barh(y_pos, df['Stanley Cup %'], color=colors, edgecolor='black', linewidth=0.5, alpha=0.8)

    # Add percentage labels
    for i, (team, prob) in enumerate(zip(df['Team'], df['Stanley Cup %'])):
        if prob > 0.10:
            # Label inside bar (white text)
            ax.text(prob - 0.005, i, f"{prob:.1%}", va='center', ha='right',
                   fontsize=9, color='white', fontweight='bold')
        else:
            # Label outside bar (black text)
            ax.text(prob + 0.005, i, f"{prob:.1%}", va='center', ha='left',
                   fontsize=9, color='black', fontweight='bold')

    # Formatting
    ax.set_yticks(y_pos)
    ax.set_xlabel('Stanley Cup Probability', fontsize=12, fontweight='bold')
    ax.xaxis.set_label_position('top')  # Move x-axis label to top
    ax.xaxis.tick_top()  # Move x-axis ticks to top
    max_prob = df['Stanley Cup %'].max()

    # Add team logos on y-axis BEFORE setting xlim
    has_logos = False
    for i, team in enumerate(df['Team']):
        logo = get_team_logo(team, zoom=0.04)  # Small logos consistent with other charts
        if logo:
            ab = AnnotationBbox(logo, (-0.02, i), frameon=False, xycoords='data',
                               box_alignment=(1, 0.5), clip_on=False)
            ax.add_artist(ab)
            has_logos = True

    # Extend xlim to make room for logos on the left
    if has_logos:
        ax.set_xlim(-0.08, max_prob * 1.15)  # Start at -0.08 to show logos
    else:
        ax.set_xlim(0, max_prob * 1.15)

    # Set y-axis labels (use team names if logos not available)
    if has_logos:
        ax.set_yticklabels([])  # Hide text labels when using logos
    else:
        ax.set_yticklabels(df['Team'], fontsize=10)

    # Grid
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)

    # Remove spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False) if has_logos else None

    # Add title and subtitle using fig-level functions
    fig.suptitle('Stanley Cup Championship Odds', fontsize=16, fontweight='bold', y=0.97)
    fig.text(0.5, 0.935, f'Top {len(df)} Contenders - Based on {n_sims:,} simulations',
             ha='center', fontsize=11, style='italic')

    plt.tight_layout(rect=[0, 0, 1, 0.85])
    plt.savefig(output_path, dpi=VIZ_DPI, bbox_inches='tight', facecolor='white')
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
    df = results_df.copy()

    # Sort by playoff probability
    df = df.sort_values('Playoff %', ascending=False)

    # Select columns for heatmap
    prob_cols = ['Playoff %', 'Round 2 %', 'Conf Finals %', 'Finals %', 'Stanley Cup %', "President's Trophy %"]
    heatmap_data = df[prob_cols].values

    # Create figure
    fig, ax = plt.subplots(figsize=HEATMAP_FIGURE_SIZE, dpi=VIZ_DPI)

    # Create heatmap (disable grid lines with linewidths=0)
    im = ax.imshow(heatmap_data, cmap=HEATMAP_COLORMAP, aspect='auto', vmin=0, vmax=1,
                   interpolation='nearest')

    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Probability', rotation=270, labelpad=20, fontsize=11, fontweight='bold')

    # Set ticks and labels
    ax.set_xticks(np.arange(len(prob_cols)))
    ax.set_yticks(np.arange(len(df)))
    ax.set_xticklabels(['Playoff', 'Round 2', 'Conf\nFinals', 'SCF', 'Cup', 'Pres\nTrophy'],
                       fontsize=10, fontweight='bold')
    ax.xaxis.tick_top()  # Move x-axis ticks to top

    # Disable grid lines
    ax.grid(False)
    ax.set_frame_on(False)

    # Add team logos on y-axis
    has_logos = False
    for i, team in enumerate(df['Team']):
        logo = get_team_logo(team, zoom=0.04)  # Very small for compact heatmap
        if logo:
            ab = AnnotationBbox(logo, (-0.6, i), frameon=False, xycoords='data',
                               box_alignment=(1, 0.5), clip_on=False)
            ax.add_artist(ab)
            has_logos = True

    # Extend x-axis limits to show logos
    if has_logos:
        ax.set_xlim(-1.0, len(prob_cols) - 0.5)
    else:
        ax.set_xlim(-0.5, len(prob_cols) - 0.5)

    # Set y-axis labels (use team names if logos not available)
    if has_logos:
        ax.set_yticklabels([])  # Hide text labels when using logos
    else:
        ax.set_yticklabels(df['Team'], fontsize=8)

    # Add text annotations
    for i in range(len(df)):
        for j in range(len(prob_cols)):
            value = heatmap_data[i, j]
            # Choose text color based on background
            text_color = 'white' if value > 0.5 else 'black'
            text = ax.text(j, i, f'{value:.1%}', ha='center', va='center',
                          color=text_color, fontsize=7, fontweight='bold')

    # Rotate x-axis labels for better readability
    plt.setp(ax.get_xticklabels(), rotation=0, ha='center')

    # Add title and subtitle using fig-level functions
    fig.suptitle('NHL Playoff Advancement Probabilities', fontsize=16, fontweight='bold', y=0.97)
    fig.text(0.5, 0.935, f'Based on {n_sims:,} simulations',
             ha='center', fontsize=11, style='italic')

    plt.tight_layout(rect=[0, 0, 1, 0.85])
    plt.savefig(output_path, dpi=VIZ_DPI, bbox_inches='tight', facecolor='white')
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
