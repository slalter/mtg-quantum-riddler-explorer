"""Pareto frontier: project decks onto (power, castability, mana_efficiency, stuff_to_do)
4D space. Identify decks that aren't dominated on all 4 axes."""
import random
from optimize import evaluate, PHELIA_V19, SOURCE_CORKYBOYY, PURE_ENGINE, ROKU

# Build a sample of variants to project
VARIANTS = {
    "Source (Corkyboyy)": SOURCE_CORKYBOYY,
    "Phelia v19 (legal baseline)": PHELIA_V19,
    "Pure baseline": PURE_ENGINE,
    "Roku baseline": ROKU,
}

# Add some hill-climbed and synthetic variants
VARIANTS["Phelia + 4 Solitude (max combo)"] = {
    'White Orchid Phantom': 4, 'Phelia': 3, 'Phlage': 2, 'Quantum Riddler': 4, 'Solitude': 4,
    'Erode': 4, 'Path to Exile': 3, 'Galvanic Discharge': 2, 'Cleansing Wildfire': 4,
    'Price of Freedom': 4, 'Wrath of the Skies': 1,  # 35 spells
    'Sacred Foundry': 2, 'Scalding Tarn': 4, 'Hallowed Fountain': 2, 'Arid Mesa': 4,
    'Steam Vents': 1, 'Arena of Glory': 3, 'Demolition Field': 3, 'Field of Ruin': 2,
    'Plains': 2, 'Mountain': 1, 'Island': 1,
}

VARIANTS["Heavy Phlage (4 Phlage, 0 Phelia)"] = {
    'White Orchid Phantom': 4, 'Phlage': 4, 'Quantum Riddler': 4, 'Solitude': 3,
    'Erode': 4, 'Path to Exile': 4, 'Galvanic Discharge': 3, 'Cleansing Wildfire': 4,
    'Price of Freedom': 4, 'Wrath of the Skies': 1,
    'Sacred Foundry': 3, 'Scalding Tarn': 4, 'Hallowed Fountain': 2, 'Arid Mesa': 4,
    'Steam Vents': 1, 'Arena of Glory': 3, 'Demolition Field': 3, 'Field of Ruin': 2,
    'Plains': 2, 'Mountain': 1, 'Island': 1,
}

VARIANTS["Snapcaster + Counterspell flex"] = {
    'White Orchid Phantom': 4, 'Phelia': 2, 'Phlage': 2, 'Quantum Riddler': 4, 'Solitude': 2,
    'Snapcaster Mage': 2,
    'Erode': 4, 'Path to Exile': 3, 'Galvanic Discharge': 2, 'Cleansing Wildfire': 4,
    'Price of Freedom': 4, 'Wrath of the Skies': 2,  # 35 spells
    'Sacred Foundry': 2, 'Scalding Tarn': 4, 'Hallowed Fountain': 2, 'Arid Mesa': 4,
    'Steam Vents': 1, 'Arena of Glory': 3, 'Demolition Field': 3, 'Field of Ruin': 2,
    'Plains': 2, 'Mountain': 1, 'Island': 1,
}

if __name__ == "__main__":
    print(f"{'Variant':<48} {'Comp':>6} {'Power':>6} {'Cast':>6} {'Eff':>6} {'Stuff':>6}")
    print("-" * 90)
    results = {}
    for name, deck in VARIANTS.items():
        random.seed(42)
        try:
            score, parts, _ = evaluate(deck, n_seeds=2, trials=1500)
            results[name] = parts
            print(f"{name:<48} {score:>6.2f} {parts['power']:>6.2f} {parts['castability']:>6.2f} {parts['mana_efficiency']:>6.2f} {parts['stuff_to_do']:>6.2f}")
        except ValueError as e:
            print(f"{name:<48} ERROR: {e}")

    # Pareto frontier: a deck is Pareto-optimal if no other deck dominates on all 4 axes.
    print()
    print("Pareto-optimal decks (not dominated on all 4 axes):")
    for n1, p1 in results.items():
        dominated = False
        for n2, p2 in results.items():
            if n1 == n2:
                continue
            if (p2["power"] >= p1["power"] and
                p2["castability"] >= p1["castability"] and
                p2["mana_efficiency"] >= p1["mana_efficiency"] and
                p2["stuff_to_do"] >= p1["stuff_to_do"] and
                (p2["power"] > p1["power"] or
                 p2["castability"] > p1["castability"] or
                 p2["mana_efficiency"] > p1["mana_efficiency"] or
                 p2["stuff_to_do"] > p1["stuff_to_do"])):
                dominated = True
                break
        if not dominated:
            print(f"  ✓ {n1}")
