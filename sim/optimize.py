"""Optimization driver: takes a deck list, evaluates it, tries pairwise
swaps, reports which improve the weighted score.

Usage:
    python3 optimize.py [variant_name]

variants: phelia, pure, roku
"""
import sys
import random
from simulate import simulate, build_deck, CARDS, PHELIA, PURE_ENGINE, ROKU, SOURCE_CORKYBOYY

# Importance weights for the weighted score (must match webapp's METRIC_IMPORTANCE)
WEIGHTS = {
    "erode_T1":          3,
    "path_T1":           3,
    "galvanic_T1":       2,
    "phantom_T2":        1,
    "phantom_T3":        3,
    "phelia_T2":         2,
    "phelia_T3":         2,
    "wildfire_T2":       4,
    "pof_T2":            4,
    "phlage_T3_removal": 3,
    "warp_qr_T2":        3,
    "warp_qr_T3":        4,
    "hardcast_qr_T5":    2,
    "hardcast_qr_T6":    2,
    "wos_T4":            2,
    "roku_T4":           1,
    "phlage_escape_T7":  2,  # bumped from 1 — it's a real subplan now
}

# Conditional applicability: if the metric's relevant card isn't in the deck, skip it
METRIC_REQUIRES = {
    "erode_T1": "Erode",
    "path_T1": "Path to Exile",
    "galvanic_T1": "Galvanic Discharge",
    "phantom_T2": "White Orchid Phantom",
    "phantom_T3": "White Orchid Phantom",
    "phelia_T2": "Phelia",
    "phelia_T3": "Phelia",
    "wildfire_T2": "Cleansing Wildfire",
    "pof_T2": "Price of Freedom",
    "phlage_T3_removal": "Phlage",
    "warp_qr_T2": "Quantum Riddler",
    "warp_qr_T3": "Quantum Riddler",
    "hardcast_qr_T5": "Quantum Riddler",
    "hardcast_qr_T6": "Quantum Riddler",
    "wos_T4": "Wrath of the Skies",
    "roku_T4": "The Legend of Roku",
    "phlage_escape_T7": "Phlage",
}

def evaluate(deck_def, weights=WEIGHTS, trials=8000, seed=42, n_seeds=1):
    """Return (composite_score, parts_dict, raw_sim_result).
    Multi-seed: averages over n_seeds different RNG seeds for noise reduction."""
    from score import composite_score
    deck = build_deck(deck_def)
    scores, parts_list = [], []
    last_res = None
    for s in range(n_seeds):
        random.seed(seed + s * 1000)
        res = simulate(deck, trials=trials)
        score, parts = composite_score(deck_def, res)
        scores.append(score)
        parts_list.append(parts)
        last_res = res
    avg_score = sum(scores) / len(scores)
    avg_parts = {k: (sum(p[k] for p in parts_list) / len(parts_list)
                     if isinstance(parts_list[0][k], (int, float)) else parts_list[0][k])
                 for k in parts_list[0]}
    return avg_score, avg_parts, last_res

def deck_total(deck_def):
    return sum(deck_def.values())

# Catalog of plausible swap candidates for each variant
# (cut_card, add_card)
SWAP_CANDIDATES = [
    # Threat consolidation
    ("Phlage", "Phelia"),
    ("Phelia", "Phlage"),
    ("White Orchid Phantom", "Phelia"),
    ("White Orchid Phantom", "Phlage"),
    ("Quantum Riddler", "Phelia"),  # consider cutting QR for more threats
    ("Phelia", "Quantum Riddler"),
    # Removal tuning
    ("Path to Exile", "Erode"),
    ("Erode", "Path to Exile"),
    ("Galvanic Discharge", "Path to Exile"),
    ("Path to Exile", "Galvanic Discharge"),
    ("Galvanic Discharge", "Erode"),
    ("Wrath of the Skies", "Galvanic Discharge"),
    # Engine tuning
    ("Cleansing Wildfire", "Price of Freedom"),
    ("Price of Freedom", "Cleansing Wildfire"),
    # Mana base swaps — better blue
    ("Demolition Field", "Hallowed Fountain"),
    ("Demolition Field", "Steam Vents"),
    ("Demolition Field", "Scalding Tarn"),
    ("Field of Ruin", "Hallowed Fountain"),
    ("Field of Ruin", "Scalding Tarn"),
    ("Plains", "Hallowed Fountain"),
    ("Plains", "Island"),
    ("Plains", "Mountain"),
    # Mana base — better Phlage haste
    ("Mountain", "Arena of Glory"),
    ("Sacred Foundry", "Arena of Glory"),
    # Mana base — Phelia variant has 1 of each basic; consider more lands
    ("Demolition Field", "Sacred Foundry"),
    ("Field of Ruin", "Sacred Foundry"),
    ("Mountain", "Sacred Foundry"),
    # Add fetches if not max
    ("Sacred Foundry", "Scalding Tarn"),
    ("Hallowed Fountain", "Scalding Tarn"),
    # Cut weakest finishers
    ("Wrath of God", "Wrath of the Skies"),
    ("The Legend of Roku", "Quantum Riddler"),
    ("The Legend of Roku", "Phelia"),
    # Add Solitude — combos with Phelia per user feedback
    ("Wrath of the Skies", "Solitude"),
    ("Wrath of God", "Solitude"),
    ("Galvanic Discharge", "Solitude"),
    ("White Orchid Phantom", "Solitude"),
    ("Phlage", "Solitude"),
    ("Phelia", "Solitude"),
    # Add Cori Mountain Monastery — 1-of late-game value
    ("Mountain", "Cori Mountain Monastery"),
    ("Plains", "Cori Mountain Monastery"),
    ("Demolition Field", "Cori Mountain Monastery"),
    ("Field of Ruin", "Cori Mountain Monastery"),
    # Add Sunken Citadel — mana doubler for land abilities
    ("Plains", "Sunken Citadel"),
    ("Mountain", "Sunken Citadel"),
    ("Island", "Sunken Citadel"),
    ("Demolition Field", "Sunken Citadel"),
    ("Field of Ruin", "Sunken Citadel"),
    # And the inverse direction: too many of these probably bad
    ("Sunken Citadel", "Sacred Foundry"),
    ("Cori Mountain Monastery", "Mountain"),
    # Off-color fetches — 1-of considerations for additional fetch density
    ("Demolition Field", "Misty Rainforest"),
    ("Field of Ruin", "Misty Rainforest"),
    ("Plains", "Marsh Flats"),
    ("Mountain", "Bloodstained Mire"),
    ("Plains", "Windswept Heath"),
    ("Demolition Field", "Polluted Delta"),
    # Shock-count tightening: cut redundant shocks (4-4-1 → 2-2-1) by
    # swapping into off-color fetches that reach those shocks via type-line.
    # Adding both directions so the climb can move freely.
    ("Sacred Foundry", "Marsh Flats"),
    ("Sacred Foundry", "Polluted Delta"),
    ("Sacred Foundry", "Misty Rainforest"),
    ("Hallowed Fountain", "Marsh Flats"),
    ("Hallowed Fountain", "Misty Rainforest"),
    ("Hallowed Fountain", "Polluted Delta"),
    ("Sacred Foundry", "Steam Vents"),
    ("Hallowed Fountain", "Steam Vents"),
    ("Sacred Foundry", "Hallowed Fountain"),
    ("Hallowed Fountain", "Sacred Foundry"),
    # Reverse direction (re-add a shock if dropped too far)
    ("Marsh Flats", "Sacred Foundry"),
    ("Misty Rainforest", "Hallowed Fountain"),
    ("Polluted Delta", "Hallowed Fountain"),
    # Basic vs off-color fetch trade-off
    ("Plains", "Misty Rainforest"),
    ("Mountain", "Marsh Flats"),
    ("Island", "Marsh Flats"),
    ("Island", "Polluted Delta"),
    # Surveil duals (MKM): basic-typed, ETB tapped only as 4th+ land,
    # no life cost. Cut shocks for them to save life.
    ("Sacred Foundry", "Meticulous Archive"),
    ("Sacred Foundry", "Elegant Parlor"),
    ("Hallowed Fountain", "Meticulous Archive"),
    ("Hallowed Fountain", "Thundering Falls"),
    ("Steam Vents", "Thundering Falls"),
    ("Plains", "Meticulous Archive"),
    ("Plains", "Elegant Parlor"),
    ("Island", "Meticulous Archive"),
    ("Island", "Thundering Falls"),
    ("Mountain", "Elegant Parlor"),
    ("Mountain", "Thundering Falls"),
    # Reverse direction
    ("Meticulous Archive", "Sacred Foundry"),
    ("Elegant Parlor", "Sacred Foundry"),
    ("Thundering Falls", "Steam Vents"),
    # Fast lands (Spirebluff Canal cycle): not basic-typed (not fetchable
    # by basic-fetches) but ETB untapped early with no life cost.
    ("Sacred Foundry", "Inspiring Vantage"),
    ("Hallowed Fountain", "Seachrome Coast"),
    ("Steam Vents", "Spirebluff Canal"),
    ("Plains", "Inspiring Vantage"),
    ("Plains", "Seachrome Coast"),
    ("Island", "Seachrome Coast"),
    ("Island", "Spirebluff Canal"),
    ("Mountain", "Inspiring Vantage"),
    ("Mountain", "Spirebluff Canal"),
]

def run_optimization(name, deck_def, max_swaps=None):
    candidates = SWAP_CANDIDATES if max_swaps is None else SWAP_CANDIDATES[:max_swaps]
    base_score, base_contribs, base_res = evaluate(deck_def)
    print(f"\n{'='*60}\nOptimizing: {name}")
    print(f"Total cards: {deck_total(deck_def)}")
    print(f"Base score: {base_score:.2f}")
    print(f"{'='*60}")

    # Try each swap
    results = []
    for cut, add in candidates:
        if deck_def.get(cut, 0) <= 0:
            continue
        new_def = dict(deck_def)
        new_def[cut] -= 1
        if new_def[cut] == 0:
            del new_def[cut]
        new_def[add] = new_def.get(add, 0) + 1
        try:
            new_score, _, _ = evaluate(new_def, trials=6000)
        except Exception as e:
            continue
        delta = new_score - base_score
        results.append((delta, cut, add, new_score))

    results.sort(reverse=True)
    print(f"\nTop 10 swaps (positive deltas only):")
    print(f"  {'Δscore':>8}  {'cut':<28}{'→ add':<28}{'new score':>10}")
    n_shown = 0
    for delta, cut, add, ns in results:
        if delta <= 0:
            continue
        print(f"  {delta:+8.2f}  -1 {cut:<25}+1 {add:<25}{ns:>10.2f}")
        n_shown += 1
        if n_shown >= 10:
            break

    print(f"\nWorst 5 swaps (negative deltas):")
    for delta, cut, add, ns in results[-5:]:
        print(f"  {delta:+8.2f}  -1 {cut:<25}+1 {add:<25}{ns:>10.2f}")

    return base_score, results

BASIC_LANDS = {"Plains", "Mountain", "Island", "Swamp", "Forest"}

# Source list reference: Corkyboyy WR has 24 lands. User allows +1 = 25 max.
SOURCE_LAND_COUNT = 24
MAX_LAND_COUNT = SOURCE_LAND_COUNT + 1  # 25

# Pre-constrained Phelia v19 baseline: 25 lands, 4 basics (legal under new rules).
# Adjusted from PHELIA: -1 Demolition Field, -1 Field of Ruin, +1 Plains, +1 Path to Exile
PHELIA_V19 = {
    "White Orchid Phantom": 4, "Phelia": 3, "Phlage": 3, "Quantum Riddler": 4,
    "Erode": 4, "Path to Exile": 3, "Galvanic Discharge": 4, "Cleansing Wildfire": 4,
    "Price of Freedom": 4, "Wrath of the Skies": 2,
    "Scalding Tarn": 4, "Arid Mesa": 4, "Sacred Foundry": 2, "Hallowed Fountain": 2,
    "Steam Vents": 1, "Arena of Glory": 3, "Demolition Field": 3, "Field of Ruin": 2,
    "Plains": 2, "Mountain": 1, "Island": 1,
}

def is_land_card(card):
    from simulate import CARDS
    return card in CARDS and CARDS[card].get("land", False)

def land_count(deck_def):
    return sum(qty for c, qty in deck_def.items() if is_land_card(c))

def is_legal(deck_def):
    """Modern legality: max 4 of any non-basic card; basics unlimited.
    Plus: land count must be ≤ MAX_LAND_COUNT (source+1)."""
    for k, v in deck_def.items():
        if v > 4 and k not in BASIC_LANDS:
            return False
    if land_count(deck_def) > MAX_LAND_COUNT:
        return False
    return True

def is_legal_swap(deck_def, cut, add):
    """Spell-for-spell or land-for-land only (manabase locked)."""
    if is_land_card(cut) != is_land_card(add):
        return False
    return True

def hill_climb_2step(name, deck_def, max_iters=4, min_delta=0.4, n_seeds=3, trials=2000):
    """2-step lookahead hill-climb. At each step, try (cut1+add1, cut2+add2)
    pairs and apply the joint best. Multi-seed averaged for noise reduction."""
    print(f"\n{'='*60}\n2-step hill-climb: {name}\n{'='*60}")
    current = dict(deck_def)
    base_score, _, _ = evaluate(current, n_seeds=n_seeds, trials=trials)
    print(f"Start score (avg of {n_seeds} seeds): {base_score:.2f}")

    for step in range(max_iters):
        best = None
        for c1, a1 in SWAP_CANDIDATES:
            if current.get(c1, 0) <= 0:
                continue
            mid = dict(current)
            mid[c1] -= 1
            if mid[c1] == 0:
                del mid[c1]
            mid[a1] = mid.get(a1, 0) + 1
            if not is_legal(mid):
                continue
            for c2, a2 in SWAP_CANDIDATES:
                if mid.get(c2, 0) <= 0:
                    continue
                final = dict(mid)
                final[c2] -= 1
                if final[c2] == 0:
                    del final[c2]
                final[a2] = final.get(a2, 0) + 1
                if not is_legal(final):
                    continue
                try:
                    new_score, _, _ = evaluate(final, n_seeds=n_seeds, trials=trials)
                except Exception:
                    continue
                delta = new_score - base_score
                if best is None or delta > best[0]:
                    best = (delta, c1, a1, c2, a2, new_score, final)

        if best is None or best[0] < min_delta:
            print(f"  Step {step+1}: no 2-step improvement >= {min_delta}; stopping.")
            break
        delta, c1, a1, c2, a2, new_score, new_def = best
        print(f"  Step {step+1}: -1 {c1:<22} +1 {a1:<22}, then -1 {c2:<22} +1 {a2:<22}  Δ={delta:+.2f}  → {new_score:.2f}")
        current = new_def
        base_score = new_score

    print(f"\nFinal score: {base_score:.2f}")
    print("Final list:")
    for k, v in sorted(current.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {v} {k}")
    return current, base_score

def hill_climb(name, deck_def, max_iters=8, min_delta=0.4):
    """Greedy hill-climb: at each step, apply the best single swap.
    Respects Modern's 4-of rule (basics unlimited)."""
    print(f"\n{'='*60}\nHill-climb: {name}\n{'='*60}")
    current = dict(deck_def)
    base_score, _, _ = evaluate(current)
    print(f"Start score: {base_score:.2f}  (cards: {deck_total(current)})")

    history = [(base_score, "(start)")]
    for step in range(max_iters):
        best = None
        for cut, add in SWAP_CANDIDATES:
            if current.get(cut, 0) <= 0:
                continue
            new_def = dict(current)
            new_def[cut] -= 1
            if new_def[cut] == 0:
                del new_def[cut]
            new_def[add] = new_def.get(add, 0) + 1
            if not is_legal(new_def):
                continue
            if not is_legal_swap(current, cut, add):
                continue
            try:
                new_score, _, _ = evaluate(new_def, trials=6000)
            except Exception:
                continue
            delta = new_score - base_score
            if best is None or delta > best[0]:
                best = (delta, cut, add, new_score, new_def)

        if best is None or best[0] < min_delta:
            print(f"  Step {step+1}: no improvement >= {min_delta}; stopping.")
            break
        delta, cut, add, new_score, new_def = best
        print(f"  Step {step+1}: -1 {cut:<25} +1 {add:<25} Δ={delta:+.2f}  → {new_score:.2f}")
        current = new_def
        base_score = new_score
        history.append((new_score, f"-1 {cut} +1 {add}"))

    print(f"\nFinal score: {base_score:.2f}")
    print(f"Final list:")
    for k, v in sorted(current.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {v} {k}")
    return current, base_score, history

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "phelia"
    decks = {"phelia": ("Phelia Riddler", PHELIA), "pure": ("Pure Engine", PURE_ENGINE), "roku": ("Roku Hardcast", ROKU), "source": ("Source: Corkyboyy", SOURCE_CORKYBOYY)}
    if target == "all":
        for k, (n, d) in decks.items():
            run_optimization(n, d)
    elif target == "climb":
        which = sys.argv[2] if len(sys.argv) > 2 else "phelia"
        n, d = decks[which]
        hill_climb(n, d)
    else:
        n, d = decks[target]
        run_optimization(n, d)
