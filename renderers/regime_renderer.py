from typing import Optional, Dict
from utils.regime_tracker import RegimeSnapshot
from core.brief_renderer import assert_conviction

def render_regime_section(regime_snapshot: RegimeSnapshot, horizon_state: Optional[Dict] = None) -> str:
    # Enforce language constraints
    weak_words = ["might", "looks", "appears"]
    if any(word in regime_snapshot.inevitability.lower() for word in weak_words):
        raise ValueError("WEAK LANGUAGE DETECTED in regime inevitability")

    # Ensure inevitability has required verbs
    required = ["cannot", "forces", "eliminates", "locks", "guaranteed", "pulled", "decays"]
    if not any(req in regime_snapshot.inevitability.lower() for req in required):
        raise ValueError("Regime inevitability requires causal verbs")

    lines = []
    lines.append(f"## 🚦 Regime Status — {regime_snapshot.name}")
    lines.append("")
    lines.append(f"Custody: {regime_snapshot.custody}")
    lines.append(f"Entropy Field: {regime_snapshot.entropy}")
    lines.append(f"Tension Grade: {regime_snapshot.tension:.1f}")
    lines.append(f"Corridor: {regime_snapshot.corridor}")
    lines.append("")
    lines.append(f"**Outcome:** {regime_snapshot.inevitability}")
    if horizon_state:
        mode = horizon_state.get("horizon_mode")
        if mode == "coil":
            line = "Regime Horizon (7d): UNRESOLVED COIL — compression is undecided; timing withheld by chain."
        else:
            dom = horizon_state.get("dominant_regime")
            line = f"Regime Horizon (7d): BIASED → {dom} — the chain is pulling future state toward {dom.lower()}."
            # Optional: add numbers
            p = horizon_state.get("p_horizon", [])
            if p:
                pct = [round(x*100) for x in p]
                line += f" ({pct[0]}C / {pct[1]}A / {pct[2]}S / {pct[3]}D)"
        # Enforce conviction
        assert_conviction(line)
        lines.append("")
        lines.append(f"**{line}**")
    return "\n".join(lines)