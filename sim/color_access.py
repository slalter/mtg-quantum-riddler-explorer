"""Color-access curve: P(have W+U+R sources by turn N) per variant."""
import random
from simulate import build_deck, CARDS

VARIANTS = {}
def add_variant(name, deck): VARIANTS[name] = deck

# v19 Phelia legal baseline
add_variant("v19 Phelia", {
    'White Orchid Phantom': 4, 'Phelia': 3, 'Phlage': 3, 'Quantum Riddler': 4,
    'Erode': 4, 'Path to Exile': 3, 'Galvanic Discharge': 4, 'Cleansing Wildfire': 4,
    'Price of Freedom': 4, 'Wrath of the Skies': 2,
    'Sacred Foundry': 2, 'Scalding Tarn': 4, 'Hallowed Fountain': 2, 'Arid Mesa': 4,
    'Steam Vents': 1, 'Arena of Glory': 3, 'Demolition Field': 3, 'Field of Ruin': 2,
    'Plains': 2, 'Mountain': 1, 'Island': 1,
})

# Snapcaster variant
add_variant("Snapcaster variant", {
    'White Orchid Phantom': 4, 'Phelia': 2, 'Phlage': 2, 'Quantum Riddler': 4, 'Solitude': 2,
    'Snapcaster Mage': 2,
    'Erode': 4, 'Path to Exile': 3, 'Galvanic Discharge': 2, 'Cleansing Wildfire': 4,
    'Price of Freedom': 4, 'Wrath of the Skies': 2,
    'Sacred Foundry': 2, 'Scalding Tarn': 4, 'Hallowed Fountain': 2, 'Arid Mesa': 4,
    'Steam Vents': 1, 'Arena of Glory': 3, 'Demolition Field': 3, 'Field of Ruin': 2,
    'Plains': 2, 'Mountain': 1, 'Island': 1,
})

def has_color(land, color):
    """Does this land produce this color (counting fetch targets)?"""
    if land in CARDS and CARDS[land]["land"]:
        produces = CARDS[land]["produces"]
        return color in produces
    return False

# A fetch can produce W if it can find a shock with W (Tarn → HF; Mesa → SF/HF; Strand → SF/HF; etc.)
# For simplicity, treat fetches as having access to any color a shock provides.
FETCH_COLORS = {
    "Scalding Tarn": {"U", "R", "W"},  # Steam Vents (UR), Hallowed Fountain (WU), Sacred Foundry (RW via Mountain in SF type)
    "Arid Mesa": {"R", "W", "U"},
    "Flooded Strand": {"W", "U", "R"},
    "Misty Rainforest": {"U", "W"},  # HF (WU), SV (UR) — only U overlaps both
    "Polluted Delta": {"U", "W", "R"},  # HF (WU), SV (UR)
    "Marsh Flats": {"W", "U", "R"},
    "Wooded Foothills": {"R", "W", "U"},
    "Bloodstained Mire": {"R", "W", "U"},
    "Windswept Heath": {"W", "U", "R"},
}
# Override for fetches: include the colors any reachable shock provides
def land_colors(land):
    if land in FETCH_COLORS:
        return FETCH_COLORS[land]
    if land in CARDS and CARDS[land]["land"]:
        return set(CARDS[land]["produces"]) - {"C"}
    return set()

def simulate_color_access(deck_def, n=5000, max_turn=6):
    deck_list = build_deck(deck_def)
    p_all_three = {t: 0 for t in range(1, max_turn + 1)}
    for _ in range(n):
        random.shuffle(deck_list)
        hand = deck_list[:7]
        library = deck_list[7:]
        in_play = []
        for turn in range(1, max_turn + 1):
            # Draw (skip T1 on the play)
            if turn > 1 and library:
                hand.append(library.pop(0))
            # Play a land — pick one that adds a new color
            have_colors = set().union(*[land_colors(l) for l in in_play]) if in_play else set()
            land_in_hand = [c for c in hand if CARDS[c]["land"]]
            if land_in_hand:
                # Pick land that adds the most colors
                land_in_hand.sort(key=lambda l: len(land_colors(l) - have_colors), reverse=True)
                play = land_in_hand[0]
                in_play.append(play)
                hand.remove(play)
            # Check colors
            colors = set().union(*[land_colors(l) for l in in_play]) if in_play else set()
            if {"W", "U", "R"}.issubset(colors):
                p_all_three[turn] += 1
    return {t: p_all_three[t] / n * 100 for t in p_all_three}

if __name__ == "__main__":
    random.seed(42)
    print(f"{'Variant':<25} {'T1':>6} {'T2':>6} {'T3':>6} {'T4':>6} {'T5':>6} {'T6':>6}")
    for name, deck in VARIANTS.items():
        results = simulate_color_access(deck)
        line = f"{name:<25}"
        for t in range(1, 7):
            line += f" {results[t]:>5.1f}%"
        print(line)
