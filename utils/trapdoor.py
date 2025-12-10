from typing import Dict, Any

def compute_trapdoor(
    custody_streak: int,
    chain_tension_index: float,
) -> Dict[str, Any]:
    """
    Compute Custody Trapdoor score and band using custody streak and CTI.
    Higher values indicate more stored exit-velocity risk.
    """
    cti = max(float(chain_tension_index), 1.0)
    streak = max(int(custody_streak), 0)

    raw = (streak ** 2) / cti

    if raw < 3:
        band = "latent"
        label = "Trapdoor latent — compression is building, but not yet dangerous."
    elif raw < 6:
        band = "primed"
        label = "Trapdoor primed — a custody unwind would amplify any move."
    else:
        band = "loaded"
        label = "Trapdoor loaded — exit velocity is primed; reversals risk violent follow-through."

    return {
        "score": round(raw, 3),
        "band": band,
        "label": label,
    }