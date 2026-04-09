"""
Analyze why OT games are never the most common score outcome.
This script demonstrates the statistical reality of score distributions.
"""
import numpy as np
from collections import Counter

np.random.seed(42)

# Simulate what the model does
home_xg = 3.5
away_xg = 3.5
n_sims = 100000

print(f"Simulating {n_sims:,} games with home_xg={home_xg}, away_xg={away_xg}")
print("=" * 70)

# Track both the "model's way" and "regulation score + win_type"
model_scores = []  # How the model currently tracks (final score with OT goal added)
reg_scores_with_type = []  # Regulation score + how game ended

for _ in range(n_sims):
    hg = np.random.poisson(home_xg)
    ag = np.random.poisson(away_xg)

    if hg == ag:
        # Game goes to OT - current model adds +1 goal to winner
        if np.random.rand() < 0.5:  # Home wins OT
            model_scores.append((hg + 1, ag, 'OT'))
            reg_scores_with_type.append((hg, ag, 'OT', 'home'))
        else:  # Away wins OT
            model_scores.append((hg, ag + 1, 'OT'))
            reg_scores_with_type.append((hg, ag, 'OT', 'away'))
    else:
        model_scores.append((hg, ag, 'REG'))
        reg_scores_with_type.append((hg, ag, 'REG', 'home' if hg > ag else 'away'))

# Current model's tracking method
model_counts = Counter(model_scores)
print("\n1. CURRENT MODEL TRACKING (what you see now)")
print("-" * 50)
print("Top 15 most common outcomes:")
for i, (score, count) in enumerate(model_counts.most_common(15), 1):
    pct = count / n_sims * 100
    win_type = score[2]
    print(f"  {i:2}. {score[0]}-{score[1]} ({win_type}): {count:,} ({pct:.2f}%)")

# Check how many OT games in top 15
ot_in_top15 = sum(1 for score, _ in model_counts.most_common(15) if score[2] != 'REG')
print(f"\nOT/SO games in top 15: {ot_in_top15}")

# What if we tracked regulation score instead?
print("\n2. ALTERNATIVE: Track REGULATION score + win_type")
print("-" * 50)
reg_counts = Counter((h, a, wt) for h, a, wt, _ in reg_scores_with_type)
print("Top 15 most common outcomes (by regulation score):")
for i, (score, count) in enumerate(reg_counts.most_common(15), 1):
    pct = count / n_sims * 100
    win_type = score[2]
    print(f"  {i:2}. {score[0]}-{score[1]} ({win_type}): {count:,} ({pct:.2f}%)")

# Show the OT breakdown
print("\n3. OT GAME ANALYSIS")
print("-" * 50)
total_ot = sum(1 for s in model_scores if s[2] != 'REG')
print(f"Total OT/SO games: {total_ot:,} ({total_ot/n_sims*100:.1f}%)")

# Most common tied regulation scores
tied_regs = [(h, a) for h, a, wt, _ in reg_scores_with_type if wt != 'REG']
tied_counts = Counter(tied_regs)
print("\nMost common regulation ties that went to OT:")
for (h, a), count in tied_counts.most_common(5):
    pct = count / n_sims * 100
    # This count gets SPLIT between home OT win and away OT win
    print(f"  {h}-{h}: {count:,} ({pct:.2f}%) - split into two outcomes in current model")

print("\n4. THE PROBLEM EXPLAINED")
print("-" * 50)
print("""
When a 3-3 regulation tie occurs (say, 6% of games), the current model:
  - Records (4, 3, 'OT') if home wins OT (~3% of all games)
  - Records (3, 4, 'OT') if away wins OT (~3% of all games)

Meanwhile, a (4, 3, 'REG') outcome might occur 4-5% of all games directly.

So (4, 3, 'REG') at ~4.5% beats (4, 3, 'OT') at ~3% every time.

This is why you NEVER see OT as the most common outcome - it's mathematically
impossible unless ties are MORE common than any single non-tied score.
""")

print("\n5. POSSIBLE FIXES")
print("-" * 50)
print("""
Option A: Show "most common FINAL score" (combine REG + OT)
  - Group (4, 3, 'REG') and (4, 3, 'OT') together
  - Then check if OT contributed significantly to that score

Option B: Show "most common REGULATION score" + how game likely ended
  - Track regulation score before OT goal is added
  - If most common is a tie, show it with (OT) notation

Option C: Show TWO predictions
  - "Most likely regulation outcome: 4-3"
  - "Most likely OT scenario: 3-3 (OT)" if ties are common enough
""")
