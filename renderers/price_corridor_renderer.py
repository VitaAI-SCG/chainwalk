from utils.price_corridor_engine import CorridorSnapshot

def render_price_corridor(snapshot: CorridorSnapshot):
    # Enforce vocabulary constraints
    weak_verbs = ["could", "maybe", "suggests", "might"]
    for verb in weak_verbs:
        if verb in snapshot.inevitability.lower():
            raise ValueError(f"WEAK LANGUAGE DETECTED in inevitability: {verb}")

    # Ensure inevitability has required verbs
    required = ["impossible", "bias", "cannot", "forces", "eliminates", "structurally illegal", "no viable off-ramp"]
    if not any(req in snapshot.inevitability.lower() for req in required):
        raise ValueError("V6 Corridor requires inevitability verbs in sentence.")

    lines = []
    lines.append("🟥 PRICE CORRIDOR ENGINE")
    lines.append(f"Legality Floor: {snapshot.legality_floor}")
    lines.append(f"Custody Drift: {snapshot.custody_drift}")
    lines.append(f"Entropy Field: {snapshot.entropy_field}")
    lines.append(f"Tension Grade: {snapshot.tension_grade}/10")
    lines.append(f"Inevitability: {snapshot.inevitability}")
    lines.append("")
    lines.append("Corridor Rule:")
    lines.append("The chain is not reacting to price.")
    lines.append("Price is reacting to the chain.")
    return "\n".join(lines)