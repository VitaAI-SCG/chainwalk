# utils/miner_threshold.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Dict, Any


ThresholdBand = Literal["below", "amber", "strained", "critical"]


@dataclass
class MinerThresholdResult:
    index: float              # 0.0 – 1.0
    band: ThresholdBand       # below / amber / strained / critical
    at_threshold: bool        # True when system is in the "cliff" zone
    regime: str               # echo of regime_label
    cti: float
    stress_score: float
    collapse_window_open: bool
    notes: str                # short human-readable summary


def compute_miner_threshold(
    *,
    cti: float,
    regime_label: str,
    stress_score: float,
    collapse_window_open: bool,
) -> MinerThresholdResult:
    """
    Fuse miner stress + chain tension into a single threshold index.

    - cti: Chain Tension Index 0–10
    - regime_label: COMPRESSION / ASCENT / ...
    - stress_score: 0–1 from hashrate_state.json
    - collapse_window_open: True if intent clock days_remaining == 0
    """

    # 1) Normalize CTI
    cti_norm = max(0.0, min(1.0, cti / 10.0))

    # 2) Clamp incoming stress_score just in case
    s = max(0.0, min(1.0, stress_score))

    # 3) Base index: weighted fusion of miner stress + chain tension
    base = 0.6 * s + 0.4 * cti_norm

    # 4) Regime bonus: only care deeply in COMPRESSION
    if regime_label.upper() == "COMPRESSION":
        base += 0.05  # small lift to reflect tighter field

    # 5) Collapse-window bonus: cliff is open
    if collapse_window_open:
        base += 0.1

    index = max(0.0, min(1.0, base))

    # 6) Banding with strict semantics
    if regime_label.upper() in {"COMPRESSION", "STARVATION"}:
        if stress_score >= 0.7 and cti >= 6.5:
            band: ThresholdBand = "critical"
            at_threshold = True
            note = "Miner field at cliff — producers are being forced to sell."
        elif stress_score >= 0.4 and cti >= 4.5:
            band = "strained"
            at_threshold = True
            note = "Miners in the threshold zone — exits matter more than conviction."
        elif stress_score >= 0.2 or cti >= 3.0:
            band = "amber"
            at_threshold = False
            note = "Miners approaching forced-seller territory."
        else:
            band = "below"
            at_threshold = False
            note = "Miners operating below stress threshold."
    else:
        # Outside meaningful regimes, default to relaxed
        band = "below"
        at_threshold = False
        note = "Miner stress not directional outside COMPRESSION/STARVATION."

    return MinerThresholdResult(
        index=index,
        band=band,
        at_threshold=at_threshold,
        regime=regime_label,
        cti=cti,
        stress_score=s,
        collapse_window_open=collapse_window_open,
        notes=note,
    )


def to_state_dict(result: MinerThresholdResult) -> Dict[str, Any]:
    """Return a JSON-serializable dict snapshot for reports/miner_threshold_state.json."""
    return {
        "version": "1.0",
        "index": round(result.index, 3),
        "band": result.band,
        "at_threshold": result.at_threshold,
        "regime": result.regime,
        "cti": result.cti,
        "stress_score": round(result.stress_score, 3),
        "collapse_window_open": result.collapse_window_open,
        "notes": result.notes,
    }