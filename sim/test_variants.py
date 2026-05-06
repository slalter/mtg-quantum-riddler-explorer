"""Test specific variant tunings derived from leave-one-out analysis."""
import random
from optimize import evaluate

PHELIA_V18 = {
    'White Orchid Phantom': 4, 'Phelia': 2, 'Phlage': 2, 'Quantum Riddler': 4, 'Solitude': 2,
    'Erode': 4, 'Path to Exile': 4, 'Galvanic Discharge': 2, 'Cleansing Wildfire': 4,
    'Price of Freedom': 4, 'Wrath of the Skies': 2,
    'Sacred Foundry': 3, 'Scalding Tarn': 4, 'Hallowed Fountain': 3, 'Arid Mesa': 4,
    'Steam Vents': 1, 'Arena of Glory': 3, 'Field of Ruin': 3, 'Demolition Field': 2,
    'Plains': 1, 'Mountain': 1, 'Island': 1,
}

def score(name, deck, n_seeds=5, trials=1500):
    s, _, _ = evaluate(deck, n_seeds=n_seeds, trials=trials)
    print(f"{name:<55} {s:.2f}")
    return s

def variant(base, swaps):
    d = dict(base)
    for cut, add in swaps:
        d[cut] -= 1
        if d[cut] == 0:
            del d[cut]
        d[add] = d.get(add, 0) + 1
    return d

if __name__ == "__main__":
    random.seed(42)
    print("Tested with 5 seeds × 1500 trials each (noise ~±0.3)\n")
    base_score = score("v18 Phelia (baseline)", PHELIA_V18)
    print()

    # Single-card adjustments
    score("v18 +1 Hallowed Fountain -1 Phelia", variant(PHELIA_V18, [("Phelia", "Hallowed Fountain")]))
    score("v18 +1 Sacred Foundry -1 Phelia", variant(PHELIA_V18, [("Phelia", "Sacred Foundry")]))
    score("v18 +1 Hallowed Fountain -1 Phlage", variant(PHELIA_V18, [("Phlage", "Hallowed Fountain")]))
    score("v18 +1 Sacred Foundry -1 Mountain", variant(PHELIA_V18, [("Mountain", "Sacred Foundry")]))
    score("v18 +1 Sacred Foundry -1 Island", variant(PHELIA_V18, [("Island", "Sacred Foundry")]))
    score("v18 +1 Hallowed Fountain -1 Arena of Glory", variant(PHELIA_V18, [("Arena of Glory", "Hallowed Fountain")]))
    # skipping illegal/missing variants
    print()

    # Multi-card combos
    score("v18 -2 Phelia +1 HF +1 SF (cut combo glue)",
          variant(PHELIA_V18, [("Phelia", "Hallowed Fountain"), ("Phelia", "Sacred Foundry")]))
    score("v18 -1 Phelia -1 Phlage +2 Solitude",
          variant(PHELIA_V18, [("Phelia", "Solitude"), ("Phlage", "Solitude")]))
    score("v18 +1 Solitude -1 Galvanic",
          variant(PHELIA_V18, [("Galvanic Discharge", "Solitude")]))
    score("v18 -1 Mountain -1 Island +2 Sacred Foundry",
          variant(PHELIA_V18, [("Mountain", "Sacred Foundry"), ("Island", "Sacred Foundry")]))
    score("v18 -1 Phelia +1 Snapcaster Mage (combo glue)",
          variant(PHELIA_V18, [("Phelia", "Snapcaster Mage")]))
