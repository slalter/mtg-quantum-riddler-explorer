# Sim / optimizer pipeline

Python-only Monte Carlo simulator + composite scorer + greedy hill-climb optimizer.

## Files

- **`simulate.py`** — turn-by-turn Monte Carlo simulator. Plays the deck against itself for 12 turns, ~15k trials per evaluation. Tracks: castability per card per target turn, basic-tutors forced, yard density, mana fix bank, energy banked, late-game flood.
- **`score.py`** — composite scorer: 45% effective_power_density + 25% castability + 15% mana_efficiency + 15% stuff_to_do. Per-card power scores with diminishing returns and conditional scaling.
- **`optimize.py`** — single-step and 2-step lookahead hill-climb. Modern legality enforced (4-of cap, 25-land cap, basic floor, spell→spell or land→land swaps only).
- **`hand_analysis.py`** — opening-hand pathology distribution (mulligan keeps, color screw, dead cards).
- **`leave_one_out.py`** — per-card marginal value (drop 1 copy, replace with Plains, re-score).
- **`pareto.py`** — Pareto frontier analysis on (power, castability, mana_efficiency, stuff_to_do).
- **`color_access.py`** — P(have W+U+R sources by turn N).
- **`convergence_test.py`** — hill-climb from 5 different starting decks; checks for global optimum.
- **`explore_candidates.py`** — try specific named card swaps.
- **`export_deck.py`** — generate MTGO/Cockatrice import format.
- **`test_variants.py`** — manual variant comparison.

## Quickstart

```bash
# Score the canonical decks
python3 score.py

# Run a 2-step hill-climb on Phelia v19 baseline
python3 optimize.py climb phelia

# Hand-pattern distribution (5000 sample openings)
python3 hand_analysis.py

# Convergence test (~30+ min, 5 starting points)
python3 convergence_test.py
```

## Tuning the model

Per-card power: edit `CARD_POWER` in `score.py`. Each entry has:
- `base`: base power (1-10 scale)
- `dr`: diminishing-returns curve [copy1, copy2, copy3, copy4]
- `engine`: True if engine card (gets sigmoid-scaling once depletion threshold reached)
- `legendary`: True if legendary (harsher DR)
- `needs_white_density` / `needs_blink_targets`: special conditional flags

Synergies: edit the bonus calculations in `effective_power()` in `score.py`.

Composite weights: edit the tuple in `composite_score()` (default 0.45 / 0.25 / 0.15 / 0.15).

## Adding new cards

Add to `CARDS` dict in `simulate.py`:
- `S(cmc, {color: count}, creature=True)` for spells
- `L(produces_set, tapped=False, basic=False)` for lands

Add to `CARD_POWER` dict in `score.py` if you want it to contribute to the score.

Add to `SWAP_CANDIDATES` in `optimize.py` if you want the hill-climb to try swaps with it.

## Caveats

- Sim is solitaire (no opponent)
- Heuristic AI plays "best castable spell each turn"
- Power scores are subjective (1-10 scale, hand-tuned)
- No mulligan modeling
- No matchup awareness

See README at repo root for the full caveats list and how the model evolved.
