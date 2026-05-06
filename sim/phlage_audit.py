"""Phlage value audit — tests user's pushback that Phlage is undervalued.

Three lines of inquiry:
1. Is Phlage's DR curve [1.0, 0.5, 0.2, 0.1] too harsh?
   Phlage in HELIX MODE doesn't care about legendary rule — each copy goes
   to yard on cast. Only a Phlage already in play makes the legendary rule
   bite, and even then we can elect to sac the old one.
2. What is the actual T3-Phlage castability across variants?
3. Is there a 22% "dead-card" rate? Where does that number come from?

We run the SAFE (0 Phlage), HYBRID (2 Phlage), and Phlage-heavy variants
and compare the actual sim metrics.
"""
import random
import sys
sys.path.insert(0, "/tmp/mtg-quantum-riddler-explorer/sim")
from simulate import simulate, build_deck
from score import composite_score, effective_power, CARD_POWER

# Locked SAFE recommendation
SAFE = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2,
    "Solitude": 2, "Snapcaster Mage": 3, "Erode": 4, "Path to Exile": 4,
    "Cleansing Wildfire": 4, "Price of Freedom": 4, "Galvanic Discharge": 2,
    "Wrath of the Skies": 2,
    "Arid Mesa": 4, "Scalding Tarn": 4, "Sacred Foundry": 4,
    "Hallowed Fountain": 4, "Steam Vents": 1, "Arena of Glory": 1,
    "Demolition Field": 1, "Field of Ruin": 1, "Misty Rainforest": 1,
    "Plains": 2, "Mountain": 1, "Island": 1,
}

# Hybrid (2 Phlage)
HYBRID = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2,
    "Phlage": 2, "Solitude": 2, "Snapcaster Mage": 2, "Erode": 4,
    "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 2, "Wrath of the Skies": 1,
    "Arid Mesa": 4, "Scalding Tarn": 4, "Sacred Foundry": 4,
    "Hallowed Fountain": 4, "Steam Vents": 1, "Arena of Glory": 1,
    "Demolition Field": 1, "Field of Ruin": 2,
    "Plains": 2, "Mountain": 1, "Island": 1,
}

# 3 Phlage — drop 1 Snap, 1 Phelia, +1 Arena
P3 = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2,
    "Phlage": 3, "Solitude": 2, "Snapcaster Mage": 1, "Erode": 4,
    "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 2, "Wrath of the Skies": 1,
    "Arid Mesa": 4, "Scalding Tarn": 4, "Sacred Foundry": 4,
    "Hallowed Fountain": 4, "Steam Vents": 1, "Arena of Glory": 2,
    "Demolition Field": 1, "Field of Ruin": 1,
    "Plains": 2, "Mountain": 1, "Island": 1,
}

# 4 Phlage — full commit; drop Solitude+Snap+Phelia for engine + Phlage redundancy
# Cuts: 1 Phelia (2->1), 1 Solitude (2->1), 2 Snap (3->1). +4 Phlage. +1 Arena. +1 WoS net.
# Lands: same 25-land base as SAFE but +1 Arena, -1 Misty Rainforest.
P4 = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 1,
    "Phlage": 4, "Solitude": 1, "Snapcaster Mage": 1, "Erode": 4,
    "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 2, "Wrath of the Skies": 2,
    "Arid Mesa": 4, "Scalding Tarn": 4, "Sacred Foundry": 4,
    "Hallowed Fountain": 4, "Steam Vents": 1, "Arena of Glory": 2,
    "Demolition Field": 1, "Field of Ruin": 1,
    "Plains": 2, "Mountain": 1, "Island": 1,
}

# 4 Phlage WITH FoR/DF dropped for blue support — user's exact ask:
# "Maybe we can't realistically cast & flashback Phlage AND blue spells AND keep FoR/DF."
# So this drops FoR + DF entirely; replaces with basic+ shock for color reliability.
P4_NO_LD_LANDS = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2,
    "Phlage": 4, "Solitude": 2, "Snapcaster Mage": 1, "Erode": 4,
    "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 2, "Wrath of the Skies": 1,
    "Arid Mesa": 4, "Scalding Tarn": 4, "Sacred Foundry": 4,
    "Hallowed Fountain": 4, "Steam Vents": 1, "Arena of Glory": 2,
    # NO Demolition Field, NO Field of Ruin
    "Plains": 2, "Mountain": 1, "Island": 2,
}

def total(deck):
    return sum(deck.values())

decks = [
    ("SAFE (0 Phlage, 3 Snap, 1 FoR+DF)", SAFE),
    ("HYBRID (2 Phlage, 2 Snap)", HYBRID),
    ("P3 (3 Phlage, 1 Snap)", P3),
    ("P4 (4 Phlage, 1 Solitude)", P4),
    ("P4_NO_LD (4 Phlage, NO FoR/DF)", P4_NO_LD_LANDS),
]
for name, d in decks:
    if total(d) != 60:
        print(f"!! {name} has {total(d)} cards")
        continue

# Multi-seed averages
print(f"{'Variant':<40} {'Score':>7} {'Power':>7} {'Cast':>7} {'Eff':>7} {'Flood':>7} {'PhlageT3':>10} {'PhlageEsc':>10}")
print("-" * 110)
for name, d in decks:
    if total(d) != 60:
        continue
    scores = []
    powers = []
    casts = []
    effs = []
    floods = []
    phlage_t3s = []
    phlage_escs = []
    for seed in [1, 2, 3, 4, 5]:
        random.seed(seed)
        res = simulate(build_deck(d), trials=4000)
        s, parts = composite_score(d, res)
        scores.append(s)
        powers.append(parts["power"])
        casts.append(parts["castability"])
        effs.append(parts["mana_efficiency"])
        floods.append(parts["stuff_to_do"])
        pe = res.get("phlage_T3_removal", {})
        cast_pct = pe.get("castable_given_in_hand_pct")
        in_hand_pct = pe.get("had_in_hand_pct")
        phlage_t3s.append(cast_pct if cast_pct is not None else 0)
        pesc = res.get("phlage_escape_T7", {})
        phlage_escs.append(pesc.get("castable_given_in_hand_pct") or 0)
    def avg(xs): return sum(xs)/len(xs)
    print(f"{name:<40} {avg(scores):>7.2f} {avg(powers):>7.2f} {avg(casts):>7.2f} {avg(effs):>7.2f} {avg(floods):>7.2f} {avg(phlage_t3s):>9.1f}% {avg(phlage_escs):>9.1f}%")

# ---------------------------------------------------------------
# Now: re-score with a softened Phlage DR curve representing the
# Helix-mode redundancy argument (each extra in hand = another Helix
# you can cast → goes to yard immediately, fueling escape).
# Old curve: [1.0, 0.5, 0.2, 0.1] — assumes legendary DR
# New curve: [1.0, 0.85, 0.55, 0.30] — moderate Helix-redundancy
# ---------------------------------------------------------------
print()
print("=== With softened Phlage DR curve [1.0, 0.85, 0.55, 0.30] ===")
print(f"{'Variant':<40} {'Score':>7} {'Power':>7} {'dPower':>7}")
print("-" * 70)
import score as score_mod
score_mod.CARD_POWER["Phlage"]["dr"] = [1.0, 0.85, 0.55, 0.30]
for name, d in decks:
    if total(d) != 60:
        continue
    scores = []
    powers = []
    for seed in [1, 2, 3, 4, 5]:
        random.seed(seed)
        res = simulate(build_deck(d), trials=4000)
        s, parts = score_mod.composite_score(d, res)
        scores.append(s)
        powers.append(parts["power"])
    def avg(xs): return sum(xs)/len(xs)
    print(f"{name:<40} {avg(scores):>7.2f} {avg(powers):>7.2f}")

# Restore
score_mod.CARD_POWER["Phlage"]["dr"] = [1.0, 0.5, 0.2, 0.1]

print()
print("=== Phlage component breakdown (per copy effective power, max conditions) ===")
print(f"{'#':<4} {'Base':>7} {'DR':>6} {'+Arena':>7} {'+Late':>7} {'PerCopy':>8} {'Cumul':>8}")
cfg = CARD_POWER["Phlage"]
cum = 0
for n in range(1, 5):
    dr = cfg["dr"][n-1]
    base = cfg["base"]
    full = (base + 1.5 + 1.0) * dr
    cum += full
    print(f"{n:<4} {base:>7.1f} {dr:>6.2f} {1.5*dr:>7.2f} {1.0*dr:>7.2f} {full:>8.2f} {cum:>8.2f}")
print()
print("=== If DR softened to [1.0, 0.85, 0.6, 0.35] (Helix-mode redundancy) ===")
soft = [1.0, 0.85, 0.6, 0.35]
cum = 0
for n in range(1, 5):
    full = (9 + 1.5 + 1.0) * soft[n-1]
    cum += full
    print(f"{n}: per_copy={full:.2f}  cumul={cum:.2f}")
