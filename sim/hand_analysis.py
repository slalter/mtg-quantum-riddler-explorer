"""Hand-distribution analysis: sample opening hands from a deck and categorize.

Identifies common pathologies:
  - mulligan-keep (2-4 lands)
  - mana flood (≥5 lands)
  - mana screw (0-1 lands)
  - color-screw (only 1 distinct color in lands)
  - all-engine no-removal (no Erode/Path/Galvanic/Wildfire/PoF/Phantom for opening turns)
  - QR-flood (≥2 Quantum Riddlers in opening 7)
  - solitude-no-white (Solitude in hand, no other white card)
  - phlage-pre-T3 (Phlage in opening — has to wait for mana)
  - phelia-no-target (Phelia in opening, no good blink target in hand)
"""
import random
from collections import Counter
from simulate import build_deck, CARDS, PHELIA, ROKU, PURE_ENGINE

LAND_NAMES = {name for name, c in CARDS.items() if c["land"]}
BASIC_LANDS = {"Plains", "Mountain", "Island"}
COLORS = {"W", "U", "R"}
ENGINE_OPENERS = {"Erode", "Path to Exile", "Galvanic Discharge", "Cleansing Wildfire", "Price of Freedom", "White Orchid Phantom"}
WHITE_CARDS = {"Erode", "Path to Exile", "Cleansing Wildfire", "Price of Freedom", "Phelia", "White Orchid Phantom",
               "Solitude", "Ephemerate", "Wrath of the Skies", "Wrath of God", "Phlage"}
PHELIA_TARGETS = {"Quantum Riddler", "White Orchid Phantom", "Solitude", "Snapcaster Mage"}

def hand_colors(hand):
    """Set of colors producible by lands in hand."""
    out = set()
    for c in hand:
        if not CARDS[c]["land"]: continue
        out |= set(CARDS[c]["produces"]) & COLORS
    return out

def categorize_hand(hand):
    cats = []
    lands = [c for c in hand if CARDS[c]["land"]]
    n_lands = len(lands)
    n_basics = sum(1 for c in lands if c in BASIC_LANDS)
    cats.append(f"lands={n_lands}")
    cats.append(f"basics={n_basics}")

    if 2 <= n_lands <= 4:
        cats.append("KEEP_lands")
    elif n_lands <= 1:
        cats.append("MANA_SCREW")
    else:
        cats.append("MANA_FLOOD")

    colors = hand_colors(hand)
    cats.append(f"colors={len(colors)}")
    if len(colors) <= 1:
        cats.append("COLOR_SCREW")

    if not any(c in ENGINE_OPENERS for c in hand):
        cats.append("NO_ENGINE_OPENER")

    qrs = sum(1 for c in hand if c == "Quantum Riddler")
    if qrs >= 2:
        cats.append(f"QR_FLOOD_{qrs}")

    if "Solitude" in hand:
        other_white = sum(1 for c in hand if c in WHITE_CARDS and c != "Solitude")
        if other_white == 0:
            cats.append("SOLITUDE_NO_EVOKE")

    if "Phlage" in hand:
        cats.append("PHLAGE_OPENING")  # requires T3 hardcast; can be slow

    if "Phelia" in hand:
        targets = sum(1 for c in hand if c in PHELIA_TARGETS)
        if targets == 0:
            cats.append("PHELIA_NO_TARGET")

    return cats

def analyze_deck(name, deck_def, n=5000):
    deck_list = build_deck(deck_def)
    counter = Counter()
    print(f"\n=== {name} ({n} opening hands) ===")
    for _ in range(n):
        random.shuffle(deck_list)
        hand = deck_list[:7]
        for cat in categorize_hand(hand):
            counter[cat] += 1
    print(f"{'Category':<30} {'Count':>8} {'Pct':>7}")
    # Sort by count
    for cat, count in sorted(counter.items(), key=lambda x: -x[1]):
        if cat.startswith(("lands=", "basics=", "colors=")):
            continue  # skip the histograms; we'll show separately
        pct = count / n * 100
        print(f"{cat:<30} {count:>8} {pct:>6.1f}%")
    # Distribution histograms
    lands_dist = Counter(int(k.split("=")[1]) for k in counter if k.startswith("lands="))
    basics_dist = Counter(int(k.split("=")[1]) for k in counter if k.startswith("basics="))
    colors_dist = Counter(int(k.split("=")[1]) for k in counter if k.startswith("colors="))
    # Compute properly from per-hand counts
    # (Since we counted per-hand cats, the dist is just the appearances of each value)
    return counter

if __name__ == "__main__":
    random.seed(42)
    PHELIA_V18 = {
        'White Orchid Phantom': 4, 'Phelia': 2, 'Phlage': 2, 'Quantum Riddler': 4, 'Solitude': 2,
        'Erode': 4, 'Path to Exile': 4, 'Galvanic Discharge': 2, 'Cleansing Wildfire': 4,
        'Price of Freedom': 4, 'Wrath of the Skies': 2,
        'Sacred Foundry': 3, 'Scalding Tarn': 4, 'Hallowed Fountain': 3, 'Arid Mesa': 4,
        'Steam Vents': 1, 'Arena of Glory': 3, 'Field of Ruin': 3, 'Demolition Field': 2,
        'Plains': 1, 'Mountain': 1, 'Island': 1,
    }
    analyze_deck("Phelia Riddler v18 (optimized)", PHELIA_V18)
    analyze_deck("Phelia Riddler (baseline)", PHELIA)
    analyze_deck("Roku Hardcast (baseline)", ROKU)
    analyze_deck("Pure Engine (baseline)", PURE_ENGINE)
