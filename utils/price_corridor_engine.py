from dataclasses import dataclass

@dataclass
class CorridorSnapshot:
    legality_floor: str        # "structurally illegal", "fragile", "permitted"
    custody_drift: str         # "vaultward", "marketward"
    entropy_field: str         # "compressing", "releasing", "neutral"
    tension_grade: float       # 0-10 scale
    inevitability: str         # one sentence

def compute_corridor(memory_state, custody_state, entropy_state):
    drift = custody_state.get("direction", "marketward")   # vault, market
    ent = entropy_state.get("gradient", "neutral")      # compressing, flat, rising
    cti = memory_state.get("cti_current", 5.0)

    if drift == "vault" and ent == "compressing" and cti >= 6:
        floor = "structurally illegal"
        inevit = "Below this corridor is impossible—float has already died."
    elif drift == "vault":
        floor = "fragile"
        inevit = "Each block removes exit liquidity; price denial collapses later."
    else:
        floor = "permitted"
        inevit = "Markets can drift, but incentives still bias upward."

    # Strip unicode
    inevit = inevit.encode('ascii', 'ignore').decode('ascii')

    return CorridorSnapshot(
        legality_floor=floor,
        custody_drift=drift,
        entropy_field=ent,
        tension_grade=float(cti),
        inevitability=inevit
    )