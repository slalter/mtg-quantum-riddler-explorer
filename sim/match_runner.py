"""Two-agent MTG match — Cockatrice-style.

Per user: "it can be cockatrice style where the rules aren't explicitly
coded... agents have a chat where they can keep each other honest."

DESIGN:
  - Minimal mechanical state: hands, battlefield, libraries, life,
    graveyards, mana pool, turn, active player, phase.
  - Agents narrate actions in natural language.
  - Opponent reviews each action; can flag rules issues.
  - Parent driver applies the agreed-on state changes.
  - No card-effect database. Agents know the rules.

STATE — kept minimal so agents own the rules:
  - Each card is just its name (string).
  - Permanents on battlefield track tapped/summoning_sick.
  - Mana pool tracks floating mana per turn.
  - History is the chat log (every action narration + counter-comment).

NOT INCLUDED (yet):
  - Stack / instant-speed responses (agents work it out via chat)
  - Counter tracking (agents track via chat; state has counters dict)
  - Hidden info enforcement (each agent only sees their own hand —
    rendered separately)

Loaded by parent agent (Claude Code main loop). The match runner
itself runs in Python; the per-turn agent calls happen via the
Agent tool from the parent's context.
"""
from __future__ import annotations
import json
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Permanent:
    name: str
    tapped: bool = False
    summoning_sick: bool = True
    counters: Dict[str, int] = field(default_factory=dict)

    def to_str(self):
        bits = [self.name]
        if self.tapped:
            bits.append("(tapped)")
        if self.summoning_sick and self.is_creature():
            bits.append("(summoning sick)")
        for k, v in self.counters.items():
            bits.append(f"({v} {k})")
        return " ".join(bits)

    def is_creature(self):
        # Hand-coded for our deck's cards
        creatures = {"White Orchid Phantom", "Quantum Riddler", "Phelia, Exuberant Shepherd",
                     "Phlage, Titan of Fire's Fury", "Solitude", "Snapcaster Mage"}
        return self.name in creatures


@dataclass
class Player:
    name: str
    deck: List[str]
    library: List[str] = field(default_factory=list)
    hand: List[str] = field(default_factory=list)
    battlefield: List[Permanent] = field(default_factory=list)
    graveyard: List[str] = field(default_factory=list)
    exile: List[str] = field(default_factory=list)
    life: int = 20
    mana_pool: Dict[str, int] = field(default_factory=lambda: {"W": 0, "U": 0, "R": 0, "C": 0})
    energy: int = 0
    has_played_land_this_turn: bool = False


@dataclass
class GameState:
    p0: Player
    p1: Player
    active: int = 0   # index 0 or 1
    turn: int = 1
    phase: str = "untap"
    history: List[str] = field(default_factory=list)
    on_play: int = 0
    winner: Optional[int] = None
    win_reason: str = ""

    def player(self, idx) -> Player:
        return self.p0 if idx == 0 else self.p1

    def opponent(self, idx) -> Player:
        return self.p1 if idx == 0 else self.p0

    def log(self, msg):
        self.history.append(msg)


# ============================================================================
# Setup
# ============================================================================
def make_player(name: str, deck_def: Dict[str, int]) -> Player:
    deck = []
    for c, n in deck_def.items():
        deck.extend([c] * n)
    assert len(deck) == 60, f"Deck must be 60 cards, got {len(deck)}"
    return Player(name=name, deck=deck, library=list(deck))


def setup(state: GameState, seed=None):
    if seed is not None:
        random.seed(seed)
    for p in (state.p0, state.p1):
        random.shuffle(p.library)
        p.hand = p.library[:7]
        p.library = p.library[7:]
    state.log(f"=== Game start. {state.p0.name} on the play. ===")
    state.log(f"{state.p0.name}: opening hand drawn ({len(state.p0.hand)} cards)")
    state.log(f"{state.p1.name}: opening hand drawn ({len(state.p1.hand)} cards)")


# ============================================================================
# State render (perspective-aware)
# ============================================================================
def render(state: GameState, perspective: int) -> str:
    me = state.player(perspective)
    them = state.opponent(perspective)
    lines = []
    lines.append(f"=== Turn {state.turn}, {state.phase} phase ===")
    lines.append(f"Active player: {state.player(state.active).name}")
    lines.append(f"")
    lines.append(f"YOU: {me.name}    Life: {me.life}    Library: {len(me.library)} cards    Yard: {len(me.graveyard)} cards    Mana floating: {dict((k,v) for k,v in me.mana_pool.items() if v) or '{}'}")
    lines.append(f"OPPONENT: {them.name}    Life: {them.life}    Library: {len(them.library)} cards    Yard: {len(them.graveyard)} cards")
    lines.append("")
    lines.append("YOUR HAND:")
    for c in me.hand:
        lines.append(f"  - {c}")
    lines.append("")
    lines.append(f"YOUR BATTLEFIELD ({len(me.battlefield)}):")
    for p in me.battlefield:
        lines.append(f"  - {p.to_str()}")
    lines.append("")
    lines.append(f"OPPONENT BATTLEFIELD ({len(them.battlefield)}):")
    for p in them.battlefield:
        lines.append(f"  - {p.to_str()}")
    lines.append("")
    lines.append("YOUR GRAVEYARD:")
    for c in me.graveyard:
        lines.append(f"  - {c}")
    lines.append("")
    lines.append("RECENT ACTIONS (last 12):")
    for h in state.history[-12:]:
        lines.append(f"  {h}")
    return "\n".join(lines)


# ============================================================================
# Mechanical state updates from agent actions.
# Agents return actions in JSON. Parent applies them.
# ============================================================================
def apply_action(state: GameState, player_idx: int, action: Dict):
    """Apply one action to state. Returns description of what happened."""
    p = state.player(player_idx)
    typ = action.get("type")
    if typ == "play_land":
        card = action["card"]
        if card not in p.hand:
            return f"ERROR: {card} not in hand"
        if p.has_played_land_this_turn:
            return f"ERROR: already played a land this turn"
        p.hand.remove(card)
        new_perm = Permanent(name=card)
        # Lands don't get summoning sick
        new_perm.summoning_sick = False
        # Default tapped status from card name (caller can override via "tapped" field)
        if action.get("tapped"):
            new_perm.tapped = True
        p.battlefield.append(new_perm)
        p.has_played_land_this_turn = True
        state.log(f"{p.name} plays {card}{' tapped' if new_perm.tapped else ''}")
        return f"played {card}"
    elif typ == "cast_spell":
        card = action["card"]
        if card not in p.hand:
            return f"ERROR: {card} not in hand"
        p.hand.remove(card)
        # Spell goes to yard by default (resolution handled by agent narration)
        p.graveyard.append(card)
        state.log(f"{p.name} casts {card}" + (f" → {action.get('description', '')}" if action.get("description") else ""))
        return f"cast {card}"
    elif typ == "cast_creature":
        card = action["card"]
        if card not in p.hand:
            return f"ERROR: {card} not in hand"
        p.hand.remove(card)
        new_perm = Permanent(name=card)
        new_perm.summoning_sick = True
        p.battlefield.append(new_perm)
        state.log(f"{p.name} casts {card}, enters battlefield")
        return f"cast {card}"
    elif typ == "tap_for_mana":
        # Mark a permanent tapped, add mana
        target = action["target"]
        for perm in p.battlefield:
            if perm.name == target and not perm.tapped:
                perm.tapped = True
                color = action.get("color", "C")
                amount = action.get("amount", 1)
                p.mana_pool[color] = p.mana_pool.get(color, 0) + amount
                state.log(f"{p.name} taps {target} for {amount}{color}")
                return f"tapped {target}"
        return f"ERROR: {target} not found untapped"
    elif typ == "deal_damage":
        target = action.get("target", "opponent")
        amount = int(action["amount"])
        if target == "opponent":
            them = state.opponent(player_idx)
            them.life -= amount
            state.log(f"{p.name} deals {amount} damage to {them.name} ({them.life} life)")
            if them.life <= 0:
                state.winner = player_idx
                state.win_reason = f"opponent at {them.life} life"
            return f"dealt {amount} damage"
    elif typ == "gain_life":
        amount = int(action["amount"])
        p.life += amount
        state.log(f"{p.name} gains {amount} life ({p.life})")
        return f"gained {amount} life"
    elif typ == "draw":
        n = action.get("amount", 1)
        for _ in range(n):
            if not p.library:
                state.winner = state.opponent(player_idx) == state.p0 and 0 or 1
                state.win_reason = f"{p.name} milled"
                return "milled"
            card = p.library.pop(0)
            p.hand.append(card)
        state.log(f"{p.name} draws {n}")
        return f"drew {n}"
    elif typ == "discard":
        card = action["card"]
        if card in p.hand:
            p.hand.remove(card)
            p.graveyard.append(card)
            state.log(f"{p.name} discards {card}")
            return f"discarded {card}"
        return f"ERROR: {card} not in hand"
    elif typ == "destroy":
        # Destroy a permanent (agent specifies whose)
        owner = action.get("owner", "opponent")
        target = action["target"]
        target_player = p if owner == "self" else state.opponent(player_idx)
        for i, perm in enumerate(target_player.battlefield):
            if perm.name == target:
                target_player.battlefield.pop(i)
                target_player.graveyard.append(perm.name)
                state.log(f"{p.name} destroys {target_player.name}'s {target}")
                return f"destroyed {target}"
        return f"ERROR: {target} not found on {target_player.name}'s battlefield"
    elif typ == "exile":
        # Exile a permanent
        owner = action.get("owner", "opponent")
        target = action["target"]
        target_player = p if owner == "self" else state.opponent(player_idx)
        for i, perm in enumerate(target_player.battlefield):
            if perm.name == target:
                target_player.battlefield.pop(i)
                target_player.exile.append(perm.name)
                state.log(f"{p.name} exiles {target_player.name}'s {target}")
                return f"exiled {target}"
        return f"ERROR: {target} not found"
    elif typ == "search_basic":
        # Force opponent to search basic from library (engine effect)
        # Or self
        owner = action.get("owner", "opponent")
        target_player = p if owner == "self" else state.opponent(player_idx)
        # Pick a basic from library; remove and put on battlefield (tapped)
        for i, c in enumerate(target_player.library):
            if c in ("Plains", "Mountain", "Island", "Swamp", "Forest"):
                target_player.library.pop(i)
                random.shuffle(target_player.library)
                # Convention: searched basic goes to battlefield tapped
                new_perm = Permanent(name=c, tapped=True, summoning_sick=False)
                target_player.battlefield.append(new_perm)
                state.log(f"{target_player.name} searches library for basic, puts {c} into play tapped")
                return f"{target_player.name} found {c}"
        state.log(f"{target_player.name} has no basic to search")
        return f"no basic"
    elif typ == "attack":
        # Tap attackers
        attackers = action.get("attackers", [])
        for a in attackers:
            for perm in p.battlefield:
                if perm.name == a and not perm.tapped:
                    perm.tapped = True
                    break
        state.log(f"{p.name} attacks with: {', '.join(attackers)}")
        return f"attacks with {attackers}"
    elif typ == "pass" or typ == "pass_priority":
        return "pass"
    elif typ == "concede":
        state.winner = 1 - player_idx
        state.win_reason = f"{p.name} conceded"
        state.log(f"{p.name} concedes")
        return "concede"
    elif typ == "narrate":
        # Free-form action description; just log it
        state.log(f"{p.name}: {action.get('text', '')}")
        return "narrated"
    else:
        state.log(f"{p.name} unknown action: {action}")
        return f"unknown action {typ}"


# ============================================================================
# Phase orchestration helpers
# ============================================================================
def begin_turn(state: GameState):
    """Untap, upkeep, draw phase for active player."""
    p = state.player(state.active)
    # Untap step
    for perm in p.battlefield:
        perm.tapped = False
        if perm.is_creature():
            perm.summoning_sick = False
    p.has_played_land_this_turn = False
    p.mana_pool = {"W": 0, "U": 0, "R": 0, "C": 0}
    state.phase = "draw"
    # Draw (skip on first turn for player on the play)
    if not (state.turn == 1 and state.active == state.on_play):
        if p.library:
            c = p.library.pop(0)
            p.hand.append(c)
            state.log(f"{p.name} draws for turn (now {len(p.hand)} cards)")
        else:
            state.winner = 1 - state.active
            state.win_reason = f"{p.name} milled"


# ============================================================================
# Save/load match transcripts for review
# ============================================================================
def save_transcript(state: GameState, path: str):
    out = {
        "turn": state.turn,
        "active": state.active,
        "winner": state.winner,
        "win_reason": state.win_reason,
        "p0": {"name": state.p0.name, "life": state.p0.life,
               "battlefield": [p.to_str() for p in state.p0.battlefield],
               "yard": state.p0.graveyard},
        "p1": {"name": state.p1.name, "life": state.p1.life,
               "battlefield": [p.to_str() for p in state.p1.battlefield],
               "yard": state.p1.graveyard},
        "history": state.history,
    }
    with open(path, "w") as f:
        json.dump(out, f, indent=2)


# Decklists for the test
USER_DECK = {
    "White Orchid Phantom": 4, "Quantum Riddler": 4, "Phelia, Exuberant Shepherd": 2,
    "Phlage, Titan of Fire's Fury": 2, "Solitude": 2, "Snapcaster Mage": 2,
    "Erode": 4, "Path to Exile": 4, "Cleansing Wildfire": 4, "Price of Freedom": 4,
    "Galvanic Discharge": 2, "Wrath of the Skies": 1,
    "Arid Mesa": 4, "Scalding Tarn": 4, "Marsh Flats": 2, "Misty Rainforest": 1,
    "Sacred Foundry": 2, "Hallowed Fountain": 1, "Steam Vents": 1,
    "Meticulous Archive": 1, "Elegant Parlor": 1,
    "Arena of Glory": 1, "Demolition Field": 1, "Field of Ruin": 2,
    "Plains": 2, "Mountain": 1, "Island": 1,
}

# Opponent: Boros Energy (rough representation; adjust as needed)
BOROS_ENERGY = {
    "Ocelot Pride": 4, "Goblin Bushwhacker": 2,
    "Phlage, Titan of Fire's Fury": 4,
    "Ajani, Nacatl Pantherl": 0,  # placeholder
    "Static Prison": 4,
    "Galvanic Discharge": 4, "Lightning Helix": 4,
    "Guide of Souls": 4,
    "Amped Raptor": 4,
    "Boros Charm": 2,
    "Inti, Seneschal of the Sun": 4,
    "Stoneforge Mystic": 0,
    "Steam Vents": 1, "Sacred Foundry": 4, "Inspiring Vantage": 4,
    "Plains": 2, "Mountain": 2,
    "Arid Mesa": 4, "Scalding Tarn": 0,
    "Sokenzan, Crucible of Defiance": 1,
}


if __name__ == "__main__":
    # Verify counts
    print(f"USER_DECK: {sum(USER_DECK.values())} cards")
    # Run a setup test
    state = GameState(
        p0=make_player("USER 2-1-1", USER_DECK),
        p1=make_player("USER 2-1-1 (mirror)", USER_DECK),
    )
    setup(state, seed=42)
    print(render(state, 0))
