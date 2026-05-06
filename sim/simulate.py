"""Monte Carlo simulator v3 — turn-by-turn play with land activations,
graveyard tracking, and proper Phlage handling.

Per-turn the bot:
  1. Draws (skipping T1 on the play)
  2. Plays a land. Picks the land that gives the most-needed color, prefers
     untapped, deprioritizes colorless if other colored options exist.
     Sunken Citadel chooses color based on whether we need to power a
     Field-of-Ruin / Demolition Field activation soon.
  3. Activates land abilities opportunistically:
     - Field of Ruin: pay 1 + tap + sacrifice for opp non-basic + both basics.
       Triggered when we have spare 1 generic AND opp is presumed to have a
       non-basic (constant 70% probability used here).
     - Sunken Citadel adds 2 of chosen color toward Field of Ruin / Demolition
       Field activations.
  4. Casts a self-Cleansing Wildfire if it would unstick a color need.
  5. Tracks events:
     - Erode/Path castable on T1 (precondition: in hand + W).
     - Phantom castable on T2-T3 (precondition: in hand + WW).
     - Phelia, Wildfire, PoF castable on T2-T3.
     - Phlage T3 as REMOVAL: 3-damage trigger + self-sac, Phlage to yard.
       (Treated as a positive event — it's a Lightning Helix that puts
       Phlage in your yard for future escape.)
     - Phlage escape T5/T6/T7: precondition is Phlage in yard +
       ≥5 OTHER yard cards + RRWW available + Phlage in yard.
     - Warp QR T2/T3.
     - Hardcast QR T5/T6.

Pretty different model. Conservative-ish: opp non-basic for FoR-sac is
modeled as a 70% probability per turn (most Modern decks have one).
"""
import random
from collections import defaultdict, Counter

LAND = "L"

def L(produces, tapped=False, basic=False):
    return {"land": True, "produces": frozenset(produces), "tapped": tapped, "basic": basic}
def S(cmc, colors, creature=False):
    return {"land": False, "cmc": cmc, "colors": Counter(colors), "creature": creature}

CARDS = {
    "Quantum Riddler":      S(5, {"U":2}, creature=True),
    "Phlage":               S(3, {"R":1, "W":1}, creature=True),
    "White Orchid Phantom": S(2, {"W":2}, creature=True),
    "Phelia":               S(2, {"W":1}, creature=True),
    "Solitude":             S(5, {"W":1}, creature=True),
    "Erode":                S(1, {"W":1}),
    "Path to Exile":        S(1, {"W":1}),
    "Galvanic Discharge":   S(1, {"R":1}),
    "Cleansing Wildfire":   S(2, {"R":1}),
    "Price of Freedom":     S(2, {"R":1}),
    "Wrath of the Skies":   S(2, {"W":2}),
    "Wrath of God":         S(4, {"W":2}),
    "Ephemerate":           S(1, {"W":1}),
    "The Legend of Roku":   S(4, {"R":2}),
    "Teferi, Time Raveler": S(3, {"W":1, "U":1}),
    "Plains":              L({"W"}, basic=True),
    "Mountain":            L({"R"}, basic=True),
    "Island":              L({"U"}, basic=True),
    "Sacred Foundry":      L({"R","W"}),
    "Hallowed Fountain":   L({"W","U"}),
    "Steam Vents":         L({"U","R"}),
    "Scalding Tarn":       L({"U","R"}),
    "Arid Mesa":           L({"R","W"}),
    "Flooded Strand":      L({"W","U"}),
    # Off-color fetches: still find Sacred Foundry / Hallowed Fountain / Steam Vents
    # (shocks have multiple subtypes); only find 1/3 WUR basics each.
    # Modeled as fetching the best WUR shock, same as the in-color fetches.
    "Misty Rainforest":    L({"U","R"}),  # G/U; reaches HF, SV
    "Polluted Delta":      L({"U","R"}),  # U/B; reaches HF, SV
    "Marsh Flats":         L({"W","R"}),  # W/B; reaches SF, HF
    "Wooded Foothills":    L({"R","W"}),  # R/G; reaches SF, SV
    "Bloodstained Mire":   L({"R","U"}),  # B/R; reaches SF, SV
    "Windswept Heath":     L({"W","R"}),  # W/G; reaches SF, HF
    "Demolition Field":    L({"C"}),
    "Field of Ruin":       L({"C"}),
    "Sunken Citadel":      L({"C"}, tapped=True),
    "Cori Mountain Monastery": L({"R"}),
    "Arena of Glory":      L({"R"}),
    "Otawara, Soaring City": L({"U"}),
    "Eiganjo, Seat of the Empire": L({"W"}),
    "Sokenzan, Crucible of Defiance": L({"R"}),
    "Flashback":           S(1, {"R":1}),
    "Snapcaster Mage":     S(2, {"U":1}, creature=True),
    "Counterspell":        S(2, {"U":2}),
    "Mystical Dispute":    S(2, {"U":1}),
    "Teferi, Time Raveler": S(3, {"W":1, "U":1}, creature=True),
}

def build_deck(quantities):
    deck = []
    for name, qty in quantities.items():
        if name not in CARDS:
            raise KeyError(name)
        deck.extend([name] * qty)
    if len(deck) != 60:
        raise ValueError(f"deck has {len(deck)} cards, expected 60")
    return deck

def can_pay_cost(land_colors, cost):
    pool = [set(s) for s in land_colors]
    req = dict(cost)
    generic = req.pop("G", 0)
    for color in ["W", "U", "R", "B", "C"]:
        n = req.get(color, 0)
        if n == 0:
            continue
        cands = [(len(pool[i]), i) for i in range(len(pool)) if color in pool[i]]
        cands.sort()
        if len(cands) < n:
            return False
        for _, idx in cands[:n]:
            pool[idx] = set()
    remaining = sum(1 for s in pool if s)
    return remaining >= generic

def color_count(land_colors, color):
    return sum(1 for s in land_colors if color in s)

def pick_land(hand, battlefield, turn):
    """Heuristic land choice: prioritize colors we lack."""
    lands = [c for c in hand if CARDS[c]["land"]]
    if not lands:
        return None
    have = set().union(*[CARDS[l]["produces"] for l in battlefield]) if battlefield else set()
    # We want W, U, R coverage. C-only lands are last resort.
    def score(l):
        produces = CARDS[l]["produces"]
        new_colors = produces - have
        is_C_only = produces == frozenset({"C"})
        is_basic = CARDS[l]["basic"]
        is_tapped = CARDS[l]["tapped"]
        # Lower score = better
        return (
            -len(new_colors),     # prefer new-color lands
            is_C_only,            # avoid colorless if possible
            is_tapped,            # prefer untapped
            not is_basic,         # prefer basics over duals (bait less)
        )
    lands.sort(key=score)
    return lands[0]

def simulate(deck, trials=15000, on_play=True, max_turn=12):
    cond = defaultdict(lambda: [0, 0])  # key -> [had_precondition, could_cast]
    misc = defaultdict(int)

    for _ in range(trials):
        dk = list(deck)
        random.shuffle(dk)
        hand = dk[:7]
        library = dk[7:]
        battlefield = []
        graveyard = []  # cards we've sent to our yard
        casts = []      # spells cast this game
        max_qrs_in_hand = 0

        # Track Field of Ruin / Sunken Citadel state for activations
        used_for = 0  # number of FoR sacrificed
        used_df = 0   # demolition field sacrificed
        # Track if we cast self-Wildfire
        self_wildfires = 0
        # Cumulative basic-tutors forced on opponent
        basics_tutored = 0
        # Cumulative energy banked from Galvanic casts (this trial)
        energy_banked = 0

        # Mulligan-keepable
        land_count_open = sum(1 for c in hand if CARDS[c]["land"])
        if 2 <= land_count_open <= 4:
            misc["keep_open"] += 1

        for turn in range(1, max_turn + 1):
            # 1. Draw
            if not (on_play and turn == 1) and library:
                hand.append(library.pop(0))

            # 2. Land drop
            land = pick_land(hand, battlefield, turn)
            if land:
                hand.remove(land)
                # Fetchlands: crack immediately. Fetch goes to yard, replaced by best dual.
                FETCH_TARGETS = {
                    "Scalding Tarn":      ["Steam Vents", "Hallowed Fountain", "Sacred Foundry", "Island", "Mountain"],
                    "Arid Mesa":          ["Sacred Foundry", "Hallowed Fountain", "Steam Vents", "Mountain", "Plains"],
                    "Flooded Strand":     ["Hallowed Fountain", "Sacred Foundry", "Steam Vents", "Plains", "Island"],
                    # Off-color fetches: list ONLY shocks they can actually find via subtypes,
                    # then the 1 basic they reach. Lose flexibility vs in-color fetches.
                    "Misty Rainforest":   ["Hallowed Fountain", "Steam Vents", "Island"],     # G/U fetch
                    "Polluted Delta":     ["Hallowed Fountain", "Steam Vents", "Island"],     # U/B fetch
                    "Marsh Flats":        ["Sacred Foundry", "Hallowed Fountain", "Plains"],   # W/B fetch
                    "Wooded Foothills":   ["Sacred Foundry", "Steam Vents", "Mountain"],      # R/G fetch
                    "Bloodstained Mire":  ["Sacred Foundry", "Steam Vents", "Mountain"],      # B/R fetch
                    "Windswept Heath":    ["Sacred Foundry", "Hallowed Fountain", "Plains"],   # W/G fetch
                }
                if land in FETCH_TARGETS:
                    graveyard.append(land)  # fetchland goes to yard
                    # Pick the best target — must actually exist in library!
                    have = set().union(*[CARDS[l]["produces"] for l in battlefield]) if battlefield else set()
                    best = None
                    # First pass: find a shock in library that adds a new color
                    for cand in FETCH_TARGETS[land]:
                        if cand not in library:
                            continue
                        produces = CARDS[cand]["produces"]
                        new = produces - have
                        if new:
                            best = cand
                            break
                    # Second pass: find any valid land in library (any new color or not)
                    if best is None:
                        for cand in FETCH_TARGETS[land]:
                            if cand in library:
                                best = cand
                                break
                    if best is not None:
                        library.remove(best)  # actually remove from library — fetches THIN the deck
                        battlefield.append(best)
                    # else: no valid target in library — fetch fizzles, fetch goes to yard for nothing
                else:
                    battlefield.append(land)

            # 3. Compute available mana (untapped lands)
            avail = []
            for i, l in enumerate(battlefield):
                # Skip the just-played tapped land for this turn
                produces = CARDS[l]["produces"]
                # Sunken Citadel ETBT — skip if just played
                if CARDS[l]["tapped"] and i == len(battlefield) - 1:
                    continue
                avail.append(produces)

            # 4. Bonus from Sunken Citadel: only spendable on land abilities,
            # so we use it specifically to power Field of Ruin / Demolition activations
            citadel_in_play = any(
                l == "Sunken Citadel" for i, l in enumerate(battlefield)
                if not (CARDS[l]["tapped"] and i == len(battlefield) - 1)
            )
            for_in_play = sum(1 for l in battlefield if l == "Field of Ruin")
            df_in_play = sum(1 for l in battlefield if l == "Demolition Field")

            # Field of Ruin self-sac (with citadel powering it)
            # Sac FoR to get a basic (and break opp non-basic). Conservative: at most 1 sac per game in this sim.
            opp_has_nonbasic_p = 0.7  # most Modern decks have at least one; assume 70%
            if (turn >= 2 and for_in_play > 0 and used_for < 1
                and (citadel_in_play or len(avail) >= 2)
                and random.random() < opp_has_nonbasic_p):
                short_colors = [c for c in ["W", "U", "R"] if color_count(avail, c) < 2]
                if short_colors:
                    chosen = short_colors[0]
                    # Replace FoR with basic, FoR itself goes to OUR yard
                    for i, l in enumerate(battlefield):
                        if l == "Field of Ruin":
                            battlefield[i] = {"W": "Plains", "U": "Island", "R": "Mountain"}[chosen]
                            graveyard.append("Field of Ruin")  # FoR sacrificed → our yard
                            break
                    used_for += 1
                    basics_tutored += 1  # opp's non-basic destroyed → opp searches basic
                    avail = [CARDS[l]["produces"] for i, l in enumerate(battlefield)
                             if not (CARDS[l]["tapped"] and i == len(battlefield) - 1)]

            # Demolition Field self-sac: trades 2 mana for breaking opp same-name non-basic.
            # Doesn't fix our mana but DF goes to our yard. Useful for Phlage escape fuel.
            if (turn >= 3 and df_in_play > 0 and used_df < 1
                and len(avail) >= 3  # need 2 generic for activation + 1 for spell cast
                and random.random() < opp_has_nonbasic_p):  # treat DF same as FoR
                for i, l in enumerate(battlefield):
                    if l == "Demolition Field":
                        battlefield.pop(i)
                        graveyard.append("Demolition Field")
                        break
                used_df += 1
                basics_tutored += 1  # treat DF same as FoR (you said so)
                avail = [CARDS[l]["produces"] for i, l in enumerate(battlefield)
                         if not (CARDS[l]["tapped"] and i == len(battlefield) - 1)]

            # Self-Cleansing Wildfire: if we're hurting for a color and have Wildfire + spare R + 1 generic.
            # Target a non-basic of ours we don't need.
            if ("Cleansing Wildfire" in hand
                and self_wildfires < 1
                and turn >= 2
                and can_pay_cost(avail, {"R": 1, "G": 1})):
                # Find a non-basic to wildfire that won't hurt our color base
                target_idx = None
                for i, l in enumerate(battlefield):
                    if not CARDS[l]["basic"] and l != "Field of Ruin" and l != "Demolition Field" and l != "Sunken Citadel":
                        # Don't wildfire shocks unprovoked; only do it if we need a specific color
                        if l in ("Sacred Foundry", "Hallowed Fountain", "Steam Vents", "Scalding Tarn", "Arid Mesa", "Flooded Strand"):
                            # Only consider if we'd benefit from a basic of a color we lack
                            # Skip — these are good lands
                            continue
                        # Citadel/Cori/Arena are good wildfire targets
                        if l in ("Cori Mountain Monastery", "Arena of Glory"):
                            target_idx = i
                            break
                if target_idx is not None:
                    short_colors = [c for c in ["W", "U", "R"] if color_count(avail, c) < 2]
                    if short_colors:
                        chosen = short_colors[0]
                        # The destroyed land also goes to OUR yard
                        destroyed_land = battlefield[target_idx]
                        graveyard.append(destroyed_land)
                        battlefield[target_idx] = {"W": "Plains", "U": "Island", "R": "Mountain"}[chosen]
                        hand.remove("Cleansing Wildfire")
                        graveyard.append("Cleansing Wildfire")
                        casts.append("Cleansing Wildfire")
                        self_wildfires += 1
                        # NOTE: this is self-Wildfire, NOT a basic-tutor on opp. Doesn't count.
                        # Recompute avail
                        avail = [CARDS[l]["produces"] for i, l in enumerate(battlefield)
                                 if not (CARDS[l]["tapped"] and i == len(battlefield) - 1)]

            # Track QR flooding
            qrs = sum(1 for c in hand if c == "Quantum Riddler")
            max_qrs_in_hand = max(max_qrs_in_hand, qrs)

            # === CONDITIONAL EVENTS ===
            def track(key, precondition, castable):
                if precondition:
                    cond[key][0] += 1
                    if castable:
                        cond[key][1] += 1

            # T1
            if turn == 1:
                track("erode_T1", "Erode" in hand, can_pay_cost(avail, {"W": 1}))
                track("path_T1", "Path to Exile" in hand, can_pay_cost(avail, {"W": 1}))
                track("galvanic_T1", "Galvanic Discharge" in hand, can_pay_cost(avail, {"R": 1}))

            # T2
            if turn == 2:
                track("phantom_T2", "White Orchid Phantom" in hand, can_pay_cost(avail, {"W": 2}))
                track("phelia_T2", "Phelia" in hand, can_pay_cost(avail, {"W": 1, "G": 1}))
                track("wildfire_T2", "Cleansing Wildfire" in hand, can_pay_cost(avail, {"R": 1, "G": 1}))
                track("pof_T2", "Price of Freedom" in hand, can_pay_cost(avail, {"R": 1, "G": 1}))
                track("warp_qr_T2", "Quantum Riddler" in hand, can_pay_cost(avail, {"U": 1, "G": 1}))

            # T3
            if turn == 3:
                track("phantom_T3", "White Orchid Phantom" in hand, can_pay_cost(avail, {"W": 2}))
                track("phelia_T3", "Phelia" in hand, can_pay_cost(avail, {"W": 1, "G": 1}))
                track("warp_qr_T3", "Quantum Riddler" in hand, can_pay_cost(avail, {"U": 1, "G": 1}))
                # Phlage T3 as REMOVAL spell (Lightning Helix-equivalent + Phlage to yard)
                track("phlage_T3_removal", "Phlage" in hand, can_pay_cost(avail, {"R": 1, "W": 1, "G": 1}))

            # T4
            if turn == 4:
                track("wos_T4", "Wrath of the Skies" in hand, can_pay_cost(avail, {"W": 2, "G": 2}))
                track("roku_T4", "The Legend of Roku" in hand, can_pay_cost(avail, {"R": 2, "G": 2}))

            # T5
            if turn == 5:
                track("hardcast_qr_T5", "Quantum Riddler" in hand, can_pay_cost(avail, {"U": 2, "G": 3}))
                # Phlage escape: Phlage in yard + 5 other yard cards + RRWW
                phlage_in_yard = "Phlage" in graveyard
                yard_other = len(graveyard) - (1 if phlage_in_yard else 0)
                escape_mana_ok = can_pay_cost(avail, {"R": 2, "W": 2})
                track("phlage_escape_T5", phlage_in_yard and yard_other >= 5, escape_mana_ok)
                # Looser: just track mana
                misc["mana_for_phlage_escape_T5"] += 1 if escape_mana_ok else 0
                misc["t5_total"] += 1

            # T6
            if turn == 6:
                track("hardcast_qr_T6", "Quantum Riddler" in hand, can_pay_cost(avail, {"U": 2, "G": 3}))
                phlage_in_yard = "Phlage" in graveyard
                yard_other = len(graveyard) - (1 if phlage_in_yard else 0)
                escape_mana_ok = can_pay_cost(avail, {"R": 2, "W": 2})
                track("phlage_escape_T6", phlage_in_yard and yard_other >= 5, escape_mana_ok)
                misc["mana_for_phlage_escape_T6"] += 1 if escape_mana_ok else 0
                misc["t6_total"] += 1

            # T7 — looser timing for escape
            if turn == 7:
                phlage_in_yard = "Phlage" in graveyard
                yard_other = len(graveyard) - (1 if phlage_in_yard else 0)
                escape_mana_ok = can_pay_cost(avail, {"R": 2, "W": 2})
                track("phlage_escape_T7", phlage_in_yard and yard_other >= 5, escape_mana_ok)

            # Track cumulative basic-tutors at each turn for the optimizer
            misc[f"basics_tutored_at_T{turn}"] += basics_tutored
            misc[f"energy_banked_at_T{turn}"] += energy_banked
            # "Stuff to do" flood metric: count non-land cards in hand.
            non_land_in_hand = sum(1 for c in hand if not CARDS[c]["land"])
            misc[f"non_land_in_hand_T{turn}"] += non_land_in_hand
            misc[f"non_land_zero_T{turn}"] += 1 if non_land_in_hand == 0 else 0

            # === ACT: cast a spell to fill yard ===
            # Heuristic: cast best castable spell each turn (grows yard, simulates real game)
            # Priority: removal at T1, engine at T2, phlage at T3, etc.
            cast_priorities = []
            if turn == 1:
                cast_priorities = ["Erode", "Path to Exile", "Galvanic Discharge"]
            elif turn == 2:
                cast_priorities = ["Cleansing Wildfire", "Price of Freedom", "Phelia", "Erode", "Path to Exile", "Galvanic Discharge"]
            elif turn == 3:
                cast_priorities = ["Phlage", "Cleansing Wildfire", "Price of Freedom", "White Orchid Phantom", "Phelia"]
            elif turn == 4:
                cast_priorities = ["Wrath of the Skies", "Wrath of God", "The Legend of Roku", "Cleansing Wildfire", "Price of Freedom", "Phantom"]
            elif turn == 5:
                cast_priorities = ["Quantum Riddler", "Solitude", "Cleansing Wildfire", "Price of Freedom", "Phlage", "Erode"]
            elif 6 <= turn <= 8:
                cast_priorities = ["Quantum Riddler", "Phlage", "Solitude", "White Orchid Phantom", "Cleansing Wildfire", "Price of Freedom", "Erode", "Path to Exile", "Phelia"]
            else:  # turns 9-12: anything castable
                cast_priorities = ["Phlage", "Quantum Riddler", "Solitude", "Cleansing Wildfire", "Price of Freedom", "Erode", "Path to Exile", "Phelia", "White Orchid Phantom", "Galvanic Discharge", "Wrath of the Skies"]

            for spell in cast_priorities:
                if spell not in hand:
                    continue
                cost_map = {
                    "Erode": {"W": 1}, "Path to Exile": {"W": 1}, "Galvanic Discharge": {"R": 1},
                    "Cleansing Wildfire": {"R": 1, "G": 1}, "Price of Freedom": {"R": 1, "G": 1},
                    "Phelia": {"W": 1, "G": 1}, "White Orchid Phantom": {"W": 2},
                    "Phlage": {"R": 1, "W": 1, "G": 1},
                    "Wrath of the Skies": {"W": 2, "G": 2}, "Wrath of God": {"W": 2, "G": 2},
                    "The Legend of Roku": {"R": 2, "G": 2},
                    "Quantum Riddler": {"U": 2, "G": 3},  # hardcast
                    "Solitude": {"W": 1, "G": 4},
                }
                if spell not in cost_map:
                    continue
                if can_pay_cost(avail, cost_map[spell]):
                    hand.remove(spell)
                    graveyard.append(spell)  # spell goes to yard
                    casts.append(spell)
                    # Engine cards force opp to search a basic when cast on opp board/lands
                    if spell in ("Erode", "Path to Exile", "Cleansing Wildfire", "Price of Freedom"):
                        basics_tutored += 1
                    if spell == "White Orchid Phantom":
                        basics_tutored += 1
                    # Track energy banked from Galvanic for Wrath synergy (per-trial cumulative)
                    if spell == "Galvanic Discharge":
                        energy_banked += 2  # bank 2/3 (1 used as removal)
                    break  # one spell per turn

        if max_qrs_in_hand >= 2:
            misc["qr_flood_2plus"] += 1

    # Compose results
    result = {}
    for k, (had, cast) in cond.items():
        result[k] = {
            "had_in_hand_pct": had / trials * 100,
            "castable_given_in_hand_pct": (cast / had * 100) if had else None,
            "miss_rate_pct": ((had - cast) / had * 100) if had else None,
            "n_trials_with_card": had,
        }
    result["misc"] = {
        "keep_open_2to4_lands_pct": misc["keep_open"] / trials * 100,
        "qr_flood_2plus_pct": misc["qr_flood_2plus"] / trials * 100,
        "mana_for_phlage_escape_T5_pct": misc["mana_for_phlage_escape_T5"] / max(misc["t5_total"], 1) * 100,
        "mana_for_phlage_escape_T6_pct": misc["mana_for_phlage_escape_T6"] / max(misc["t6_total"], 1) * 100,
        # Average cumulative basic-tutors forced at each turn
        "avg_basics_tutored_T3": misc.get("basics_tutored_at_T3", 0) / trials,
        "avg_basics_tutored_T4": misc.get("basics_tutored_at_T4", 0) / trials,
        "avg_basics_tutored_T5": misc.get("basics_tutored_at_T5", 0) / trials,
        "avg_basics_tutored_T6": misc.get("basics_tutored_at_T6", 0) / trials,
        "avg_basics_tutored_T7": misc.get("basics_tutored_at_T7", 0) / trials,
        "avg_basics_tutored_T8": misc.get("basics_tutored_at_T8", 0) / trials,
        # Avg cumulative Galvanic-banked energy at each turn (for Wrath synergy)
        "avg_energy_banked_T3": misc.get("energy_banked_at_T3", 0) / trials,
        "avg_energy_banked_T4": misc.get("energy_banked_at_T4", 0) / trials,
        "avg_energy_banked_T5": misc.get("energy_banked_at_T5", 0) / trials,
        "avg_energy_banked_T6": misc.get("energy_banked_at_T6", 0) / trials,
        # Flood/stuff-to-do metrics: avg non-land cards in hand by turn N
        "avg_non_land_in_hand_T7": misc.get("non_land_in_hand_T7", 0) / trials,
        "avg_non_land_in_hand_T8": misc.get("non_land_in_hand_T8", 0) / trials,
        "avg_non_land_in_hand_T10": misc.get("non_land_in_hand_T10", 0) / trials,
        "avg_non_land_in_hand_T12": misc.get("non_land_in_hand_T12", 0) / trials,
        "pct_non_land_zero_T7": misc.get("non_land_zero_T7", 0) / trials * 100,
        "pct_non_land_zero_T8": misc.get("non_land_zero_T8", 0) / trials * 100,
        "pct_non_land_zero_T10": misc.get("non_land_zero_T10", 0) / trials * 100,
        "pct_non_land_zero_T12": misc.get("non_land_zero_T12", 0) / trials * 100,
    }
    return result

def _just_played_turn(bf, hand, turn):
    return turn

# --- Decks ---
PHELIA = {
    "White Orchid Phantom": 4, "Phelia": 3, "Phlage": 3, "Quantum Riddler": 4,
    "Erode": 4, "Path to Exile": 2, "Galvanic Discharge": 4, "Cleansing Wildfire": 4,
    "Price of Freedom": 4, "Wrath of the Skies": 2,
    "Scalding Tarn": 4, "Arid Mesa": 4, "Sacred Foundry": 2, "Hallowed Fountain": 2,
    "Steam Vents": 1, "Arena of Glory": 3, "Demolition Field": 4, "Field of Ruin": 3,
    "Plains": 1, "Mountain": 1, "Island": 1,
}
PURE_ENGINE = {
    "White Orchid Phantom": 4, "Phlage": 4, "Quantum Riddler": 4,
    "Erode": 4, "Path to Exile": 3, "Galvanic Discharge": 4,
    "Cleansing Wildfire": 4, "Price of Freedom": 4, "Wrath of the Skies": 3,
    "The Legend of Roku": 1,
    "Sacred Foundry": 4, "Hallowed Fountain": 2, "Demolition Field": 3,
    "Field of Ruin": 3, "Sunken Citadel": 2, "Arena of Glory": 3,
    "Plains": 3, "Mountain": 1, "Island": 2, "Eiganjo, Seat of the Empire": 1, "Otawara, Soaring City": 1,
}
ROKU = {
    "White Orchid Phantom": 4, "Phlage": 3, "Phelia": 2, "Quantum Riddler": 4,
    "Erode": 4, "Path to Exile": 4, "Galvanic Discharge": 3, "Cleansing Wildfire": 4,
    "Price of Freedom": 4, "Wrath of the Skies": 1, "The Legend of Roku": 1,
    "Sacred Foundry": 4, "Hallowed Fountain": 2, "Demolition Field": 4,
    "Field of Ruin": 4, "Sunken Citadel": 2, "Arena of Glory": 3,
    "Plains": 3, "Mountain": 1, "Island": 2, "Eiganjo, Seat of the Empire": 1,
}
SOURCE_CORKYBOYY = {
    "White Orchid Phantom": 4, "Phlage": 2, "Solitude": 3,
    "Erode": 4, "Flashback": 1, "Galvanic Discharge": 4, "Path to Exile": 4,
    "Cleansing Wildfire": 4, "Price of Freedom": 4, "Wrath of the Skies": 4,
    "Wrath of God": 1, "The Legend of Roku": 1,
    "Cori Mountain Monastery": 3, "Demolition Field": 4, "Field of Ruin": 4,
    "Mountain": 1, "Plains": 5, "Sacred Foundry": 4, "Sunken Citadel": 3,
}

def report(name, deck_def):
    deck = build_deck(deck_def)
    res = simulate(deck, trials=15000)
    print(f"\n=== {name} ===")
    print(f"  keep={res['misc']['keep_open_2to4_lands_pct']:.1f}%  flood={res['misc']['qr_flood_2plus_pct']:.1f}%  "
          f"phlage_mana_T5={res['misc']['mana_for_phlage_escape_T5_pct']:.1f}%  "
          f"T6={res['misc']['mana_for_phlage_escape_T6_pct']:.1f}%")
    print(f"  {'Conditional metric':<25} {'In hand':>9} {'Cast OK':>8} {'Miss':>6}")
    for key in [
        "erode_T1", "path_T1", "galvanic_T1",
        "phantom_T2", "phantom_T3", "phelia_T2", "phelia_T3",
        "wildfire_T2", "pof_T2", "phlage_T3_removal",
        "warp_qr_T2", "warp_qr_T3", "hardcast_qr_T5", "hardcast_qr_T6",
        "wos_T4", "roku_T4",
        "phlage_escape_T5", "phlage_escape_T6", "phlage_escape_T7",
    ]:
        if key not in res:
            continue
        e = res[key]
        had = e["had_in_hand_pct"]
        cast = e["castable_given_in_hand_pct"]
        cast_str = f"{cast:.1f}%" if cast is not None else "n/a"
        print(f"  {key:<25} {had:>8.1f}% {cast_str:>8}")
    return res

if __name__ == "__main__":
    random.seed(42)
    src = report("Source: Corkyboyy", SOURCE_CORKYBOYY)
    a = report("Phelia Riddler v8", PHELIA)
    b = report("Pure Engine v8", PURE_ENGINE)
    c = report("Roku Hardcast v8", ROKU)
    import json
    out = {"source": src, "phelia": a, "pure": b, "roku": c}
    with open("/tmp/mtg-deck-explorer/js/stats.js", "w") as f:
        f.write("const STATS = " + json.dumps(out, indent=2) + ";\n")
    print("\nSaved to js/stats.js")
