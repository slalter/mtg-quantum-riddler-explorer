# Iteration history

This repo grew from a real-time conversation between an MTG-playing human and an AI assistant. Each numbered "Overnight" doc was a checkpoint review.

## Phase 1: Identifying the actual deck (v1–v3)

The user wanted a Quantum Riddler upgrade for "the recent WR Land Destruction deck doing well in Modern with Erode". The AI initially:

1. **Hallucinated** a non-existent deck without searching, got called out.
2. **Searched** and found the wrong list (an older Nahiri+Emrakul Boros LD shell).
3. **Eventually found** Corkyboyy's actual list at MTGGoldfish: 13th place in 2026-05-04 Modern Challenge 64. White Orchid Phantom + Phlage + Solitude + Erode + Cleansing Wildfire shell.

**Lesson**: search public deck data before designing. The "obvious" interpretation might be wrong.

## Phase 2: Building the engine (v4–v8)

Once the user pointed out the **basic-depletion engine** (5 cards × 4 copies = 20 forced basic-tutors), the deck's win condition came into focus. Subsequent variants:

- **Phelia Riddler** (Jeskai blink + LD)
- **Wildfire Engine** (Ephemerate-heavy)
- **Roku Hardcast** (engine intact + Roku for U-fix)
- All variants compared on castability, basic-tutor count, and Phelia/Phlage/Solitude pattern.

## Phase 3: The model gets serious (v9–v18)

User pushed for a real test fixture, optimizer, and metric tuning. The AI:

- Built `simulate.py` with turn-by-turn play
- Built `score.py` with composite (power + castability + mana efficiency + flood)
- Built `optimize.py` with greedy + 2-step hill-climb
- Modern legality enforced (4-of cap, land count cap, basic floor)
- Added synergies: Galvanic→Wrath, Phlage→Arena, Phelia→Solitude, Roku→QR
- Diminishing returns per-card (legendary harsher)
- Sigmoid depletion threshold

## Phase 4: Sim bugs and corrections (v18–v19)

User caught two issues that the AI had to fix:

1. **Phantom-shock bug**: fetches were creating phantom shocks without thinning library. Major bug. +3 score shift after fix.
2. **Land swaps weren't enforced as land→land**: cleanly fixed.
3. **3 basics doesn't actually work** (user's experience): added continuous shortfall penalty, then a hard floor.

The model after these fixes was meaningfully more accurate.

## Phase 5: Convergence (overnight)

The AI ran:
- Multi-seed averaging across 5 starting points (PHELIA_V19, Source, Pure, Minimal, Alt-fetch)
- All starting points hill-climbed to within 62-66 composite range
- Evidence of a true global optimum

Highest-scoring variants:
- **Source-optimized** (Corkyboyy's list + 4 land tweaks): 65.46. No QR.
- **Phlage-free SAFE** (no Phlage, 3 Snap): 63.70. Locked recommendation.
- **Hybrid** (with Phlage): 63.49. Alternative if Phlage matchup utility wanted.

## Doc review numbering

The conversation produced ~20 doc reviews. Some were retracted:

- v3 retracted (Phelia → HF was a spell-for-land swap, illegal)
- Random-restart abandoned due to bugs
- Cockatrice playthrough not possible (GUI client)

## Final deliverables

- The webapp (interactive deck explorer)
- The Python sim/optimizer pipeline
- This README + history
- The decklist (in `MTGO_LIST.md`)
- Sideboard recommendations

## What went well

- Iterative real-time feedback from the human kept the model honest.
- Each new metric was triggered by a specific human observation.
- The hand-pattern data (5000 sample openings) gave a sanity check beyond the composite.
- Multi-seed verification confirmed the recommendation is robust.

## What could improve

- Coding an opponent model would make win-rate the metric instead of "castability".
- Numpy vectorization would push trial counts 10-50×.
- Per-matchup tuning would address the model's matchup-blindness.
- Sideboard search wasn't done (hand-picked).
