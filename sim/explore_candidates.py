"""Explore non-obvious card additions to the v19 baseline.
Each test = swap an existing card for a new candidate, score the variant."""
import random
from optimize import evaluate, PHELIA_V19

# Starting from PHELIA_V19, try replacing 1 spell with each candidate
# (only spell-for-spell allowed)
CANDIDATES_TO_TRY = [
    # Format: (card_to_add, card_to_cut, reason)
    ("Ephemerate", "Galvanic Discharge", "combo glue for QR + Phantom + Solitude"),
    ("Ephemerate", "Wrath of the Skies", "combo glue alternative"),
    ("Snapcaster Mage", "Galvanic Discharge", "flashback engine for Wildfire/PoF"),
    ("Snapcaster Mage", "Phelia", "flashback engine — replace Phelia"),
    ("Teferi, Time Raveler", "Galvanic Discharge", "sorcery-speed flash + bounce"),
    ("Teferi, Time Raveler", "Wrath of the Skies", "permanent-bounce + sorcery-flash"),
    ("Solitude", "Galvanic Discharge", "exile-removal vs energy-burn"),
    ("Solitude", "Phlage", "evoke flexibility vs recursive Phlage"),
    ("Solitude", "Wrath of the Skies", "evoke vs sweeper"),
    ("Wrath of God", "Wrath of the Skies", "non-X sweeper"),
    ("Path to Exile", "Galvanic Discharge", "more depletion triggers"),
    ("Cleansing Wildfire", "Galvanic Discharge", "5th Wildfire - illegal but check 4-cap"),
    ("Phelia", "Galvanic Discharge", "extra Phelia copy"),
    ("Phlage", "Galvanic Discharge", "extra Phlage copy"),
]

if __name__ == "__main__":
    random.seed(42)
    base, _, _ = evaluate(PHELIA_V19, n_seeds=2, trials=1000)
    print(f"Baseline (PHELIA_V19): {base:.2f}")
    print()
    print(f"{'Add':<25} {'Cut':<25} {'Score':>7} {'Δ':>7}")
    print("-" * 70)

    results = []
    for add_card, cut_card, reason in CANDIDATES_TO_TRY:
        d = dict(PHELIA_V19)
        if d.get(cut_card, 0) <= 0:
            continue
        d[cut_card] -= 1
        if d[cut_card] == 0:
            del d[cut_card]
        d[add_card] = d.get(add_card, 0) + 1
        # Check 4-of cap
        if d[add_card] > 4 and add_card not in ("Plains", "Mountain", "Island"):
            continue
        try:
            score, _, _ = evaluate(d, n_seeds=2, trials=1000)
            delta = score - base
            results.append((delta, add_card, cut_card, score, reason))
            marker = " ← improvement" if delta > 0.4 else ""
            print(f"{add_card:<25} {cut_card:<25} {score:>7.2f} {delta:>+7.2f}{marker}")
        except Exception as e:
            print(f"{add_card:<25} {cut_card:<25} ERROR: {e}")

    print()
    print("Top 5 candidate additions:")
    results.sort(reverse=True)
    for delta, add, cut, score, reason in results[:5]:
        print(f"  +{delta:>5.2f}  +1 {add:<25}-1 {cut:<25}  ({reason})")
