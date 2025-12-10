# utils/irreversibility_engine.py

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class IRQResult:
    band: str
    index: float
    details: Dict[str, Any]


def compute_irq(state: Dict[str, Any]) -> IRQResult:
    """
    Computes the irreversibility index (IRQ) by fusing the constraint fields.
    state must include CTI, MTI, ETI, custody_streak, regime, intent_state.
    """
    # Extract fields
    cti = float(state.get("cti", 0.0))
    mti = float(state.get("mti", 0.0))
    eti = float(state.get("eti", 0.0))
    custody_streak = int(state.get("custody_streak", 0))
    regime = str(state.get("regime", ""))
    intent_state = str(state.get("intent_state", ""))

    # Normalize
    cti_norm = cti / 10.0
    custody_norm = min(custody_streak / 10.0, 1.0)

    # Fused IRQ
    irq = 0.35 * cti_norm + 0.35 * mti + 0.20 * eti + 0.10 * custody_norm

    # Assign band
    if irq >= 0.90 and mti >= 0.85 and cti >= 6.5:
        band = "floor"
    elif irq >= 0.78 and regime in {"COMPRESSION", "STARVATION"}:
        band = "irreversible"
    elif irq >= 0.45:
        band = "primed"
    else:
        band = "reversible"

    # Details for debug
    details = {
        "cti_norm": cti_norm,
        "custody_norm": custody_norm,
        "fused_components": {
            "cti": 0.35 * cti_norm,
            "mti": 0.35 * mti,
            "eti": 0.20 * eti,
            "custody": 0.10 * custody_norm,
        },
        "regime": regime,
        "intent_state": intent_state,
    }

    return IRQResult(band=band, index=irq, details=details)