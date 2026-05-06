"""Genetic algorithm optimizer for MTG decklists.

Per user feedback: "Consider a genetic algorithm approach as well."

Operates on a fixed cardpool (catalog of all cards considered legal in
this deck-design exercise). Each genome is a decklist (60 cards).
Generations: select-tournament + crossover + mutate.

Fitness = composite score under the current model.

Mutations:
  - Swap card type (creature ↔ creature, land ↔ land — Modern legality)
  - Bump count up/down (1 ↔ 2 ↔ 3 ↔ 4)
  - Swap basic ↔ utility (mountain ↔ field of ruin)

Crossover: take 30 cards from parent A + 30 from parent B, then heal to
60 by adjusting basics.
"""
import random
import sys
sys.path.insert(0, "/tmp/mtg-quantum-riddler-explorer/sim")

from optimize import evaluate
from simulate import build_deck, CARDS

# Cardpool — the design space the GA explores. Spell pool + land pool.
SPELL_POOL = [
    "White Orchid Phantom", "Quantum Riddler", "Phelia",
    "Phlage", "Solitude", "Snapcaster Mage",
    "Erode", "Path to Exile", "Cleansing Wildfire", "Price of Freedom",
    "Galvanic Discharge", "Wrath of the Skies", "Wrath of God",
    "The Legend of Roku",
]
LAND_POOL = [
    "Arid Mesa", "Scalding Tarn", "Marsh Flats", "Misty Rainforest", "Polluted Delta",
    "Sacred Foundry", "Hallowed Fountain", "Steam Vents",
    "Meticulous Archive", "Elegant Parlor", "Thundering Falls",
    "Sunken Citadel", "Arena of Glory",
    "Demolition Field", "Field of Ruin",
    "Plains", "Mountain", "Island",
]
BASICS = {"Plains", "Mountain", "Island"}


def random_deck(target_lands=25, seed=None):
    """Generate a random legal 60-card deck."""
    if seed is not None:
        random.seed(seed)
    deck = {}
    # Spells: 60 - target_lands distributed across SPELL_POOL with 4-of cap
    target_spells = 60 - target_lands
    spells_remaining = target_spells
    # Always include the core threats
    for c in ["White Orchid Phantom", "Quantum Riddler"]:
        n = random.randint(2, 4)
        deck[c] = n
        spells_remaining -= n
    while spells_remaining > 0:
        c = random.choice(SPELL_POOL)
        if deck.get(c, 0) >= 4 and c not in BASICS:
            continue
        bump = min(random.randint(1, 4), spells_remaining)
        deck[c] = deck.get(c, 0) + bump
        if deck[c] > 4 and c not in BASICS:
            deck[c] = 4
        spells_remaining = target_spells - sum(v for k, v in deck.items() if k in SPELL_POOL)
    # Lands: target_lands distributed
    lands_remaining = target_lands
    # Always include some fetches
    for c in ["Arid Mesa", "Scalding Tarn"]:
        n = random.randint(2, 4)
        deck[c] = n
        lands_remaining -= n
    while lands_remaining > 0:
        c = random.choice(LAND_POOL)
        if deck.get(c, 0) >= 4 and c not in BASICS:
            continue
        bump = min(random.randint(1, 4), lands_remaining)
        deck[c] = deck.get(c, 0) + bump
        if deck[c] > 4 and c not in BASICS:
            deck[c] = 4
        lands_remaining = target_lands - sum(v for k, v in deck.items() if k in LAND_POOL)
    # Sanity-fix to exactly 60
    diff = 60 - sum(deck.values())
    if diff > 0:
        deck["Plains"] = deck.get("Plains", 0) + diff
    elif diff < 0:
        # remove a basic
        for b in ("Plains", "Mountain", "Island"):
            while diff < 0 and deck.get(b, 0) > 0:
                deck[b] -= 1
                if deck[b] == 0:
                    del deck[b]
                diff += 1
    return deck


def mutate(deck, mutation_rate=0.10):
    """Mutate a deck in-place: swap card types or bump counts."""
    new = dict(deck)
    n_mutations = max(1, int(len(new) * mutation_rate))
    for _ in range(n_mutations):
        action = random.choice(["bump", "swap_in_kind"])
        if action == "bump":
            cards = list(new.keys())
            if not cards:
                continue
            c = random.choice(cards)
            delta = random.choice([-1, 1])
            cap = float("inf") if c in BASICS else 4
            new[c] = max(0, min(cap, new[c] + delta))
            if new[c] == 0:
                del new[c]
        else:
            # Swap one card for another of the same type
            cards = list(new.keys())
            if not cards:
                continue
            c = random.choice(cards)
            is_land = c in LAND_POOL
            pool = LAND_POOL if is_land else SPELL_POOL
            other = random.choice(pool)
            if other == c:
                continue
            cap = float("inf") if other in BASICS else 4
            if new.get(other, 0) >= cap:
                continue
            new[c] -= 1
            if new[c] == 0:
                del new[c]
            new[other] = new.get(other, 0) + 1
    # Fix to 60 if drift
    diff = 60 - sum(new.values())
    if diff > 0:
        new["Plains"] = new.get("Plains", 0) + diff
    elif diff < 0:
        for b in ("Plains", "Mountain", "Island"):
            while diff < 0 and new.get(b, 0) > 0:
                new[b] -= 1
                if new[b] == 0:
                    del new[b]
                diff += 1
    return new


def crossover(a, b):
    """Take half of cards from A, half from B, heal to 60."""
    # Combine card sets, average counts
    all_cards = set(a.keys()) | set(b.keys())
    child = {}
    for c in all_cards:
        ca = a.get(c, 0)
        cb = b.get(c, 0)
        # Random pick: from A, from B, or average
        choice = random.random()
        if choice < 0.45:
            n = ca
        elif choice < 0.90:
            n = cb
        else:
            n = (ca + cb) // 2
        if n > 0:
            cap = float("inf") if c in BASICS else 4
            child[c] = min(cap, n)
    diff = 60 - sum(child.values())
    if diff > 0:
        child["Plains"] = child.get("Plains", 0) + diff
    elif diff < 0:
        for bb in ("Plains", "Mountain", "Island"):
            while diff < 0 and child.get(bb, 0) > 0:
                child[bb] -= 1
                if child[bb] == 0:
                    del child[bb]
                diff += 1
    return child


def fitness(deck, trials=1500, n_seeds=2):
    """Composite score; cached if possible."""
    try:
        score, _, _ = evaluate(deck, trials=trials, n_seeds=n_seeds)
        return score
    except Exception:
        return 0.0


def tournament_select(pop_with_fitness, k=3):
    """Pick k random individuals; return the best."""
    sample = random.sample(pop_with_fitness, min(k, len(pop_with_fitness)))
    sample.sort(key=lambda x: x[1], reverse=True)
    return sample[0][0]


def run_ga(seed_decks, generations=8, pop_size=12, elite=2,
           mutation_rate=0.12, log_each_gen=True):
    """Run the genetic algorithm.

    seed_decks: list of starting decklists to seed the population.
    generations: number of evolution cycles.
    pop_size: population size.
    elite: top individuals carried forward unchanged.
    """
    # Initial population: seeds + random fills
    population = [dict(d) for d in seed_decks]
    while len(population) < pop_size:
        population.append(random_deck())

    print(f"GA: {pop_size} individuals × {generations} generations")
    print("=" * 70)
    best_ever = None
    for gen in range(generations):
        scored = [(d, fitness(d)) for d in population]
        scored.sort(key=lambda x: x[1], reverse=True)
        if best_ever is None or scored[0][1] > best_ever[1]:
            best_ever = scored[0]
        if log_each_gen:
            avg = sum(s for _, s in scored) / len(scored)
            print(f"Gen {gen+1:>2}: best={scored[0][1]:.2f}  avg={avg:.2f}  worst={scored[-1][1]:.2f}")
        # Next gen: elites + tournament-selected breeders
        new_pop = [scored[i][0] for i in range(elite)]
        while len(new_pop) < pop_size:
            parent_a = tournament_select(scored)
            parent_b = tournament_select(scored)
            child = crossover(parent_a, parent_b)
            child = mutate(child, mutation_rate=mutation_rate)
            if sum(child.values()) == 60:
                new_pop.append(child)
        population = new_pop

    print("\n" + "=" * 70)
    print(f"BEST OVER {generations} GENS: score = {best_ever[1]:.2f}")
    print("Decklist:")
    for k, v in sorted(best_ever[0].items(), key=lambda x: (-x[1], x[0])):
        print(f"  {v} {k}")
    return best_ever


if __name__ == "__main__":
    # Seed with the candidates we've been comparing
    HYBRID_25_44 = {
        "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2, "Phlage": 2,
        "Solitude": 2, "Snapcaster Mage": 2, "Erode": 4, "Path to Exile": 4,
        "Cleansing Wildfire": 4, "Price of Freedom": 4, "Galvanic Discharge": 2,
        "Wrath of the Skies": 1,
        "Arid Mesa": 4, "Scalding Tarn": 4, "Sacred Foundry": 4, "Hallowed Fountain": 4,
        "Steam Vents": 1, "Arena of Glory": 1, "Demolition Field": 1, "Field of Ruin": 2,
        "Plains": 2, "Mountain": 1, "Island": 1,
    }
    USER_PICK = {
        "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2, "Phlage": 2,
        "Solitude": 2, "Snapcaster Mage": 2, "Erode": 4, "Path to Exile": 4,
        "Cleansing Wildfire": 4, "Price of Freedom": 4, "Galvanic Discharge": 2,
        "Wrath of the Skies": 1,
        "Arid Mesa": 4, "Scalding Tarn": 4, "Marsh Flats": 2, "Misty Rainforest": 1,
        "Sacred Foundry": 2, "Hallowed Fountain": 1, "Steam Vents": 1,
        "Meticulous Archive": 1, "Elegant Parlor": 1,
        "Arena of Glory": 1, "Demolition Field": 1, "Field of Ruin": 2,
        "Plains": 2, "Mountain": 1, "Island": 1,
    }
    USER_INTUITION = {
        "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia": 2, "Phlage": 3,
        "Snapcaster Mage": 2, "Erode": 4, "Path to Exile": 3,
        "Cleansing Wildfire": 4, "Price of Freedom": 4, "Galvanic Discharge": 2,
        "Wrath of the Skies": 2,
        "Arid Mesa": 4, "Scalding Tarn": 4, "Arena of Glory": 2,
        "Sunken Citadel": 2,
        "Sacred Foundry": 1, "Hallowed Fountain": 1, "Steam Vents": 1,
        "Meticulous Archive": 1, "Elegant Parlor": 1,
        "Demolition Field": 1, "Field of Ruin": 3,
        "Mountain": 1, "Plains": 2, "Island": 2,
    }
    seeds = [HYBRID_25_44, USER_PICK, USER_INTUITION]
    random.seed(0)
    run_ga(seeds, generations=6, pop_size=10)
