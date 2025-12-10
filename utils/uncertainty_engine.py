from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
import math

@dataclass
class UQIResult:
    band: str        # open | narrowing | thin | terminal
    index: float     # 0.00 – 1.00
    details: Dict[str, Any]    # supporting metrics

def compute_uqi(state: Dict[str, Any]) -> UQIResult:
    """
    Compute Uncertainty Quotient Index (UQI).

    UQI measures how many possible futures the Bitcoin protocol still permits.
    When UQI collapses, the market no longer decides — it inherits.

    Formula: UQI = 1 - exp(- (w1*C + w2*M + w3*R + w4*S + w5*(1-D)))

    Where:
    - C: custody constraint (normalized custody streak)
    - M: miner stress (MTI index)
    - R: irreversibility (IRQ index)
    - S: resolution force (REI index)
    - D: difficulty slack (normalized ETI, higher = less slack)

    Weights: C 0.25, M 0.25, R 0.20, S 0.20, (1-D) 0.10
    """

    # Extract and normalize inputs
    cti = float(state.get("chain_tension_index", 0.0)) / 10.0  # 0-1
    custody_streak = float(state.get("custody_streak", 0)) / 10.0  # assume max 10
    custody_streak = min(custody_streak, 1.0)
    mti = float(state.get("miner_threshold", {}).get("index", 0.0))  # already 0-1
    eti = float(state.get("difficulty_epoch", {}).get("tension_index", 0.0)) / 5.0  # normalize, assume max 5
    eti = min(eti, 1.0)
    irq = float(state.get("irreversibility", {}).get("index", 0.0))  # 0-1
    rei = float(state.get("resolution", {}).get("index", 0.0))  # 0-1

    # Weights
    w_c = 0.25
    w_m = 0.25
    w_r = 0.20
    w_s = 0.20
    w_d = 0.10

    # Compute UQI
    exponent = (w_c * custody_streak + w_m * mti + w_r * irq + w_s * rei + w_d * (1 - eti))
    uqi_index = 1 - math.exp(-exponent)

    # Determine band
    if uqi_index < 0.33:
        band = "open"
    elif uqi_index < 0.66:
        band = "narrowing"
    elif uqi_index < 0.88:
        band = "thin"
    else:
        band = "terminal"

    # Glyphs
    glyphs = {
        "open": "🟢",
        "narrowing": "🟠",
        "thin": "🟣",
        "terminal": "⚫"
    }

    details = {
        "glyph": glyphs.get(band, "❓"),
        "normalized_inputs": {
            "cti": cti,
            "custody_streak": custody_streak,
            "mti": mti,
            "eti": eti,
            "irq": irq,
            "rei": rei
        },
        "exponent": exponent
    }

    return UQIResult(band=band, index=round(uqi_index, 4), details=details)