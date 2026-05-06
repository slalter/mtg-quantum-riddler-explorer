"""Hill-climb from a 4-4-1 starting point. Verifies the model converges
to a 2-2-1 (or 2-1-1) shock split with off-color fetches and surveil
duals once color_reliability + life_safety are in the score."""
import random
import sys
sys.path.insert(0, "/tmp/mtg-quantum-riddler-explorer/sim")
from optimize import hill_climb_2step, hill_climb, evaluate

# Starting point: deliberately bad manabase — 4 SF + 4 HF + 1 SV with
# all the spells from the v20 HYBRID. The optimizer should find the
# improvement path toward 2-2-1 + surveil duals.
START_4_4_1 = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2,
    "Phlage": 2, "Solitude": 2, "Snapcaster Mage": 2, "Erode": 4,
    "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 2, "Wrath of the Skies": 1,
    "Arid Mesa": 4, "Scalding Tarn": 4,
    "Sacred Foundry": 4, "Hallowed Fountain": 4, "Steam Vents": 1,
    "Arena of Glory": 1, "Demolition Field": 1, "Field of Ruin": 2,
    "Plains": 2, "Mountain": 1, "Island": 1,
}
assert sum(START_4_4_1.values()) == 60, f"start={sum(START_4_4_1.values())}"

print("=" * 60)
print("Hill-climb from 4-4-1 baseline (the original HYBRID manabase)")
print("=" * 60)
random.seed(0)
# Use lower trials for hill-climb steps to keep runtime manageable.
# Patching evaluate to use fewer trials:
import optimize
_orig_evaluate = optimize.evaluate
def fast_evaluate(deck_def, weights=optimize.WEIGHTS, trials=1500, seed=42, n_seeds=1):
    return _orig_evaluate(deck_def, weights=weights, trials=trials, seed=seed, n_seeds=n_seeds)
optimize.evaluate = fast_evaluate

final, score, hist = hill_climb("4-4-1 → ???", START_4_4_1, max_iters=10, min_delta=0.15)
print()
print(f"Final score: {score:.2f}")
print("Climb history:")
for s, action in hist:
    print(f"  {s:.2f}  {action}")
