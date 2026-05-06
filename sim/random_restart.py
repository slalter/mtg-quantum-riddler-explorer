"""Random-restart optimizer: generate N random legal starting decks,
hill-climb each, return the best. Evidence of true global optimum."""
import random
from optimize import (evaluate, hill_climb_2step, land_count, is_legal,
                       MAX_LAND_COUNT, BASIC_LANDS)
from simulate import CARDS

# Eligible spells/lands (not basics) the random gen can use
SPELLS = [c for c, info in CARDS.items() if not info["land"]]
LANDS = [c for c, info in CARDS.items() if info["land"] and c not in BASIC_LANDS]

def random_legal_deck(seed=None):
    """Generate a random legal-ish 60-card deck.
    Strategy: pick a fixed set of 'core' cards, randomly fill rest."""
    if seed is not None:
        random.seed(seed)
    # Core: must include QR (the deck's purpose)
    deck = {"Quantum Riddler": 4}
    # Add some engine random count
    for card in ["Erode", "Path to Exile", "Cleansing Wildfire", "Price of Freedom",
                 "White Orchid Phantom", "Galvanic Discharge"]:
        deck[card] = random.choice([2, 3, 4])
    # Add some threats
    for card in ["Phlage", "Phelia", "Solitude"]:
        deck[card] = random.choice([0, 1, 2, 3])
    # Add maybe Wrath / Snapcaster
    if random.random() < 0.5:
        deck["Wrath of the Skies"] = random.choice([1, 2])
    if random.random() < 0.4:
        deck["Snapcaster Mage"] = random.choice([1, 2])
    if random.random() < 0.3:
        deck["Ephemerate"] = random.choice([1, 2, 3])
    if random.random() < 0.2:
        deck["The Legend of Roku"] = 1
    if random.random() < 0.2:
        deck["Wrath of God"] = 1
    # Fill lands: 23-25 lands
    target_lands = random.choice([24, 25])
    deck["Sacred Foundry"] = random.choice([2, 3, 4])
    deck["Hallowed Fountain"] = random.choice([2, 3, 4])
    deck["Steam Vents"] = random.choice([0, 1, 2])
    fetch = random.choice([
        ["Scalding Tarn", "Arid Mesa"],
        ["Scalding Tarn", "Arid Mesa", "Flooded Strand"],
        ["Scalding Tarn", "Misty Rainforest", "Arid Mesa"],
    ])
    for f in fetch:
        deck[f] = random.choice([2, 3, 4])
    deck["Field of Ruin"] = random.choice([1, 2, 3])
    deck["Demolition Field"] = random.choice([0, 1, 2])
    deck["Arena of Glory"] = random.choice([0, 1, 2, 3])
    deck["Plains"] = random.choice([1, 2])
    deck["Mountain"] = 1
    deck["Island"] = random.choice([1, 2])
    # Trim to 60
    # First trim lands to 25
    def land_count_local(d):
        return sum(q for c, q in d.items() if c in CARDS and CARDS[c]["land"])
    while land_count_local(deck) > 25:
        # Remove a non-basic land
        cands = [c for c, q in deck.items()
                 if q > 0 and c in CARDS and CARDS[c]["land"]
                 and c not in ("Plains", "Mountain", "Island")]
        if not cands: break
        c = random.choice(cands)
        deck[c] -= 1
        if deck[c] == 0: del deck[c]
    # Trim total to 60
    while sum(deck.values()) > 60:
        candidates = [c for c, q in deck.items() if q > 1 and c != "Quantum Riddler"]
        if not candidates: break
        c = random.choice(candidates)
        deck[c] -= 1
        if deck[c] == 0:
            del deck[c]
    while sum(deck.values()) < 60:
        # Add SPELLS only — don't grow lands further
        if deck.get("Path to Exile", 0) < 4:
            deck["Path to Exile"] = deck.get("Path to Exile", 0) + 1
        elif deck.get("Erode", 0) < 4:
            deck["Erode"] = deck.get("Erode", 0) + 1
        elif deck.get("Cleansing Wildfire", 0) < 4:
            deck["Cleansing Wildfire"] = deck.get("Cleansing Wildfire", 0) + 1
        elif deck.get("Price of Freedom", 0) < 4:
            deck["Price of Freedom"] = deck.get("Price of Freedom", 0) + 1
        elif deck.get("White Orchid Phantom", 0) < 4:
            deck["White Orchid Phantom"] = deck.get("White Orchid Phantom", 0) + 1
        elif deck.get("Galvanic Discharge", 0) < 4:
            deck["Galvanic Discharge"] = deck.get("Galvanic Discharge", 0) + 1
        else:
            deck["Phelia"] = min(2, deck.get("Phelia", 0) + 1)  # legendary cap soft
            if deck["Phelia"] > 4:
                break  # avoid infinite loop
    # Final basic cleanup: ensure at least 4 basics, but no more than necessary
    basics = sum(deck.get(b, 0) for b in ("Plains", "Mountain", "Island"))
    if basics < 4:
        deck["Plains"] = deck.get("Plains", 0) + (4 - basics)
        # Compensate by removing a non-basic land
        for c in ("Demolition Field", "Field of Ruin", "Arena of Glory"):
            while sum(deck.values()) > 60 and deck.get(c, 0) > 0:
                deck[c] -= 1
                if deck[c] == 0:
                    del deck[c]
    return deck

def random_restart(N=10, max_iters=2):
    """Run N random restarts, hill-climb each, return best."""
    best = (0, None, None)
    for i in range(N):
        seed = 42 + i * 17
        deck = random_legal_deck(seed=seed)
        if not is_legal(deck) or sum(deck.values()) != 60:
            print(f"Seed {seed}: skipping (illegal or wrong count {sum(deck.values())})")
            continue
        try:
            score, _, _ = evaluate(deck, n_seeds=1, trials=600)
        except ValueError:
            print(f"Seed {seed}: skipping (build error)")
            continue
        print(f"Seed {seed}: random start score = {score:.2f}, lands={land_count(deck)}, total={sum(deck.values())}")
        # Hill-climb from this start
        try:
            final, final_score = hill_climb_2step(f"Random seed {seed}", deck, max_iters=max_iters, min_delta=0.4, n_seeds=1, trials=500)
        except Exception as e:
            print(f"Seed {seed}: hill-climb error: {e}")
            continue
        if final_score > best[0]:
            best = (final_score, final, seed)
    return best

if __name__ == "__main__":
    print("Random-restart optimizer: 6 random starts × 2-step hill-climb")
    print("=" * 60)
    score, deck, seed = random_restart(N=6, max_iters=2)
    print(f"\nBest seed: {seed}, final score: {score:.2f}")
    print("Final list:")
    for k, v in sorted(deck.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {v} {k}")
