"""Full convergence run from multiple starting points under the
current model. Compares hill-climb endpoints to find the global
optimum the model believes in."""
import random
import sys
sys.path.insert(0, "/tmp/mtg-quantum-riddler-explorer/sim")

# Reduce trials for hill-climb speed
import optimize as opt
_orig_evaluate = opt.evaluate
def fast_evaluate(deck_def, weights=opt.WEIGHTS, trials=1500, seed=42, n_seeds=2):
    return _orig_evaluate(deck_def, weights=weights, trials=trials, seed=seed, n_seeds=n_seeds)
opt.evaluate = fast_evaluate

from optimize import hill_climb

# Starting points
START_4_4_1 = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2, "Phlage": 2,
    "Solitude": 2, "Snapcaster Mage": 2, "Erode": 4, "Path to Exile": 4,
    "Cleansing Wildfire": 4, "Price of Freedom": 4, "Galvanic Discharge": 2,
    "Wrath of the Skies": 1,
    "Arid Mesa": 4, "Scalding Tarn": 4, "Sacred Foundry": 4, "Hallowed Fountain": 4,
    "Steam Vents": 1, "Arena of Glory": 1, "Demolition Field": 1, "Field of Ruin": 2,
    "Plains": 2, "Mountain": 1, "Island": 1,
}
START_USER_211 = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2, "Phlage": 2,
    "Solitude": 2, "Snapcaster Mage": 2, "Erode": 4, "Path to Exile": 4,
    "Cleansing Wildfire": 4, "Price of Freedom": 4, "Galvanic Discharge": 2,
    "Wrath of the Skies": 1,
    "Arid Mesa": 4, "Scalding Tarn": 4, "Marsh Flats": 2, "Misty Rainforest": 1,
    "Sacred Foundry": 2, "Hallowed Fountain": 1, "Steam Vents": 1,
    "Meticulous Archive": 1, "Elegant Parlor": 1,
    "Arena of Glory": 1, "Demolition Field": 1, "Field of Ruin": 2,
    "Plains": 2, "Mountain": 1, "Island": 1,
}

starts = [
    ("4-4-1 baseline", START_4_4_1),
    ("USER 2-1-1 + surveil", START_USER_211),
]
finals = []
for name, deck in starts:
    print(f"\n{'='*70}\nStart: {name}\n{'='*70}")
    random.seed(0)
    final, score, hist = hill_climb(name, deck, max_iters=8, min_delta=0.20)
    finals.append((name, score, final))

print("\n\n========== CONVERGENCE SUMMARY ==========")
for name, score, final in finals:
    print(f"\n{name}: final score = {score:.2f}")
    for k, v in sorted(final.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {v} {k}")
