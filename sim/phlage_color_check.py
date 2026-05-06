"""Color-access by turn: SAFE vs HYBRID vs P3 vs P4 vs P4_NO_LD.

Specifically: P(W+U+R by turn N), P(R+W by turn 3 for Phlage hardcast),
P(R+R+W+W by turn 5 for Phlage escape).
"""
import random
import sys
sys.path.insert(0, "/tmp/mtg-quantum-riddler-explorer/sim")
from simulate import build_deck, CARDS
from color_access import land_colors

from phlage_audit import SAFE, HYBRID, P3, P4, P4_NO_LD_LANDS

def simulate_mana(deck_def, n=8000, max_turn=8):
    deck_list = build_deck(deck_def)
    p_wur = {t: 0 for t in range(1, max_turn+1)}
    p_phlage_t3 = 0  # need RW + 1 generic = 3 lands with R, W
    p_phlage_t5 = 0  # need RRWW = 4 lands enabling 2R + 2W
    p_qr_t5 = 0      # need UU + 3 generic = 5 lands with 2 U sources
    n_t3 = 0
    n_t5 = 0
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
                in_play.append(play)
                hand.remove(play)
            # Compute color counts
            r_sources = sum(1 for l in in_play if "R" in land_colors(l))
            w_sources = sum(1 for l in in_play if "W" in land_colors(l))
            u_sources = sum(1 for l in in_play if "U" in land_colors(l))
            colors = set().union(*[land_colors(l) for l in in_play]) if in_play else set()
            if {"W","U","R"}.issubset(colors):
                p_wur[turn] += 1
            if turn == 3:
                n_t3 += 1
                if r_sources >= 1 and w_sources >= 1 and len(in_play) >= 3:
                    p_phlage_t3 += 1
            if turn == 5:
                n_t5 += 1
                if r_sources >= 2 and w_sources >= 2 and len(in_play) >= 4:
                    p_phlage_t5 += 1
                if u_sources >= 2 and len(in_play) >= 5:
                    p_qr_t5 += 1
    return {
        "wur_by_turn": {t: p_wur[t]/n*100 for t in range(1, max_turn+1)},
        "p_phlage_t3_pct": p_phlage_t3/n_t3*100,
        "p_phlage_escape_t5_pct": p_phlage_t5/n_t5*100,
        "p_qr_hardcast_t5_pct": p_qr_t5/n_t5*100,
    }

decks = [
    ("SAFE", SAFE),
    ("HYBRID", HYBRID),
    ("P3", P3),
    ("P4", P4),
    ("P4_NO_LD", P4_NO_LD_LANDS),
]
print(f"{'Variant':<10} {'T2':>5} {'T3':>5} {'T4':>5} {'T5':>5} {'T6':>5}  {'Phl-T3':>7} {'Phl-Esc-T5':>11} {'QR-HC-T5':>9}")
for name, d in decks:
    if sum(d.values()) != 60:
        print(f"!! {name} {sum(d.values())} cards"); continue
    random.seed(42)
    r = simulate_mana(d)
    wur = r["wur_by_turn"]
    print(f"{name:<10} {wur[2]:>4.1f}% {wur[3]:>4.1f}% {wur[4]:>4.1f}% {wur[5]:>4.1f}% {wur[6]:>4.1f}%  "
          f"{r['p_phlage_t3_pct']:>6.1f}% {r['p_phlage_escape_t5_pct']:>10.1f}% {r['p_qr_hardcast_t5_pct']:>8.1f}%")
