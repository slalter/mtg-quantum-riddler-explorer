"""Composite scoring v2 — applies per-card DR curves and conditional power.

Three components:
  - Effective Power Density (50%)
  - Castability  (30%)
  - Mana Efficiency  (20%) [proxied by per-turn relevant-play probability]

Per-card DR curves (per card, not universal). Multiple QR copies don't DR.
Engine cards (Erode/Path/Wildfire/PoF/Phantom) double in power once we've
crossed the depletion threshold (3 basic-tutors forced).
"""
import math
from collections import Counter

# Per-card config: base power, DR curve (multipliers for copy 1..4), and conditional flags
CARD_POWER = {
    "Quantum Riddler":      {"base": 9,   "dr": [1.0, 1.0, 1.0, 1.0],   "engine": False, "legendary": False},
    # Phlage DR softened from [1.0, 0.5, 0.2, 0.1] to [1.0, 0.85, 0.55, 0.30] per
    # user observation: Helix-mode (cast → trigger → self-sac to yard) doesn't
    # care about the legendary rule. Each extra copy in hand is another T3
    # Helix + escape-fuel, not a dead card. The old curve was over-counting
    # the legendary penalty for a card whose dominant mode bypasses it.
    "Phlage":               {"base": 9,   "dr": [1.0, 0.85, 0.55, 0.30], "engine": False, "legendary": True},
    "The Legend of Roku":   {"base": 8,   "dr": [1.0, 0.4, 0.1, 0.0],   "engine": False, "legendary": True},
    "Phelia":               {"base": 7,   "dr": [1.0, 0.4, 0.1, 0.0],   "engine": False, "legendary": True},
    "Solitude":             {"base": 8,   "dr": [1.0, 0.85, 0.65, 0.45],"engine": False, "legendary": False, "needs_white_density": True},
    "White Orchid Phantom": {"base": 7,   "dr": [1.0, 0.9, 0.75, 0.55], "engine": True,  "legendary": False},
    "Wrath of the Skies":   {"base": 8,   "dr": [1.0, 0.7, 0.4, 0.2],   "engine": False, "legendary": False},
    "Wrath of God":         {"base": 6,   "dr": [1.0, 0.6, 0.3, 0.1],   "engine": False, "legendary": False},
    "Cleansing Wildfire":   {"base": 7,   "dr": [1.0, 1.0, 1.0, 0.95],  "engine": True,  "legendary": False},
    "Price of Freedom":     {"base": 7.5, "dr": [1.0, 1.0, 1.0, 0.95],  "engine": True,  "legendary": False},
    "Erode":                {"base": 7,   "dr": [1.0, 1.0, 1.0, 0.95],  "engine": True,  "legendary": False},
    "Path to Exile":        {"base": 7,   "dr": [1.0, 1.0, 1.0, 0.95],  "engine": True,  "legendary": False},
    "Galvanic Discharge":   {"base": 6,   "dr": [1.0, 0.9, 0.8, 0.7],   "engine": False, "legendary": False},
    "Snapcaster Mage":      {"base": 7,   "dr": [1.0, 0.85, 0.65, 0.45],"engine": False, "legendary": False},
    "Ephemerate":           {"base": 6,   "dr": [1.0, 0.8, 0.5, 0.3],   "engine": False, "legendary": False, "needs_blink_targets": True},
    "Flashback":            {"base": 6,   "dr": [1.0, 0.8, 0.5, 0.3],   "engine": False, "legendary": False},
}

# Cards that count as good Ephemerate / Phelia attack-blink targets
# Per-blink value of each target. Phlage is 0 (sacs on return).
# Per user feedback: Phelia returns target at END STEP (instant-speed-only).
# That changes which targets actually combo:
#   - QR: warp → blink → permanent. Strong combo.
#   - Phantom: blink → 2nd ETB land destruction. Good.
#   - Solitude: only OK because Phelia can't blink an EVOKED Solitude (it's
#     exiled by evoke replacement). Only hard-cast Solitude can be blinked.
#     Most Solitudes are evoked → blink rarely triggers.
#   - Snap: poor. Phelia exiles Snap on attack, returns end step. Snap
#     flashbacks happen on YOUR main phase; the end-step return doesn't
#     reset the flashback timer. Net: roughly a 2/1 body, no extra value.
BLINK_TARGET_VALUE = {
    "Quantum Riddler": 9,        # warp → blink → permanent
    "White Orchid Phantom": 7,   # repeat ETB land destruction (basic-tutor)
    "Solitude": 4,               # was 9 — only hard-cast Solitudes blink (most are evoked)
    "Snapcaster Mage": 1,        # was 4 — end-step return misses flashback window
    # explicitly excluded: Phlage (sacs on return), Phelia (legendary)
}

# Set of "white cards" for Solitude evoke probability
WHITE_CARDS = {"Erode", "Path to Exile", "Cleansing Wildfire", "Price of Freedom", "Phelia", "White Orchid Phantom",
               "Solitude", "Ephemerate", "Wrath of the Skies", "Wrath of God"}
# Phlage is W/R hybrid — counts as white for Solitude evoke.
WHITE_CARDS.add("Phlage")

DEPLETION_THRESHOLD = 3  # opp likely out of basics after this many tutors

import math
def depletion_multiplier(avg_basics_T6, threshold=3.0, sigma=1.0):
    """Smooth sigmoid 1.0 → 2.0 centered at threshold.
    avg=2 → 1.27, avg=3 → 1.50, avg=4 → 1.73, avg=5 → 1.88, avg=6 → 1.95"""
    return 1.0 + 1.0 / (1 + math.exp(-(avg_basics_T6 - threshold) / sigma))

# Lands and other non-power cards that get DR via slot
LAND_POWER = {
    "Arena of Glory":  {"base": 4, "dr": [1.0, 0.4, 0.1, 0.0]},  # one copy enables Phlage haste; second redundant
    "Sunken Citadel":  {"base": 2, "dr": [1.0, 0.7, 0.4, 0.2]},  # base; bumped conditionally per land-ability count
    "Cori Mountain Monastery": {"base": 3, "dr": [1.0, 0.4, 0.1, 0.0]},  # 3R-tap exile-play; 1-of utility, multiples redundant
    "Eiganjo, Seat of the Empire": {"base": 2, "dr": [1.0, 0.3, 0.0, 0.0]},
    "Otawara, Soaring City":      {"base": 2, "dr": [1.0, 0.3, 0.0, 0.0]},
    "Sokenzan, Crucible of Defiance": {"base": 2, "dr": [1.0, 0.3, 0.0, 0.0]},
}

def hypergeom_prob_at_least_one(K, N, n):
    """P(at least 1 success) when K successes exist among N items, drawing n."""
    if K == 0 or n == 0:
        return 0.0
    # P(zero) = C(N-K, n) / C(N, n)
    if n > N - K:
        return 1.0
    num = 1.0
    den = 1.0
    for i in range(n):
        num *= (N - K - i)
        den *= (N - i)
    return 1 - (num / den)

def effective_power(deck_def, sim_result):
    """Compute effective power density: Σ(qty × per-copy effective_power) / 60.
    Engine cards multiplier = sigmoid of (avg_basics_T6 - depletion_threshold).
    Includes Galvanic→Wrath energy synergy and Phlage→Arena-of-Glory."""
    total_basics_T6 = sim_result["misc"].get("avg_basics_tutored_T6", 0)
    engine_multiplier = depletion_multiplier(total_basics_T6, threshold=DEPLETION_THRESHOLD, sigma=1.0)
    depleted = engine_multiplier > 1.5

    # --- Synergy: Galvanic Discharge → Wrath of the Skies (now from sim, not approx) ---
    # Per user: this should be a true 'if drawn, then...' iteration.
    # The sim now tracks avg cumulative energy_banked_T4 = avg energy actually
    # available when Wrath is cast at T4. Multiply by 0.7 for power bonus, cap at 6.
    avg_energy_T4 = sim_result["misc"].get("avg_energy_banked_T4", 0)
    wrath_count = deck_def.get("Wrath of the Skies", 0)
    wrath_energy_bonus = min(avg_energy_T4 * 0.7, 6.0) if wrath_count > 0 else 0.0

    # --- Synergy: Phlage → Arena of Glory ---
    # Having ≥1 Arena of Glory makes Phlage T3 hardcast a haste play (9 dmg vs 3).
    arena_count = deck_def.get("Arena of Glory", 0)
    phlage_arena_bonus = 1.5 if arena_count >= 1 else 0.0  # +1.5 effective power per Phlage

    # --- LATE-GAME SCALING ---
    # QR's "draw +1 if hand ≤ 1" triggers when we've burned through our hand.
    # Sim tracks avg_non_land_in_hand_T10. If average ≤ 1, QR is in hand-empty mode.
    # Each QR copy gains power based on how often it's in hand-empty mode.
    avg_hand_T10 = sim_result["misc"].get("avg_non_land_in_hand_T10", 5)
    avg_hand_T12 = sim_result["misc"].get("avg_non_land_in_hand_T12", 5)
    avg_late_hand = (avg_hand_T10 + avg_hand_T12) / 2
    # P(hand ≤ 1 at any given late turn) — rough proxy: 1 if avg_late_hand < 1.5, scaling down
    p_hand_empty_late = max(0, min(1, (2 - avg_late_hand) / 1.5))
    qr_late_bonus = p_hand_empty_late * 1.5  # up to +1.5 to QR base power

    # Phlage escape scaling: based on yard density and basic_tutor count by T8.
    # Phlage escape is most valuable when:
    #   - Phlage in yard reliably (Phlage drawn AND cast as removal earlier)
    #   - Yard has 5+ other cards
    #   - We can pay RRWW
    # Use a proxy: avg_basics_tutored_T8 ≈ avg spells cast by T8 (roughly indicates yard fill)
    avg_tutors_T8 = sim_result["misc"].get("avg_basics_tutored_T8", 0)
    if avg_tutors_T8 == 0:
        avg_tutors_T8 = sim_result["misc"].get("avg_basics_tutored_T7", 0) * 1.2
    yard_density_proxy = min(avg_tutors_T8 / 4.0, 1.0)  # saturated at 4+ basic-tutors-by-T8
    phlage_late_bonus = yard_density_proxy * 1.0  # up to +1.0 per Phlage

    # Compute white-card density for Solitude conditional (excluding Solitude itself)
    white_in_deck = sum(qty for c, qty in deck_def.items()
                        if c in WHITE_CARDS and c != "Solitude")
    # Compute Ephemerate/Phelia target value
    # Effective avg target value = sum(qty × target_value) / sum(qty of targets)
    target_qty = sum(qty for c, qty in deck_def.items() if c in BLINK_TARGET_VALUE)
    target_value_sum = sum(qty * BLINK_TARGET_VALUE[c] for c, qty in deck_def.items() if c in BLINK_TARGET_VALUE)
    avg_target_value = target_value_sum / max(target_qty, 1)

    # Pre-compute Sunken Citadel conditional bonus.
    # Citadel taps for 2-of-color usable only on land abilities. Its value
    # scales with the count of land activations the deck wants to power.
    land_activations = (
        deck_def.get("Field of Ruin", 0)
        + deck_def.get("Demolition Field", 0)
        + deck_def.get("Arena of Glory", 0)
        + deck_def.get("Cori Mountain Monastery", 0)
        + deck_def.get("Eiganjo, Seat of the Empire", 0)
        + deck_def.get("Otawara, Soaring City", 0)
        + deck_def.get("Sokenzan, Crucible of Defiance", 0)
    )
    sunken_bonus = 0.5 * land_activations  # +0.5 per land-activation card in the deck

    total = 0.0
    for card, qty in deck_def.items():
        cfg = CARD_POWER.get(card)
        if not cfg:
            # Check land power
            land_cfg = LAND_POWER.get(card)
            if land_cfg:
                land_dr = land_cfg["dr"]
                land_base = land_cfg["base"]
                # Sunken Citadel: conditional bonus
                if card == "Sunken Citadel":
                    land_base = land_base + sunken_bonus
                for n in range(1, qty + 1):
                    mult = land_dr[min(n - 1, len(land_dr) - 1)]
                    total += land_base * mult
            continue
        base = cfg["base"]
        dr = cfg["dr"]

        # Engine conditional scaling (sigmoid)
        if cfg.get("engine"):
            base = base * engine_multiplier

        # Galvanic→Wrath bonus
        if card == "Wrath of the Skies":
            base = base + wrath_energy_bonus

        # Phlage→Arena bonus + late-game escape scaling
        if card == "Phlage":
            base = base + phlage_arena_bonus + phlage_late_bonus

        # Quantum Riddler late-game hand-empty scaling
        if card == "Quantum Riddler":
            base = base + qr_late_bonus

        # Solitude conditional. If we can't evoke (no other white card in hand)
        # AND we're pre-T5, Solitude is effectively a dead card in hand (power ~1).
        # At T5+ we can hardcast for {4}{W}, so power returns.
        # Effective power = blended over turns:
        #   - T2-4 (3/8 of game weight): P(evoke OK) * full_power + (1-P) * 1
        #   - T5-7 (5/8 of game weight): full_power (hardcast or evoke both work)
        if cfg.get("needs_white_density"):
            ps = [hypergeom_prob_at_least_one(white_in_deck, 59, h) for h in (5, 6, 7, 7)]
            p_evoke = sum(ps) / len(ps)
            pre_T5_eff = p_evoke * base + (1 - p_evoke) * 1.0
            post_T5_eff = base
            base = (3/8) * pre_T5_eff + (5/8) * post_T5_eff

        # Ephemerate conditional: scale by avg target value / max possible
        if cfg.get("needs_blink_targets"):
            base = base * (avg_target_value / 9.0)

        # Apply DR per copy
        for n in range(1, qty + 1):
            mult = dr[min(n - 1, len(dr) - 1)]
            total += base * mult

    # Basic-land penalty using real probabilities.
    # Field of Ruin needs a basic in YOUR library to fetch. Demolition Field
    # only gives opp a basic (your basic-count doesn't matter for DF).
    # Math: with B basics in deck (60), after drawing ~13 cards by T6
    # (~13/60 hit rate on basics), expected basics drawn ≈ B*13/60.
    # Library basics remaining = B - drawn. We need ≥1 left when activating FoR.
    # Probability that NO basics remain when we want to FoR = hypergeometric.
    basics_in_deck = sum(deck_def.get(b, 0) for b in ("Plains", "Mountain", "Island"))
    for_count = deck_def.get("Field of Ruin", 0)
    df_count = deck_def.get("Demolition Field", 0)
    # Per user: BOTH FoR and DF need basics (deck-wide mana base needs basics
    # to support fetches and the FoR basic-fetch effect).
    for_or_df_count = for_count + df_count
    fetch_count = sum(deck_def.get(f, 0) for f in ("Scalding Tarn", "Arid Mesa", "Flooded Strand"))

    # Probability of having ≥1 basic in library when FoR activates on T3-4 (≈11 cards drawn so far).
    # Approximation: P(at least 1 basic in 49 unseen cards) given B basics, 11 already drawn.
    # If B basics in 60-card deck, prob ≥1 basic in remaining 49 = 1 - C(49-B,49)/C(49,49) but B≤49.
    # Simpler: P(no basic in remaining 49) = C(60-B, 49)/C(60, 49) = product(60-B-i / 60-i for i in 0..48)
    # = (60-B)(59-B)...(12-B) / 60·59...12 — when B=0, ratio = 1 → P_no_basic = 1.
    def p_at_least_one_basic_left(B, drawn=11):
        if B == 0:
            return 0.0
        if B > 60 - drawn:
            return 1.0
        # P(no basic among remaining 49 unseen of 60)... more accurate to compute conditionally.
        # P(basics still in library | drew `drawn` cards) — by symmetry, expected basics in library = B*(1 - drawn/60).
        # Use a simpler proxy: P ≈ 1 - (1 - B/60)^drawn ... no, that's wrong.
        # Direct: P(at least 1 basic remains) = 1 - P(all B basics already drawn or in play)
        # = 1 - C(drawn, B) / C(60, B) for drawn ≥ B, else = 1.
        if drawn < B:
            return 1.0
        from math import comb
        return 1 - comb(drawn, B) / comb(60, B)

    # === Continuous basic-shortfall model (per user feedback) ===
    # Demand = expected basics consumed by mid/long game.
    # Supply = basics in deck.
    # If demand > supply: fetches get small power decline (can't reliably find basic),
    # FoR/DF "brick" partially (their basic-fetch effect fails — they become colorless utility).
    #
    # Demand components (calibrated for ~T8 mid-game):
    #   drawn_basics ≈ basics × 13/60 (cards drawn by T8)
    #   FoR consumption ≈ 1.0 × FoR copies in deck (each self-sac wants a basic)
    #   fetch consumption ≈ 0.33 × fetch copies (each crack ~1/3 grabs a basic)
    drawn_basics_by_T8 = basics_in_deck * 13 / 60
    fetch_basic_demand = fetch_count / 3.0
    for_basic_demand = for_count * 1.0  # FoR fetches a basic for YOU
    df_basic_demand = df_count * 0.0    # DF only gives opp a basic
    total_demand = drawn_basics_by_T8 + fetch_basic_demand + for_basic_demand + df_basic_demand
    shortfall = max(0, total_demand - basics_in_deck)

    if shortfall > 0:
        # Each unit of shortfall = ~one trigger that fails to find a basic.
        # Distribute the impact:
        #   - Fetches: small power decline. Each fetch's value drops by 0.3 per shortfall unit
        #     up to a max of 1.5 per fetch.
        #   - FoR: bricks partially. Each FoR loses up to 60% of its value as shortfall increases.
        fetch_decline = min(shortfall * 0.3, 1.5)
        total -= fetch_count * fetch_decline

        # FoR brick scaling: linear in shortfall, capped at 60% loss
        for_brick_factor = min(shortfall * 0.15, 0.6)  # 0 at no shortfall, 0.6 at shortfall ≥ 4
        # Each FoR loses 6 power × brick_factor
        total -= for_count * 6 * for_brick_factor

    # Mild floor: 0-1 basics still bad even with low FoR/DF count
    if basics_in_deck < 2:
        total *= (1 - 0.10 * (2 - basics_in_deck))

    # Normalize by deck size (60)
    return total / 60

def castability_score(sim_result, deck_def):
    """Average per-card conditional castability, weighted by importance."""
    weights = {
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
        "phlage_escape_T7":  2,
    }
    requires = {
        "erode_T1": "Erode", "path_T1": "Path to Exile", "galvanic_T1": "Galvanic Discharge",
        "phantom_T2": "White Orchid Phantom", "phantom_T3": "White Orchid Phantom",
        "phelia_T2": "Phelia", "phelia_T3": "Phelia",
        "wildfire_T2": "Cleansing Wildfire", "pof_T2": "Price of Freedom",
        "phlage_T3_removal": "Phlage", "warp_qr_T2": "Quantum Riddler",
        "warp_qr_T3": "Quantum Riddler", "hardcast_qr_T5": "Quantum Riddler",
        "hardcast_qr_T6": "Quantum Riddler", "wos_T4": "Wrath of the Skies",
        "roku_T4": "The Legend of Roku", "phlage_escape_T7": "Phlage",
    }
    total = 0.0
    denom = 0.0
    for metric, w in weights.items():
        req = requires.get(metric)
        if req and deck_def.get(req, 0) == 0:
            continue
        e = sim_result.get(metric)
        if not e:
            continue
        cast = e.get("castable_given_in_hand_pct")
        if cast is None:
            continue
        total += cast * w
        denom += w
    return (total / denom) if denom else 0

def mana_efficiency_score(sim_result):
    """Proxy: cumulative (basics_tutored + cast spell density) per turn,
    weighted by per-turn importance. Currently approximated by basics_tutored
    progression toward target."""
    importance = {3: 9, 4: 8, 5: 7, 6: 6, 7: 4}
    # Targets reflect: depletion threshold hit by T4, then accumulate deadland triggers
    targets = {3: 2.0, 4: 3.0, 5: 4.0, 6: 5.0, 7: 6.0}
    total = 0.0
    denom = 0.0
    for turn, w in importance.items():
        avg = sim_result["misc"].get(f"avg_basics_tutored_T{turn}", 0)
        target = targets[turn]
        score = min(avg / target, 1.0) * 100
        total += score * w
        denom += w
    return total / denom if denom else 0

def stuff_to_do_score(sim_result):
    """Flood penalty across late game (T7-T12). Decks that empty their hand
    early and draw lands top-deck after T8 are flooding.
    Score = 100 if avg ≥ 1.5 non-lands at T8+T10+T12, scaling down from there."""
    avg_T7 = sim_result["misc"].get("avg_non_land_in_hand_T7", 0)
    avg_T8 = sim_result["misc"].get("avg_non_land_in_hand_T8", 0)
    avg_T10 = sim_result["misc"].get("avg_non_land_in_hand_T10", 0)
    avg_T12 = sim_result["misc"].get("avg_non_land_in_hand_T12", 0)
    pct_zero_T8 = sim_result["misc"].get("pct_non_land_zero_T8", 0)
    pct_zero_T10 = sim_result["misc"].get("pct_non_land_zero_T10", 0)
    pct_zero_T12 = sim_result["misc"].get("pct_non_land_zero_T12", 0)
    # Average non-lands across late game — weighted toward T10/T12 (true flood window)
    avg_combined = (avg_T7 * 0.1 + avg_T8 * 0.3 + avg_T10 * 0.3 + avg_T12 * 0.3)
    spell_score = min(avg_combined / 1.5, 1.0) * 100
    # Subtract the % of trials where you flooded (zero non-lands) — averaged across T8/T10/T12
    flood_pct_avg = (pct_zero_T8 + pct_zero_T10 + pct_zero_T12) / 3
    flood_score = 100 - flood_pct_avg
    return (spell_score + flood_score) / 2

SHOCK_LANDS = {"Sacred Foundry", "Hallowed Fountain", "Steam Vents",
               "Stomping Ground", "Breeding Pool", "Watery Grave",
               "Blood Crypt", "Godless Shrine", "Overgrown Tomb",
               "Temple Garden"}
# Fast lands (Spirebluff Canal cycle): ETB tapped when played as 4th+ land.
# Untapped early. Not basic-typed.
FAST_LANDS = {"Seachrome Coast", "Spirebluff Canal", "Inspiring Vantage"}
# MKM surveil duals: ALWAYS ETB tapped, surveil 1 on ETB. Basic-typed (fetchable).
SURVEIL_DUAL_LANDS = {"Meticulous Archive", "Elegant Parlor", "Thundering Falls"}
# Combined: lands that ETB tapped under some condition AND have no life cost.
ETB_MAYBE_TAPPED_LANDS = SURVEIL_DUAL_LANDS | FAST_LANDS

# Mid-turn fetched shocks: you cracked the fetch DURING the turn, almost
# always because you need the color now → almost always untapped.
P_FETCHED_SHOCK_UNTAPPED = 0.92


def p_shock_untapped_by_turn(turn, sim_result=None):
    """P(a hardcast shock plays UNTAPPED, paying 2 life) on a given turn.

    Per user feedback: this should be computed CENTRALLY from sim data —
    "how likely we are to spend a certain amount of mana on a certain
    turn". If sim_result provides p_spell_cast_T{n}, use it directly:
    if we cast a spell, we needed the mana, so the shock came in untapped.

    Falls back to a hardcoded curve if no sim data available (e.g. when
    color_reliability_score is called standalone for testing).
    """
    if sim_result is not None:
        p = sim_result["misc"].get(f"p_spell_cast_T{turn}")
        if p is not None:
            # If we cast a spell, the shock had to be untapped; otherwise
            # we'd have ETB'd tapped. Add a small ~0.10 probability for
            # "hold-up mana" turns (you might still want untapped even
            # without casting, e.g., pass-with-removal).
            return min(1.0, p + 0.10)
    # Fallback hardcoded curve
    fallback = {1: 0.95, 2: 0.85, 3: 0.75, 4: 0.55, 5: 0.40, 6: 0.25}
    return fallback.get(turn, 0.20)


def color_reliability_score(deck_def, n=4000, return_parts=False, sim_result=None):
    """Direct measurement of manabase quality + life safety.

    Simulates land-draw + fetch-cracking against THIS deck's specific
    shock pool. A fetch can only find what's in library at fetch time;
    once shocks are exhausted the fetch falls back to a basic.

    Tracks life loss:
      - Each fetch crack: -1 life
      - Each shock entering untapped: -2 life
    Surveil duals (Meticulous Archive et al.) and fast lands (Seachrome
    Coast et al.) ETB tapped when played as the 4th-or-later land — they
    cost 0 life but can be tempo-negative late.

    Aggregates probabilities of hitting key color requirements:
      - WUR by T3 (universal)
      - RW + 1 by T3 (Phlage hardcast — only if Phlage > 0)
      - RRWW by T5 (Phlage escape — only if Phlage > 0)
      - UU + 3 by T5 (QR hardcast — only if QR > 0)
      - WW + 2 by T4 (Wrath of the Skies — only if WoS > 0)
    Plus a life_safety component: avg life remaining after T6 damage,
    rewarding manabases that don't burn the player out.

    Returns 0-100.
    """
    import random
    from simulate import build_deck, CARDS

    # Shocks first (untapped, paid 2 life — usable this turn).
    # Surveil duals only fetched if a shock isn't needed.
    FETCH_TARGETS = {
        "Scalding Tarn":     ["Steam Vents", "Hallowed Fountain", "Sacred Foundry",
                              "Meticulous Archive", "Thundering Falls", "Elegant Parlor",
                              "Island", "Mountain"],
        "Arid Mesa":         ["Sacred Foundry", "Hallowed Fountain", "Steam Vents",
                              "Meticulous Archive", "Elegant Parlor", "Thundering Falls",
                              "Mountain", "Plains"],
        "Flooded Strand":    ["Hallowed Fountain", "Sacred Foundry", "Steam Vents",
                              "Meticulous Archive", "Elegant Parlor", "Thundering Falls",
                              "Plains", "Island"],
        "Misty Rainforest":  ["Hallowed Fountain", "Steam Vents", "Meticulous Archive", "Thundering Falls", "Island"],
        "Polluted Delta":    ["Hallowed Fountain", "Steam Vents", "Meticulous Archive", "Thundering Falls", "Island"],
        "Marsh Flats":       ["Sacred Foundry", "Hallowed Fountain", "Meticulous Archive", "Elegant Parlor", "Plains"],
        "Wooded Foothills":  ["Sacred Foundry", "Steam Vents", "Elegant Parlor", "Thundering Falls", "Mountain"],
        "Bloodstained Mire": ["Sacred Foundry", "Steam Vents", "Elegant Parlor", "Thundering Falls", "Mountain"],
        "Windswept Heath":   ["Sacred Foundry", "Hallowed Fountain", "Meticulous Archive", "Elegant Parlor", "Plains"],
    }

    def land_colors_now(card):
        """Actual colors a played land currently produces (post-crack)."""
        if card in CARDS and CARDS[card]["land"]:
            return set(CARDS[card]["produces"]) - {"C"}
        return set()

    def colors_in_play(in_play):
        out = set()
        for l in in_play:
            out |= land_colors_now(l)
        return out

    def color_count(in_play, color):
        return sum(1 for l in in_play if color in land_colors_now(l))

    deck_list = build_deck(deck_def)
    n_t3 = n_t4 = n_t5 = n_t6 = 0
    p_wur_t3 = 0
    p_phlage_t3 = 0
    p_wos_t4 = 0
    p_phlage_esc_t5 = 0
    p_qr_t5 = 0
    total_damage_t6 = 0
    total_surveils = 0  # for surveil bonus
    total_natural_tap_lands_T3 = 0  # tracks "drew a surveil dual T1-T3" tempo penalty

    has_phlage = deck_def.get("Phlage", 0) > 0
    has_qr = deck_def.get("Quantum Riddler", 0) > 0
    has_wos = deck_def.get("Wrath of the Skies", 0) > 0

    def _is_etb_tapped(card, n_other_lands):
        """Resolve the actual ETB-tapped status given the current turn state."""
        if card in SURVEIL_DUAL_LANDS:
            return True  # always tapped
        if card in FAST_LANDS:
            return n_other_lands >= 3  # tapped only as 4th+ land
        return CARDS[card].get("tapped", False)

    for _ in range(n):
        random.shuffle(deck_list)
        hand = deck_list[:7]
        library = deck_list[7:]
        # Each in_play element: (card_name, ETB_was_tapped_bool)
        in_play = []
        damage = 0
        surveils_this_game = 0
        natural_tap_in_early_game = 0  # tap-lands played T1-T3 = tempo loss

        for turn in range(1, 7):
            if turn > 1 and library:
                hand.append(library.pop(0))

            land_in_hand = [c for c in hand if CARDS[c]["land"]]
            if land_in_hand:
                have = colors_in_play([nm for nm, _ in in_play])
                n_other = len(in_play)
                def play_land_score(card):
                    # Prefer: more new colors > untapped > basic
                    will_etb_tapped = _is_etb_tapped(card, n_other)
                    if card in FETCH_TARGETS:
                        best_gain = -1
                        for cand in FETCH_TARGETS[card]:
                            if cand in library:
                                cand_colors = land_colors_now(cand)
                                g = len(cand_colors - have)
                                if g > best_gain:
                                    best_gain = g
                        return (-best_gain, False, 0)  # fetches always crackable, treat as untapped
                    return (-len(land_colors_now(card) - have), will_etb_tapped, 0)
                land_in_hand.sort(key=play_land_score)
                play = land_in_hand[0]
                hand.remove(play)

                if play in FETCH_TARGETS:
                    damage += 1  # crack cost
                    have = colors_in_play([nm for nm, _ in in_play])
                    # Find best target: prefer surveil dual (free + surveil),
                    # then shock that adds new color, then any shock, then basic.
                    fetched = None
                    for cand in FETCH_TARGETS[play]:
                        if cand in library and (land_colors_now(cand) - have):
                            fetched = cand
                            break
                    if fetched is None:
                        for cand in FETCH_TARGETS[play]:
                            if cand in library:
                                fetched = cand
                                break
                    if fetched is not None:
                        library.remove(fetched)
                        if fetched in SHOCK_LANDS:
                            # Mid-turn fetched shock: almost always untapped
                            # because you needed the color now.
                            if random.random() < P_FETCHED_SHOCK_UNTAPPED:
                                damage += 2
                                in_play.append((fetched, False))
                            else:
                                in_play.append((fetched, True))
                        elif fetched in SURVEIL_DUAL_LANDS:
                            surveils_this_game += 1
                            in_play.append((fetched, True))  # always tapped
                        elif fetched in FAST_LANDS:
                            tapped = (len(in_play) >= 3)
                            in_play.append((fetched, tapped))
                        else:
                            in_play.append((fetched, False))
                else:
                    if play in SHOCK_LANDS:
                        # Hardcast shock: turn-conditional damage driven by
                        # sim-measured P(spell cast this turn).
                        p_untapped = p_shock_untapped_by_turn(turn, sim_result)
                        if random.random() < p_untapped:
                            damage += 2
                            in_play.append((play, False))
                        else:
                            in_play.append((play, True))
                    elif play in SURVEIL_DUAL_LANDS:
                        surveils_this_game += 1
                        in_play.append((play, True))
                        if turn <= 3:
                            natural_tap_in_early_game += 1
                    elif play in FAST_LANDS:
                        tapped = (len(in_play) >= 3)
                        in_play.append((play, tapped))
                        if tapped and turn <= 3:
                            natural_tap_in_early_game += 1
                    elif CARDS[play].get("tapped", False):
                        in_play.append((play, True))
                        if turn <= 3:
                            natural_tap_in_early_game += 1
                    else:
                        in_play.append((play, False))

            # Untap step at end of turn
            in_play = [(name, False) for name, _ in in_play]

            this_turn_available = [name for name, t in in_play if not t]
            r = color_count(this_turn_available, "R")
            w = color_count(this_turn_available, "W")
            u = color_count(this_turn_available, "U")
            colors = colors_in_play(this_turn_available)
            n_in_play = len(this_turn_available)

            if turn == 3:
                n_t3 += 1
                if {"W", "U", "R"}.issubset(colors):
                    p_wur_t3 += 1
                if r >= 1 and w >= 1 and n_in_play >= 3:
                    p_phlage_t3 += 1
                total_natural_tap_lands_T3 += natural_tap_in_early_game
            if turn == 4:
                n_t4 += 1
                if w >= 2 and n_in_play >= 4:
                    p_wos_t4 += 1
            if turn == 5:
                n_t5 += 1
                if r >= 2 and w >= 2 and n_in_play >= 4:
                    p_phlage_esc_t5 += 1
                if u >= 2 and n_in_play >= 5:
                    p_qr_t5 += 1
            if turn == 6:
                n_t6 += 1
                total_damage_t6 += damage
                total_surveils += surveils_this_game

    components = [(p_wur_t3 / max(n_t3, 1)) * 100]
    if has_phlage:
        components.append((p_phlage_t3 / max(n_t3, 1)) * 100)
        components.append((p_phlage_esc_t5 / max(n_t5, 1)) * 100)
    if has_qr:
        components.append((p_qr_t5 / max(n_t5, 1)) * 100)
    if has_wos:
        components.append((p_wos_t4 / max(n_t4, 1)) * 100)

    # Life safety: probabilistic damage. Modern decks taking <6 dmg are great.
    avg_damage = total_damage_t6 / max(n_t6, 1)
    life_safety = max(0.0, min(100.0, 100 - max(0, avg_damage - 4) * 6))
    components.append(life_safety)

    # Surveil-quality bonus: average surveils-per-game scaled to 0-100.
    # Each surveil = card selection ≈ +0.3 cards drawn equiv. ~3 surveils/game = great.
    avg_surveils = total_surveils / max(n_t6, 1)
    surveil_score = min(avg_surveils * 35, 100)  # 0 surveils = 0, ~3 = 100
    components.append(surveil_score)

    # Tempo penalty: natural-drawn tap-lands T1-T3 = lost mana that turn.
    # Already implicitly affects WUR/Phlage T3 metrics, but small explicit
    # weight smooths the landscape so the optimizer can see tap-land drag.
    avg_early_tap = total_natural_tap_lands_T3 / max(n_t3, 1)
    tempo_score = max(0.0, 100 - avg_early_tap * 30)  # 0 early-taps = 100, 1 = 70

    color_score = sum(components) / len(components)
    # Blend tempo score in at 15% weight relative to the average above
    color_score = 0.85 * color_score + 0.15 * tempo_score

    # Fetch flexibility bonus per user feedback: a fetch that can reach
    # diverse outcomes (basic AND shock AND surveil dual) is more valuable
    # than one with monotone targets. This rewards 2-1-1 + off-color fetch
    # manabases over flat 4-4 shock-heavy bases at the deck-design level.
    fetch_flex = _fetch_flexibility_bonus(deck_def)
    color_score += fetch_flex

    if return_parts:
        return color_score, {
            "p_wur_t3": (p_wur_t3 / max(n_t3, 1)) * 100,
            "p_phlage_t3": (p_phlage_t3 / max(n_t3, 1)) * 100 if has_phlage else None,
            "p_phlage_esc_t5": (p_phlage_esc_t5 / max(n_t5, 1)) * 100 if has_phlage else None,
            "p_qr_t5": (p_qr_t5 / max(n_t5, 1)) * 100 if has_qr else None,
            "p_wos_t4": (p_wos_t4 / max(n_t4, 1)) * 100 if has_wos else None,
            "avg_damage_t6": avg_damage,
            "life_safety": life_safety,
            "avg_surveils": avg_surveils,
            "surveil_score": surveil_score,
            "avg_early_tap_lands": avg_early_tap,
            "tempo_score": tempo_score,
            "fetch_flex": fetch_flex,
        }
    return color_score


def _fetch_flexibility_bonus(deck_def):
    """Score the average diversity of fetch targets across the deck's
    fetches. Each fetch's 'option breadth' = distinct (kind, color-set)
    of in-deck targets. Averaged across fetches in the deck.

    Per user: 'a fetch can maybe get a basic, a shock of two colors, a
    surveil dual — that's what matters.'
    """
    from simulate import CARDS, FETCH_TARGETS_FOR_PICK
    total_diversity = 0.0
    n_fetches = 0
    for fetch_name, targets in FETCH_TARGETS_FOR_PICK.items():
        n_in_deck = deck_def.get(fetch_name, 0)
        if n_in_deck == 0:
            continue
        # Distinct (kind, frozenset(produces)) outcomes in deck
        distinct = set()
        for t in targets:
            if deck_def.get(t, 0) > 0:
                if t in SHOCK_LANDS:
                    kind = "shock"
                elif t in SURVEIL_DUAL_LANDS:
                    kind = "surveil"
                elif CARDS[t]["basic"]:
                    kind = "basic"
                else:
                    kind = "other"
                distinct.add((kind, frozenset(CARDS[t]["produces"])))
        # Each fetch contributes its diversity (number of distinct outcomes)
        # to the bonus, weighted by count.
        total_diversity += n_in_deck * len(distinct)
        n_fetches += n_in_deck
    if n_fetches == 0:
        return 0.0
    avg_diversity = total_diversity / n_fetches
    # 4 distinct outcomes per fetch = +4 points; 2 distinct = +2.
    # Calibrated so the diversity bonus is meaningful but doesn't dominate.
    return avg_diversity * 1.0


def composite_score(deck_def, sim_result, weights=(0.40, 0.20, 0.10, 0.10, 0.20),
                    color_n=4000):
    """40% power + 20% castability + 10% mana efficiency + 10% stuff-to-do +
    20% color reliability.

    Color-reliability rewards manabases that reliably produce the required
    colors on time. Without it the optimizer can't distinguish between a
    redundant 4-4-1 shock split and a tighter 2-2-1 + off-color-fetch
    split — both score similar on castability because the simulator's
    pick_land already prioritizes color, masking the manabase difference."""
    power = effective_power(deck_def, sim_result)
    cast = castability_score(sim_result, deck_def)
    eff = mana_efficiency_score(sim_result)
    flood = stuff_to_do_score(sim_result)
    color = color_reliability_score(deck_def, n=color_n, sim_result=sim_result)
    power_normalized = power * 10
    score = (weights[0] * power_normalized + weights[1] * cast +
             weights[2] * eff + weights[3] * flood + weights[4] * color)
    return score, {
        "power": power_normalized,
        "castability": cast,
        "mana_efficiency": eff,
        "stuff_to_do": flood,
        "color_reliability": color,
        "depleted": sim_result["misc"].get("avg_basics_tutored_T6", 0) >= DEPLETION_THRESHOLD,
        "avg_basics_tutored_T6": sim_result["misc"].get("avg_basics_tutored_T6", 0),
        "avg_non_land_T7": sim_result["misc"].get("avg_non_land_in_hand_T7", 0),
        "pct_flood_T8": sim_result["misc"].get("pct_non_land_zero_T8", 0),
    }

if __name__ == "__main__":
    import random
    from simulate import simulate, build_deck, PHELIA, PURE_ENGINE, ROKU, SOURCE_CORKYBOYY
    decks = {"Source": SOURCE_CORKYBOYY, "Phelia": PHELIA, "Pure": PURE_ENGINE, "Roku": ROKU}
    for name, dd in decks.items():
        random.seed(42)
        res = simulate(build_deck(dd), trials=5000)
        score, parts = composite_score(dd, res)
        print(f"\n=== {name} ===")
        print(f"  Composite: {score:.2f}")
        for k, v in parts.items():
            if isinstance(v, bool):
                print(f"  {k}: {v}")
            else:
                print(f"  {k}: {v:.2f}")
