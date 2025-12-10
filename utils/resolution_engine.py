# utils/resolution_engine.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Dict, Any

ResolutionBand = Literal["dormant", "charged", "imminent", "triggered"]

@dataclass
class ResolutionResult:
    band: ResolutionBand
    index: float
    details: Dict[str, Any]


def _normalize_01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_resolution_index(
    *,
    regime_label: str,
    chain_tension_index: float,
    custody_streak: int,
    miner_threshold_index: float,
    epoch_tension_index: float,
    irreversibility_index: float,
    mempool_intent_state: str,
    intent_days_remaining: int,
) -> ResolutionResult:
    """
    Compute the Resolution Engine Index (REI).

    REI answers: how close is the current incentive configuration
    to *forcing* a regime resolution, rather than merely storing tension?
    """

    # 1) Normalize drivers
    cti_norm = _normalize_01((chain_tension_index - 4.0) / 4.0)  # focus on 4–8 band
    mti_norm = _normalize_01(miner_threshold_index)
    irq_norm = _normalize_01(irreversibility_index)
    eti_norm = _normalize_01(epoch_tension_index)
    custody_norm = _normalize_01(custody_streak / 10.0)

    # 2) Weighted blend (calibrated to 2025-12-08 state)
    w_cti = 0.25
    w_mti = 0.25
    w_irq = 0.20
    w_eti = 0.10
    w_cust = 0.20

    raw = (
        w_cti * cti_norm +
        w_mti * mti_norm +
        w_irq * irq_norm +
        w_eti * eti_norm +
        w_cust * custody_norm
    )

    rei_index = _normalize_01(raw)

    # 3) Initial band assignment
    if rei_index < 0.30:
        band: ResolutionBand = "dormant"
    elif rei_index < 0.55:
        band = "charged"
    elif rei_index < 0.78:
        band = "imminent"
    else:
        band = "triggered"

    # 4) Gating rules for high-pressure bands
    pressure_regime = regime_label in {"COMPRESSION", "STARVATION"}
    high_cti = chain_tension_index >= 6.5
    high_mti = miner_threshold_index >= 0.78
    high_irq = irreversibility_index >= 0.78

    if band in {"imminent", "triggered"}:
        if not pressure_regime or not high_cti:
            # can't be that high without a genuine pressure regime + CTI
            band = "charged"

    if band == "triggered":
        trigger_ok = (
            pressure_regime and
            high_cti and
            high_mti and
            high_irq and
            mempool_intent_state in {"BLEEDING", "EXHAUSTED"} and
            intent_days_remaining == 0
        )
        if not trigger_ok:
            band = "imminent"

    details: Dict[str, Any] = {
        "rei_index": rei_index,
        "cti_norm": cti_norm,
        "mti_norm": mti_norm,
        "irq_norm": irq_norm,
        "eti_norm": eti_norm,
        "custody_norm": custody_norm,
        "regime_label": regime_label,
        "mempool_intent_state": mempool_intent_state,
        "intent_days_remaining": intent_days_remaining,
    }

    return ResolutionResult(band=band, index=rei_index, details=details)