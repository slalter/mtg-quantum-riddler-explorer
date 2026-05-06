"""Convergence test: run hill-climb from multiple legal starting points.
If they converge to similar lists, that's evidence of a global optimum."""
import random
from optimize import (evaluate, hill_climb_2step, PHELIA_V19, SOURCE_CORKYBOYY,
                       PURE_ENGINE, land_count, is_legal, MAX_LAND_COUNT)

# Pre-make legal versions of decks
def trim_to_legal(deck_def, target_lands=25):
    """Trim land count to target_lands by cutting non-basic lands first."""
    d = dict(deck_def)
    # Add basics if needed (we want ≥4 basics)
    for basic in ("Plains", "Mountain", "Island"):
        if d.get(basic, 0) == 0:
            d[basic] = 1
    while sum(d.get(b, 0) for b in ("Plains", "Mountain", "Island")) < 4 and sum(d.values()) > 60:
        d["Plains"] += 1
        # Find a non-basic land to cut
        for cand in ("Demolition Field", "Field of Ruin", "Sunken Citadel", "Cori Mountain Monastery"):
            if d.get(cand, 0) > 1:
                d[cand] -= 1
                break
        if sum(d.values()) == 60:
            break
    while land_count(d) > target_lands:
        for cand in ("Demolition Field", "Field of Ruin", "Sunken Citadel", "Cori Mountain Monastery"):
            if d.get(cand, 0) >= 2:
                d[cand] -= 1
                # add a generic spell if total drops below 60
                if sum(d.values()) < 60:
                    d["Path to Exile"] = d.get("Path to Exile", 0) + 1
                break
        else:
            break
    return d

# Starting point 1: PHELIA_V19 (already legal)
START_PHELIA = PHELIA_V19

# Starting point 2: Source list (Corkyboyy) — 24 lands, 6 basics, legal
START_SOURCE = SOURCE_CORKYBOYY

# Starting point 3: Pure (25 lands, 6 basics, legal)
START_PURE = PURE_ENGINE

# Starting point 4: minimal/spell-heavy variant
START_MINIMAL = {
    "Quantum Riddler": 4, "Phlage": 3, "Phelia": 2, "Solitude": 2, "White Orchid Phantom": 4,
    "Erode": 4, "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 3, "Wrath of the Skies": 2,  # 36 spells
    "Sacred Foundry": 4, "Hallowed Fountain": 3, "Steam Vents": 1,
    "Scalding Tarn": 4, "Arid Mesa": 4,
    "Field of Ruin": 2, "Demolition Field": 1, "Arena of Glory": 1,
    "Plains": 2, "Mountain": 1, "Island": 1,  # 24 lands, 4 basics
}

# Starting point 5: alternate fetch mix (off-color heavy)
START_ALTFETCH = dict(PHELIA_V19)
# Replace 2 Tarns with Misty Rainforest, 2 Mesas with Wooded Foothills
START_ALTFETCH["Scalding Tarn"] -= 2
START_ALTFETCH["Misty Rainforest"] = 2
START_ALTFETCH["Arid Mesa"] -= 2
START_ALTFETCH["Wooded Foothills"] = 2

starting_points = {
    "PHELIA_V19": START_PHELIA,
    "Source (Corkyboyy)": START_SOURCE,
    "Pure baseline": START_PURE,
    "Minimal": START_MINIMAL,
    "Alt-fetch (off-color)": START_ALTFETCH,
}

if __name__ == "__main__":
    print("Convergence test: 5 starting points → 2-step hill-climb each")
    print("=" * 60)
    for name, start in starting_points.items():
        print(f"\n--- Starting: {name} ---")
        print(f"  Lands: {land_count(start)}  Basics: {sum(start.get(b,0) for b in ('Plains','Mountain','Island'))}")
        print(f"  Total cards: {sum(start.values())}")
        print(f"  Legal: {is_legal(start)}")
        random.seed(42)
        try:
            final, score = hill_climb_2step(name, start, max_iters=2, min_delta=0.4, n_seeds=1, trials=600)
        except Exception as e:
            print(f"  ERROR: {e}")
