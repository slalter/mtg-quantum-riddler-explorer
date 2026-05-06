# MTG Modern Deck Optimizer — WR Land Destruction → Quantum Riddler

A Monte Carlo deck simulator + composite scorer + hill-climb optimizer for a Magic: The Gathering Modern deck-design exercise: upgrading the recent Boros (WR) Land Destruction shell with **Quantum Riddler** as the finisher.

This repo grew out of a single conversation between a human MTG player and an AI that ran iteratively over many hours. The result is the deck explorer (interactive web app) plus the Python sim/optimizer pipeline plus the documented decision history.

## TL;DR — what's the recommendation?

**Phlage-free SAFE build** — the locked overnight recommendation. Composite score 63.70 ± 0.25 (multi-seed verified).

```
// Mainboard (60)
4 White Orchid Phantom
4 Quantum Riddler
2 Phelia, Exuberant Shepherd
2 Solitude
3 Snapcaster Mage
4 Erode
4 Path to Exile
4 Cleansing Wildfire
4 Price of Freedom
2 Galvanic Discharge
2 Wrath of the Skies
4 Arid Mesa
4 Scalding Tarn
4 Sacred Foundry
4 Hallowed Fountain
1 Steam Vents
1 Arena of Glory
1 Demolition Field
1 Field of Ruin
1 Misty Rainforest
2 Plains
1 Mountain
1 Island

// Sideboard (15)
3 Rest in Peace
2 Celestial Purge
2 Mystical Dispute
2 Negate
2 Surgical Extraction
2 Consign to Memory
1 High Noon
1 Wrath of the Skies
```

Modern legal as of 2026-05-06.

## What's in here

```
.
├── README.md                  (this file)
├── index.html                 (web app entry)
├── css/style.css              (web app styling)
├── js/
│   ├── cards.js               (oracle text database for ~40 cards)
│   ├── decks.js               (variant configurations: Source, Hybrid, PHELIA-FREE, etc.)
│   ├── stats.js               (Monte Carlo simulation results)
│   ├── app.js                 (web app logic: tabs, synergy graph, stats panel)
│   ├── cytoscape.min.js       (Cytoscape.js — graph rendering)
│   ├── cytoscape-dagre.js     (dagre layout bridge)
│   └── dagre.min.js           (dagre — directed graph layout)
├── sim/
│   ├── simulate.py            (turn-by-turn Monte Carlo simulator)
│   ├── score.py               (composite scorer: power + castability + efficiency + flood)
│   ├── optimize.py            (greedy + 2-step hill-climb optimizer)
│   ├── hand_analysis.py       (opening-hand pathology analysis)
│   ├── leave_one_out.py       (per-card marginal-value analysis)
│   ├── pareto.py              (Pareto frontier across 4D metric space)
│   ├── color_access.py        (P(have W+U+R sources by turn N))
│   ├── convergence_test.py    (hill-climb from 5 different starting points)
│   ├── explore_candidates.py  (try specific card-pair swaps)
│   ├── export_deck.py         (MTGO/Cockatrice export format)
│   ├── test_variants.py       (manual variant comparison harness)
│   └── random_restart.py      (random initialization, less stable)
└── docs/                      (overnight doc-review history)
```

## Running it

### Web app (interactive deck explorer)

```bash
cd /path/to/repo
python3 -m http.server 8765
# open http://localhost:8765/
```

Click variant tabs to compare builds. Synergy graph shows combo edges. Right sidebar has Monte Carlo statistics and per-card castability bars.

### Sim / optimizer

```bash
cd sim
python3 score.py            # quick benchmark of all variants
python3 hand_analysis.py    # opening-hand pathology
python3 leave_one_out.py    # marginal-value per card
python3 convergence_test.py # 5 starting-point hill-climb (~30+ min)
python3 optimize.py climb phelia  # hill-climb a specific deck
```

All sim outputs print to stdout. Use `python3 -u` for unbuffered output.

## The composite score

```
score = 0.45 × effective_power_density
      + 0.25 × castability_score
      + 0.15 × mana_efficiency_score
      + 0.15 × stuff_to_do_score
```

Each component is on a 0–100 scale (power is normalized × 10).

### Per-card power scores

In `sim/score.py`, `CARD_POWER` defines:
- Base power (1–10)
- Diminishing-returns curve (per-copy multiplier)
- Whether the card is an "engine" card (gets sigmoid-scaling once depletion threshold reached)
- Whether it has a special precondition (Solitude needs white density, Ephemerate needs blink targets, etc.)

### Synergy bonuses (hand-coded)

- **Galvanic Discharge → Wrath of the Skies**: each Galvanic banked = +0.7 to Wrath base power, capped at +6
- **Phlage → Arena of Glory**: +1.5 if ≥1 Arena (haste enabler)
- **Sunken Citadel**: scales with land-activation density in deck
- **Quantum Riddler → late-game hand-empty**: bonus when avg_non_land_in_hand at T10 is low
- **Phlage → late-game yard density**: bonus when basics-tutored count is high

### Constraints

- Modern 4-of cap (basics unlimited)
- Land count ≤ 25 (source list + 1)
- Spell-for-spell or land-for-land swaps only

## Key sim fixes that mattered

1. **Phantom-shock fetchland bug** — fetches were creating shocks without removing from library. Fixed: each crack actually thins the deck. +3 composite shift.
2. **12-turn simulation** — was 8. Captures Phlage escape and QR hand-empty draws.
3. **Continuous basic-shortfall model** — replaced binary thresholds. Demand = drawn_basics + FoR + 1/3 fetches; shortfall scales penalty smoothly.
4. **FoR + DF unified** — both subject to basic-fetch reliability check.
5. **Solitude evoke conditional** — uses hypergeometric P(other white card in hand) varying by turn.

## Caveats

The sim is **solitaire**. There's no opponent. "Castability" tells you what the deck can DO, not what it WINS.

Real-world testing should compare:
- Win rate vs Boros Energy
- Win rate vs Tron
- Win rate vs Living End
- Win rate vs Murktide / mirror

Without that, the optimizer is biased toward what looks fast on paper.

## History

The deck design started from Corkyboyy's actual MTGO list (2026-05-04, 13th place Modern Challenge 64). This repo iterated through ~20 model improvements based on real-time feedback from a human player. Each iteration tightened metrics, added synergies, fixed sim bugs, and re-ran the hill-climb. The convergence test from 5 different starting points all clustered to 62-65 composite, evidence of a true global optimum within the model.

## Limitations / future work

- Add an opponent model (matchup-aware win rate)
- Vectorize the sim with numpy (10-50× speedup)
- Sideboard slot search
- 3-step swap optimizer (currently 2-step)
- Simulate London mulligan policy

## License

MIT. Use at will.

## Acknowledgments

Card text comes from Wizards of the Coast / Magic: The Gathering oracle. Not affiliated with WotC.

Human player: thanks for the back-and-forth. AI: did the analysis but the design intuition was the human's. It's a partnership.
