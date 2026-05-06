"""Export deck dicts as MTGO/Cockatrice-importable text files."""
from optimize import PHELIA_V19

SNAPCASTER_VARIANT = {
    'White Orchid Phantom': 4, 'Phelia, Exuberant Shepherd': 2, 'Phlage, Titan of Fire\'s Fury': 2,
    'Quantum Riddler': 4, 'Solitude': 2, 'Snapcaster Mage': 2,
    'Erode': 4, 'Path to Exile': 3, 'Galvanic Discharge': 2, 'Cleansing Wildfire': 4,
    'Price of Freedom': 4, 'Wrath of the Skies': 2,
    'Sacred Foundry': 2, 'Scalding Tarn': 4, 'Hallowed Fountain': 2, 'Arid Mesa': 4,
    'Steam Vents': 1, 'Arena of Glory': 3, 'Demolition Field': 3, 'Field of Ruin': 2,
    'Plains': 2, 'Mountain': 1, 'Island': 1,
}

# Sideboard (15) — common across variants
SIDEBOARD = {
    'Rest in Peace': 3,
    'Celestial Purge': 2,
    'Mystical Dispute': 2,
    'Negate': 2,
    'Surgical Extraction': 2,
    'Wrath of the Skies': 1,
    'Consign to Memory': 2,
    'High Noon': 1,
}

def export_mtgo(deck_def, sideboard, name):
    """MTGO format: 'N CardName' lines, sideboard separated by 'Sideboard:'"""
    out = [f"// {name}"]
    out.append(f"// Mainboard ({sum(deck_def.values())})")
    # Replace shorthand names with full card names
    name_map = {
        "Phelia": "Phelia, Exuberant Shepherd",
        "Phlage": "Phlage, Titan of Fire's Fury",
    }
    for card, qty in sorted(deck_def.items(), key=lambda x: (-x[1], x[0])):
        full = name_map.get(card, card)
        out.append(f"{qty} {full}")
    out.append("")
    out.append(f"// Sideboard ({sum(sideboard.values())})")
    for card, qty in sorted(sideboard.items(), key=lambda x: (-x[1], x[0])):
        out.append(f"SB: {qty} {card}")
    return "\n".join(out)

if __name__ == "__main__":
    print("=" * 60)
    print("v19 Phelia (legal baseline)")
    print("=" * 60)
    print(export_mtgo(PHELIA_V19, SIDEBOARD, "Phelia v19 (25 lands, 4 basics)"))
    print()
    print("=" * 60)
    print("Snapcaster variant (overnight #7 finding, score 61.26)")
    print("=" * 60)
    print(export_mtgo(SNAPCASTER_VARIANT, SIDEBOARD, "Snapcaster Phelia variant"))
