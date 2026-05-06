"""Leave-one-out marginal value: for each card, remove 1 copy and re-score.
Reveals which copies are providing the least value — candidates for cuts."""
import random
from optimize import evaluate, PHELIA, ROKU, PURE_ENGINE
from simulate import CARDS

PHELIA_V18 = {
    'White Orchid Phantom': 4, 'Phelia': 2, 'Phlage': 2, 'Quantum Riddler': 4, 'Solitude': 2,
    'Erode': 4, 'Path to Exile': 4, 'Galvanic Discharge': 2, 'Cleansing Wildfire': 4,
    'Price of Freedom': 4, 'Wrath of the Skies': 2,
    'Sacred Foundry': 3, 'Scalding Tarn': 4, 'Hallowed Fountain': 3, 'Arid Mesa': 4,
    'Steam Vents': 1, 'Arena of Glory': 3, 'Field of Ruin': 3, 'Demolition Field': 2,
    'Plains': 1, 'Mountain': 1, 'Island': 1,
}

def marginal_analysis(name, deck_def, n_seeds=2, trials=1500):
    print(f"\n=== Leave-one-out marginal value: {name} ===")
    base_score, _, _ = evaluate(deck_def, n_seeds=n_seeds, trials=trials)
    print(f"Baseline score: {base_score:.2f}")
    print()
    print(f"{'Cut card':<35} {'Replace with':<25} {'Δscore':>8}")
    results = []
    # For each card, remove 1 copy, replace with basic Plains as the canonical 'filler'
    for card in deck_def:
        if deck_def[card] == 0:
            continue
        new_def = dict(deck_def)
        new_def[card] -= 1
        if new_def[card] == 0:
            del new_def[card]
        # Replace with the deck's most-common basic
        filler = "Plains"
        new_def[filler] = new_def.get(filler, 0) + 1
        new_score, _, _ = evaluate(new_def, n_seeds=n_seeds, trials=trials)
        delta = new_score - base_score
        results.append((delta, card))
    # Sort: most-negative-delta first (cutting hurt most = high marginal value).
    # Most-positive-delta = card whose removal HELPED the deck (over-included).
    results.sort()
    for delta, card in results:
        marker = " ← over-included" if delta > 0.3 else (" ← critical" if delta < -1.5 else "")
        print(f"  -1 {card:<31} +1 Plains              {delta:+7.2f}{marker}")
    return results

if __name__ == "__main__":
    random.seed(42)
    # marginal_analysis("Phelia v18 optimized", PHELIA_V18)
    marginal_analysis("Roku Hardcast (baseline)", ROKU)
    marginal_analysis("Pure Engine (baseline)", PURE_ENGINE)
