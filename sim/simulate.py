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
    # MKM surveil duals (2024). ALWAYS ETB tapped (verified via Scryfall —
    # there is NO "fewer than 2 other lands" exception). Tap for two colors.
    # Surveil 1 on ETB. Basic-typed (fetchable). No life cost.
    "Meticulous Archive":          L({"W", "U"}, tapped=True),
    "Elegant Parlor":              L({"R", "W"}, tapped=True),
    "Thundering Falls":            L({"U", "R"}, tapped=True),
    # Fast lands (Spirebluff Canal cycle). ETB tapped UNLESS you control ≤2
    # other lands — i.e. untapped on T1-T3, tapped from T4+. Not basic-typed
    # (not fetchable). No life cost.
    "Seachrome Coast":             L({"W", "U"}),
    "Spirebluff Canal":            L({"U", "R"}),
    "Inspiring Vantage":           L({"R", "W"}),
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

# --- Optionality scoring -----------------------------------------------------
# Per user: "the more options we have, the better. So instead of just saying
# what's the highest priority spell I can cast, say given my spells, does
# this land enable me to cast them? Each additional option is worth
# something too." This generalizes — a Phelia+Phlage hand benefits more
# from a fetch that enables BOTH plays than from a fetch that enables just
# Phlage alone, because optionality is what gives competitive edge.
#
# Implementation: option_value(castable_set, priority_list) returns
#   priority_of_best_castable + EXTRA_OPTION_WEIGHT * sum(priority of others)
# where priority(spell) = len(priority_list) - index. Best spell has the
# largest priority value.
EXTRA_OPTION_WEIGHT = 0.30  # each additional castable option worth 30% of its raw priority


def option_value(castable_spells, priority_list):
    """Score a set of castable spells. Higher = more options/better options."""
    if not castable_spells:
        return 0.0
    L = len(priority_list)
    # Map each castable spell to its priority value (higher = more important)
    priorities = []
    for s in castable_spells:
        try:
            idx = priority_list.index(s)
        except ValueError:
            idx = L  # not in priority list — small value
        priorities.append(L - idx)
    priorities.sort(reverse=True)
    primary = priorities[0]
    extras = sum(priorities[1:])
    return primary + EXTRA_OPTION_WEIGHT * extras


# Spell cost map shared between pick_land's lookahead and the actual cast loop.
COST_MAP = {
    "Erode": {"W": 1}, "Path to Exile": {"W": 1}, "Galvanic Discharge": {"R": 1},
    "Cleansing Wildfire": {"R": 1, "G": 1}, "Price of Freedom": {"R": 1, "G": 1},
    "Phelia": {"W": 1, "G": 1}, "White Orchid Phantom": {"W": 2},
    "Phlage": {"R": 1, "W": 1, "G": 1},
    "Wrath of the Skies": {"W": 2, "G": 2}, "Wrath of God": {"W": 2, "G": 2},
    "The Legend of Roku": {"R": 2, "G": 2},
    "Quantum Riddler": {"U": 2, "G": 3},
    "Solitude": {"W": 1, "G": 4},
    "Snapcaster Mage": {"U": 1, "G": 1},
    "Ephemerate": {"W": 1},
}

CAST_PRIORITIES_BY_TURN = {
    1: ["Erode", "Path to Exile", "Galvanic Discharge"],
    2: ["Cleansing Wildfire", "Price of Freedom", "Phelia", "Erode", "Path to Exile", "Galvanic Discharge"],
    3: ["Phlage", "Cleansing Wildfire", "Price of Freedom", "White Orchid Phantom", "Phelia"],
    4: ["Wrath of the Skies", "Wrath of God", "The Legend of Roku", "Cleansing Wildfire", "Price of Freedom", "White Orchid Phantom"],
    5: ["Quantum Riddler", "Solitude", "Cleansing Wildfire", "Price of Freedom", "Phlage", "Erode"],
}

def _avail_from_battlefield(battlefield, just_played_idx=None):
    """Compute available untapped color sources from battlefield. Skips a
    just-played tapped land (it ETB'd this turn)."""
    avail = []
    for i, l in enumerate(battlefield):
        if CARDS[l]["tapped"] and i == just_played_idx:
            continue
        avail.append(CARDS[l]["produces"])
    return avail


def pick_land(hand, battlefield, turn, hand_cast_priorities=None, library=None):
    """Context-aware land choice. Tries each land option in hand and picks
    the one that ENABLES the highest-priority cast this turn. Falls back to
    color-fixing heuristic when no spell is castable regardless of choice.

    Reasoning:
      - For each land L in hand, simulate playing L (and cracking if fetch).
      - Compute available mana given L is in play.
      - Find the highest-priority spell in cast_priorities that becomes
        castable with L played.
      - Pick L with the highest-priority enabling spell.
      - Tie-break: prefer untapped result, then color count, then basic.

    This captures the user's insight: pick_land shouldn't be a static
    sequence — it should depend on what we have in hand and what we'd
    like to cast.
    """
    lands = [c for c in hand if CARDS[c]["land"]]
    if not lands:
        return None

    if hand_cast_priorities is None:
        hand_cast_priorities = CAST_PRIORITIES_BY_TURN.get(turn, [])

    # Castable spells we care about, in priority order
    spells_in_hand = [s for s in hand_cast_priorities if s in hand and s in COST_MAP]

    have_colors = set().union(*[CARDS[l]["produces"] for l in battlefield]) if battlefield else set()
    early_game = turn <= 4

    def land_eval(land):
        """Returns (-option_value, is_tapped, -new_color_gain, not_is_basic).

        Lower tuple = better. Primary score is option_value: how many of
        my desired spells can I cast if I play this land? Both the best
        spell and the breadth of additional options count.
        """
        # Determine effective produces if this is a fetch (it'll resolve)
        if library is not None and land in FETCH_TARGETS_FOR_PICK:
            target = _best_fetch_target(land, battlefield, library, spells_in_hand, hand, turn)
            effective_produces = CARDS[target]["produces"] if target else CARDS[land]["produces"]
            effective_tapped = CARDS[target]["tapped"] if target else False
        else:
            effective_produces = CARDS[land]["produces"]
            effective_tapped = CARDS[land]["tapped"]

        # If this land would be tapped, it doesn't add to avail this turn.
        if effective_tapped:
            avail_after = [CARDS[l]["produces"] for l in battlefield
                           if not CARDS[l]["tapped"]]
        else:
            avail_after = [CARDS[l]["produces"] for l in battlefield
                           if not CARDS[l]["tapped"]] + [effective_produces]

        # Compute the SET of spells castable given this land choice.
        # This is the optionality view: not just "best castable" but
        # "which options open up?"
        castable_now = [s for s in spells_in_hand if can_pay_cost(avail_after, COST_MAP[s])]
        opt_val = option_value(castable_now, hand_cast_priorities)

        new_color_gain = len(set(effective_produces) - have_colors - {"C"})
        is_basic = CARDS[land]["basic"]

        # Negate option_value so that lower-tuple = better in sort.
        if early_game:
            return (-opt_val, effective_tapped, -new_color_gain, not is_basic)
        else:
            return (-opt_val, -new_color_gain, effective_tapped, not is_basic)

    lands.sort(key=land_eval)
    return lands[0]


def _best_fetch_target(fetch, battlefield, library, spells_in_hand, hand, turn):
    """Pick fetch target by option_value: which target gives the best set of
    spell options? Each candidate is scored by:
      - option_value of spells castable given this target ETB'd
      - tie-break: prefer no-damage targets (surveil dual > basic > shock)

    The user's optionality principle applied: a surveil dual that enables
    Phelia (and surveils 1 for future) competes against a shock that
    enables Phelia + Phlage (more options now, costs life).
    """
    candidates = FETCH_TARGETS_FOR_PICK.get(fetch, [])
    candidates_in_lib = [c for c in candidates if c in library]
    if not candidates_in_lib:
        return None

    priority_list = CAST_PRIORITIES_BY_TURN.get(turn, [])

    def score_target(cand):
        produces = CARDS[cand]["produces"]
        is_tapped = CARDS[cand]["tapped"]
        is_shock = cand in SHOCK_LANDS_SET
        is_surveil = cand in SURVEIL_DUAL_LANDS_SET
        is_basic = cand in {"Plains", "Mountain", "Island", "Swamp", "Forest"}

        # Compute avail_after fetching this target
        if is_tapped:
            avail_after = [CARDS[l]["produces"] for l in battlefield if not CARDS[l]["tapped"]]
        else:
            avail_after = [CARDS[l]["produces"] for l in battlefield if not CARDS[l]["tapped"]] + [produces]

        # What spells can I cast NOW with this target?
        castable_now = [s for s in spells_in_hand if can_pay_cost(avail_after, COST_MAP[s])]
        opt_val_now = option_value(castable_now, priority_list)

        # Bonus for surveil 1: yard fuel + card selection. Worth ~0.5
        # in priority units (modest).
        surveil_bonus = 0.5 if is_surveil else 0.0

        # Penalty for shock damage: -2 life ≈ small score penalty in
        # the option-value framework. Roughly 0.4 per shock entering
        # untapped (calibrated against typical option values of 1-5).
        damage_penalty = 0.4 if (is_shock and not is_tapped) else 0.0

        # Color-fixing value for FUTURE turns: count new colors added
        have_colors = set().union(*[CARDS[l]["produces"] for l in battlefield]) if battlefield else set()
        new_colors = len(set(produces) - have_colors - {"C"})
        future_color_bonus = 0.4 * new_colors  # each new color worth 0.4

        total = opt_val_now + surveil_bonus + future_color_bonus - damage_penalty
        # Lower tuple = better. Primary: -total. Tie-break by category.
        return (-total, is_shock and not is_tapped, not is_surveil, not is_basic)

    candidates_in_lib.sort(key=score_target)
    return candidates_in_lib[0]


SHOCK_LANDS_SET = {"Sacred Foundry", "Hallowed Fountain", "Steam Vents",
                   "Stomping Ground", "Breeding Pool", "Watery Grave",
                   "Blood Crypt", "Godless Shrine", "Overgrown Tomb",
                   "Temple Garden"}
SURVEIL_DUAL_LANDS_SET = {"Meticulous Archive", "Elegant Parlor", "Thundering Falls"}

# Module-level FETCH_TARGETS for use by pick_land's fetch resolution.
# Mirrors the in-loop FETCH_TARGETS used at land-play time. Ordered so the
# resolver can iterate but the actual choice is made by _best_fetch_target.
FETCH_TARGETS_FOR_PICK = {
    "Scalding Tarn":      ["Steam Vents", "Hallowed Fountain", "Sacred Foundry",
                           "Meticulous Archive", "Thundering Falls", "Elegant Parlor",
                           "Island", "Mountain"],
    "Arid Mesa":          ["Sacred Foundry", "Hallowed Fountain", "Steam Vents",
                           "Meticulous Archive", "Elegant Parlor", "Thundering Falls",
                           "Mountain", "Plains"],
    "Flooded Strand":     ["Hallowed Fountain", "Sacred Foundry", "Steam Vents",
                           "Meticulous Archive", "Elegant Parlor", "Thundering Falls",
                           "Plains", "Island"],
    "Misty Rainforest":   ["Hallowed Fountain", "Steam Vents", "Meticulous Archive",
                           "Thundering Falls", "Island"],
    "Polluted Delta":     ["Hallowed Fountain", "Steam Vents", "Meticulous Archive",
                           "Thundering Falls", "Island"],
    "Marsh Flats":        ["Sacred Foundry", "Hallowed Fountain", "Meticulous Archive",
                           "Elegant Parlor", "Plains"],
    "Wooded Foothills":   ["Sacred Foundry", "Steam Vents", "Elegant Parlor",
                           "Thundering Falls", "Mountain"],
    "Bloodstained Mire":  ["Sacred Foundry", "Steam Vents", "Elegant Parlor",
                           "Thundering Falls", "Mountain"],
    "Windswept Heath":    ["Sacred Foundry", "Hallowed Fountain", "Meticulous Archive",
                           "Elegant Parlor", "Plains"],
}

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

            # 2. Land drop (context-aware: looks at hand to pick land that
            # enables the highest-priority cast this turn)
            cast_pri_now = CAST_PRIORITIES_BY_TURN.get(turn, [])
            land = pick_land(hand, battlefield, turn, hand_cast_priorities=cast_pri_now, library=library)
            if land:
                hand.remove(land)
                # Fetchlands: crack immediately. Fetch goes to yard, replaced by best dual.
                # Fetch priority: shocks FIRST (they ETB untapped, you can cast
                # this turn). Surveil duals are valid fetch targets but only
                # taken when no shock is needed — that's handled below by
                # checking if the player needs untapped mana this turn.
                FETCH_TARGETS = {
                    "Scalding Tarn":      ["Steam Vents", "Hallowed Fountain", "Sacred Foundry",
                                           "Meticulous Archive", "Thundering Falls", "Elegant Parlor",
                                           "Island", "Mountain"],
                    "Arid Mesa":          ["Sacred Foundry", "Hallowed Fountain", "Steam Vents",
                                           "Meticulous Archive", "Elegant Parlor", "Thundering Falls",
                                           "Mountain", "Plains"],
                    "Flooded Strand":     ["Hallowed Fountain", "Sacred Foundry", "Steam Vents",
                                           "Meticulous Archive", "Elegant Parlor", "Thundering Falls",
                                           "Plains", "Island"],
                    "Misty Rainforest":   ["Hallowed Fountain", "Steam Vents", "Meticulous Archive", "Thundering Falls", "Island"],
                    "Polluted Delta":     ["Hallowed Fountain", "Steam Vents", "Meticulous Archive", "Thundering Falls", "Island"],
                    "Marsh Flats":        ["Sacred Foundry", "Hallowed Fountain", "Meticulous Archive", "Elegant Parlor", "Plains"],
                    "Wooded Foothills":   ["Sacred Foundry", "Steam Vents", "Elegant Parlor", "Thundering Falls", "Mountain"],
                    "Bloodstained Mire":  ["Sacred Foundry", "Steam Vents", "Elegant Parlor", "Thundering Falls", "Mountain"],
                    "Windswept Heath":    ["Sacred Foundry", "Hallowed Fountain", "Meticulous Archive", "Elegant Parlor", "Plains"],
                }
                if land in FETCH_TARGETS:
                    graveyard.append(land)  # fetchland goes to yard
                    # Context-aware target choice (per user feedback —
                    # "the optionality there is important"). _best_fetch_target
                    # decides:
                    #   - shock (untapped, -2 life) if needed for a cast this turn
                    #   - surveil dual (no damage + surveil) if no immediate cast
                    #   - shock for color-fixing if no surveil dual reachable
                    #   - basic as last resort
                    spells_in_hand = [s for s in cast_pri_now if s in hand and s in COST_MAP]
                    best = _best_fetch_target(land, battlefield, library, spells_in_hand, hand, turn)
                    if best is not None:
                        library.remove(best)
                        battlefield.append(best)
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

            spell_cast_this_turn = False
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
                    spell_cast_this_turn = True
                    # Engine cards force opp to search a basic when cast on opp board/lands
                    if spell in ("Erode", "Path to Exile", "Cleansing Wildfire", "Price of Freedom"):
                        basics_tutored += 1
                    if spell == "White Orchid Phantom":
                        basics_tutored += 1
                    # Track energy banked from Galvanic for Wrath synergy (per-trial cumulative)
                    if spell == "Galvanic Discharge":
                        energy_banked += 2  # bank 2/3 (1 used as removal)
                    break  # one spell per turn

            # Per user: track P(spell cast on turn N). Used by score.py to
            # compute shock-untapped probability from sim data instead of a
            # hardcoded curve. Centralized so other components can reuse it.
            if spell_cast_this_turn:
                misc[f"spell_cast_T{turn}"] += 1

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
        # P(spell cast on turn N) — sim-measured. Used by score.py to model
        # shock-untapped damage probability and other turn-conditional decisions.
        **{f"p_spell_cast_T{t}": misc.get(f"spell_cast_T{t}", 0) / trials
           for t in range(1, max_turn + 1)},
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
