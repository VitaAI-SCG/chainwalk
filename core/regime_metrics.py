from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from collections import Counter

Signal = Dict[str, Any]

@dataclass
class ChainTensionSnapshot:
    # core counts
    block_count: int
    polyphonic_rate: float          # 0.0–1.0
    avg_entropy: float              # H
    avg_complexity: float           # K
    avg_fee_pressure: float         # 0.0–1.0
    whale_tx_share: float           # 0.0–1.0
    miner_concentration: float      # 0.0–1.0 (Herfindahl or top-2 share)
    custody_bias: float             # -1.0 (into exchanges) → +1.0 (into self-custody)

    # derived index
    chain_tension_index: float      # 0.0–10.0
    regime_label: str               # "calm" | "neutral" | "stressed" | "compression"

    # for comparison with previous day
    drivers: Dict[str, float]       # e.g. {"polyphonic": 0.62, "fees": 0.31, ...}


def compute_snapshot(signals: List[Signal]) -> ChainTensionSnapshot:
    if not signals:
        return ChainTensionSnapshot(
            block_count=0,
            polyphonic_rate=0.0,
            avg_entropy=0.0,
            avg_complexity=0.0,
            avg_fee_pressure=0.0,
            whale_tx_share=0.0,
            miner_concentration=0.0,
            custody_bias=0.0,
            chain_tension_index=0.0,
            regime_label="calm",
            drivers={}
        )

    block_count = len(signals)

    # Polyphonic rate
    polys = [s for s in signals if s.get("polyphonic")]
    poly_rate = len(polys) / block_count

    # Entropy / complexity
    entropies = [s.get("entropy_h") or s.get("entropy") for s in signals if s.get("entropy_h") or s.get("entropy")]
    complexities = [s.get("complexity_k") or s.get("complexity") for s in signals if s.get("complexity_k") or s.get("complexity")]
    avg_H = sum(entropies) / len(entropies) if entropies else 0.0
    avg_K = sum(complexities) / len(complexities) if complexities else 0.0

    # Fee pressure (0–1)
    fee_ps = []
    for s in signals:
        v = s.get("fees_pct")
        if v is not None:
            fee_ps.append(min(1.0, max(0.0, v)))
    avg_fee_pressure = sum(fee_ps) / len(fee_ps) if fee_ps else 0.0

    # Whale tx share (0–1)
    whale_blocks = 0
    for s in signals:
        if s.get("channels", {}).get("whale_flow"):
            whale_blocks += 1
        else:
            lt = s.get("largest_tx_btc") or s.get("largest_tx")
            if lt and lt >= 50:
                whale_blocks += 1
    whale_share = whale_blocks / block_count

    # Miner concentration (0–1)
    pools = [s.get("pool", "unknown") for s in signals]
    c = Counter(pools)
    total = block_count
    shares = [cnt / total for cnt in c.values()]
    miner_concentration = sum(sh * sh for sh in shares)  # Herfindahl

    # Custody bias (-1 → +1)
    custody_signals = 0
    for s in signals:
        chans = s.get("channels", {})
        if chans.get("custody_shift"):
            custody_signals += 1
    custody_bias = 0.0  # Placeholder, as per spec

    # Chain Tension Index (0–10)
    poly = poly_rate
    fees = avg_fee_pressure
    whales = whale_share
    miners = miner_concentration
    custody_tension = custody_signals / block_count

    w_poly = 0.30
    w_fees = 0.20
    w_whales = 0.20
    w_miners = 0.20
    w_custody = 0.10

    raw = (
        w_poly * poly +
        w_fees * fees +
        w_whales * whales +
        w_miners * miners +
        w_custody * custody_tension
    )

    chain_tension_index = max(0.0, min(10.0, raw * 10.0))

    # Regime labels
    if chain_tension_index < 3.5:
        regime = "calm"
    elif chain_tension_index < 6.5:
        regime = "neutral"
    elif chain_tension_index < 8.5:
        regime = "stressed"
    else:
        regime = "compression"

    # Drivers dict
    drivers = {
        "polyphonic": poly_rate,
        "fees": avg_fee_pressure,
        "whales": whale_share,
        "miners": miner_concentration,
        "custody": custody_tension,
    }

    return ChainTensionSnapshot(
        block_count=block_count,
        polyphonic_rate=poly_rate,
        avg_entropy=avg_H,
        avg_complexity=avg_K,
        avg_fee_pressure=avg_fee_pressure,
        whale_tx_share=whale_share,
        miner_concentration=miner_concentration,
        custody_bias=custody_bias,
        chain_tension_index=chain_tension_index,
        regime_label=regime,
        drivers=drivers
    )