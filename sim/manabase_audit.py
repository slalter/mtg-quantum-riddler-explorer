"""Manabase audit per user feedback:
'Why 4 Sacred Foundry and 4 Hallowed Fountain? Usually 2-2-1 or 2-1-1 between
the shocks. Fetchlands functionally get all colors, and we can include
off-color fetches like marsh flats.'

Tests:
  HYBRID_25_44     : original 25 lands, 4-4-1 shocks, no off-color fetches
  HYBRID_25_221    : 25 lands, 2-2-1 shocks + 2 Marsh Flats + 1 Misty Rainforest
  HYBRID_24_221    : 24 lands, 2-2-1 shocks + 2 off-color fetches, +1 spell
  HYBRID_24_211    : 24 lands, 2-1-1 shocks + 3 off-color fetches, +1 spell
  HYBRID_25_221_3P : 25 lands, 2-2-1 shocks + off-color, with 3 Phlage
"""
import random
import sys
sys.path.insert(0, "/tmp/mtg-quantum-riddler-explorer/sim")
from simulate import simulate, build_deck
from score import composite_score
from color_access import land_colors
from simulate import CARDS

def deck_total(d): return sum(d.values())
def land_total(d):
    return sum(qty for c, qty in d.items() if c in CARDS and CARDS[c]["land"])

# Reference: original HYBRID with 4-4-1 shocks (25 lands)
HYBRID_25_44 = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2,
    "Phlage": 2, "Solitude": 2, "Snapcaster Mage": 2, "Erode": 4,
    "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 2, "Wrath of the Skies": 1,
    "Arid Mesa": 4, "Scalding Tarn": 4, "Sacred Foundry": 4,
    "Hallowed Fountain": 4, "Steam Vents": 1, "Arena of Glory": 1,
    "Demolition Field": 1, "Field of Ruin": 2,
    "Plains": 2, "Mountain": 1, "Island": 1,
}

# 25 lands, 2-2-1 shocks: dropped 2 SF + 2 HF, replaced with 2 Marsh Flats
# (W/B → finds SF, HF) + 1 Misty Rainforest (G/U → finds HF, SV) + 1 basic.
# Same 25-land count, same spells.
HYBRID_25_221 = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2,
    "Phlage": 2, "Solitude": 2, "Snapcaster Mage": 2, "Erode": 4,
    "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 2, "Wrath of the Skies": 1,
    # Lands: 4 + 4 in-color fetches + 3 off-color fetches + 5 shocks-utility + basics
    "Arid Mesa": 4, "Scalding Tarn": 4,
    "Marsh Flats": 2, "Misty Rainforest": 1,
    "Sacred Foundry": 2, "Hallowed Fountain": 2, "Steam Vents": 1,
    "Arena of Glory": 1, "Demolition Field": 1, "Field of Ruin": 2,
    "Plains": 2, "Mountain": 1, "Island": 2,
}

# 24 lands, 2-2-1 shocks: drop one basic. Free spell slot → +1 Phlage to make 3.
HYBRID_24_221_3P = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2,
    "Phlage": 3, "Solitude": 2, "Snapcaster Mage": 2, "Erode": 4,
    "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 2, "Wrath of the Skies": 1,
    "Arid Mesa": 4, "Scalding Tarn": 4,
    "Marsh Flats": 2, "Misty Rainforest": 1,
    "Sacred Foundry": 2, "Hallowed Fountain": 2, "Steam Vents": 1,
    "Arena of Glory": 1, "Demolition Field": 1, "Field of Ruin": 2,
    "Plains": 2, "Mountain": 1, "Island": 1,
}

# 24 lands, 2-2-1 shocks: free slot → +1 Snapcaster instead.
HYBRID_24_221_3S = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2,
    "Phlage": 2, "Solitude": 2, "Snapcaster Mage": 3, "Erode": 4,
    "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 2, "Wrath of the Skies": 1,
    "Arid Mesa": 4, "Scalding Tarn": 4,
    "Marsh Flats": 2, "Misty Rainforest": 1,
    "Sacred Foundry": 2, "Hallowed Fountain": 2, "Steam Vents": 1,
    "Arena of Glory": 1, "Demolition Field": 1, "Field of Ruin": 2,
    "Plains": 2, "Mountain": 1, "Island": 1,
}

# 24 lands, 2-1-1 shocks (1 SF, 2 HF, 1 SV) + off-color fetches; +1 Phlage, +1 Wrath
HYBRID_24_211_3P = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2,
    "Phlage": 3, "Solitude": 2, "Snapcaster Mage": 2, "Erode": 4,
    "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 2, "Wrath of the Skies": 2,
    "Arid Mesa": 4, "Scalding Tarn": 4,
    "Marsh Flats": 2, "Misty Rainforest": 1, "Polluted Delta": 1,
    "Sacred Foundry": 1, "Hallowed Fountain": 2, "Steam Vents": 1,
    "Arena of Glory": 1, "Demolition Field": 1, "Field of Ruin": 2,
    "Plains": 1, "Mountain": 1, "Island": 1,
}

# 23 lands, 2-2-1 shocks; free 2 slots → +1 Phlage + 1 Wrath of the Skies
HYBRID_23_221_3P = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2,
    "Phlage": 3, "Solitude": 2, "Snapcaster Mage": 2, "Erode": 4,
    "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 2, "Wrath of the Skies": 2,
    "Arid Mesa": 4, "Scalding Tarn": 4,
    "Marsh Flats": 2, "Misty Rainforest": 1,
    "Sacred Foundry": 2, "Hallowed Fountain": 2, "Steam Vents": 1,
    "Arena of Glory": 1, "Demolition Field": 1, "Field of Ruin": 1,
    "Plains": 2, "Mountain": 1, "Island": 1,
}

VARIANTS = [
    ("HYBRID_25_44 (orig 4-4-1 shocks)", HYBRID_25_44),
    ("HYBRID_25_221 (2-2-1 shocks)", HYBRID_25_221),
    ("HYBRID_24_221_3P (24 lands, 3 Phlage)", HYBRID_24_221_3P),
    ("HYBRID_24_221_3S (24 lands, 3 Snap)", HYBRID_24_221_3S),
    ("HYBRID_24_211_3P (2-1-1 shocks, 3 Phlage)", HYBRID_24_211_3P),
    ("HYBRID_23_221_3P (23 lands, 3 Phl, 2 WoS)", HYBRID_23_221_3P),
]

print(f"{'Variant':<46} {'Tot':>4} {'Lands':>5} {'Score':>7} {'Power':>7} {'Cast':>7} {'Eff':>7} {'Flood':>7}")
print("-" * 100)
for name, d in VARIANTS:
    if deck_total(d) != 60:
        print(f"!! {name} has {deck_total(d)} cards"); continue
    scores, powers, casts, effs, floods = [], [], [], [], []
    for seed in [1, 2, 3, 4, 5]:
        random.seed(seed)
        res = simulate(build_deck(d), trials=4000)
        s, parts = composite_score(d, res)
        scores.append(s); powers.append(parts["power"])
        casts.append(parts["castability"]); effs.append(parts["mana_efficiency"])
        floods.append(parts["stuff_to_do"])
    def avg(xs): return sum(xs)/len(xs)
    print(f"{name:<46} {deck_total(d):>4} {land_total(d):>5} "
          f"{avg(scores):>7.2f} {avg(powers):>7.2f} {avg(casts):>7.2f} {avg(effs):>7.2f} {avg(floods):>7.2f}")

# === Color access on the new manabases ===
print()
print("=== Color access (P(condition met by turn) over 8000 trials) ===")
print(f"{'Variant':<46} {'WUR T3':>7} {'Phl-T3':>7} {'Phl-Esc-T5':>10} {'QR-HC-T5':>9}")
def simulate_mana(deck_def, n=8000, max_turn=6):
    deck_list = build_deck(deck_def)
    p_wur_t3 = 0; p_phlage_t3 = 0; p_phlage_t5 = 0; p_qr_t5 = 0
    n_t3 = n_t5 = 0
    for _ in range(n):
        random.shuffle(deck_list)
        hand = deck_list[:7]
        library = deck_list[7:]
        in_play = []
        for turn in range(1, max_turn+1):
            if turn > 1 and library:
                hand.append(library.pop(0))
            land_in_hand = [c for c in hand if CARDS[c]["land"]]
            if land_in_hand:
                have = set().union(*[land_colors(l) for l in in_play]) if in_play else set()
                land_in_hand.sort(key=lambda l: len(land_colors(l) - have), reverse=True)
                play = land_in_hand[0]
                in_play.append(play); hand.remove(play)
            r_sources = sum(1 for l in in_play if "R" in land_colors(l))
            w_sources = sum(1 for l in in_play if "W" in land_colors(l))
            u_sources = sum(1 for l in in_play if "U" in land_colors(l))
            colors = set().union(*[land_colors(l) for l in in_play]) if in_play else set()
            if turn == 3:
                n_t3 += 1
                if {"W","U","R"}.issubset(colors): p_wur_t3 += 1
                if r_sources >= 1 and w_sources >= 1 and len(in_play) >= 3: p_phlage_t3 += 1
            if turn == 5:
                n_t5 += 1
                if r_sources >= 2 and w_sources >= 2 and len(in_play) >= 4: p_phlage_t5 += 1
                if u_sources >= 2 and len(in_play) >= 5: p_qr_t5 += 1
    return (p_wur_t3/n_t3*100, p_phlage_t3/n_t3*100, p_phlage_t5/n_t5*100, p_qr_t5/n_t5*100)

for name, d in VARIANTS:
    if deck_total(d) != 60: continue
    random.seed(42)
    wur, phl3, phl5, qr5 = simulate_mana(d)
    print(f"{name:<46} {wur:>6.1f}% {phl3:>6.1f}% {phl5:>9.1f}% {qr5:>8.1f}%")
