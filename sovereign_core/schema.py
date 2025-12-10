from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any, List


@dataclass
class Channels:
    coinbase_low_entropy: bool = False
    coinbase_low_complexity: bool = False
    header_tail_anomaly: bool = False
    inter_block_chain: bool = False
    script_pattern: bool = False
    time_delta_weird: bool = False
    finance_whale_tx: bool = False
    finance_high_fees: bool = False
    utxo_pressure: bool = False
    fee_pressure: bool = False

    def active_count(self) -> int:
        return sum(bool(v) for v in asdict(self).values())

    def to_dict(self) -> Dict[str, bool]:
        return asdict(self)


@dataclass
class Signal:
    height: int
    pool: str
    timestamp: int
    entropy: float
    complexity: float
    channels: Dict[str, bool]
    tx_count: int | None = None
    total_output_btc: float | None = None
    largest_tx_btc: float | None = None
    total_fee_btc: float | None = None
    polyphonic: bool = False
    era_label: str = "unknown"
    sample_hex: str = ""
    plain: str = ""

    # Enhanced fields
    header_entropy: float | None = None
    header_complexity: float | None = None
    script_patterns: Dict[str, Any] | None = None
    network_health: Dict[str, Any] | None = None
    polyphony_score: int = 0

    # APEX signals
    risk_vector: str = "→"
    custody_state: str = "market"
    miner_motive: str = "neutral"

    def polyphonic_check(self) -> bool:
        return self.polyphony_score >= 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "height": self.height,
            "timestamp": self.timestamp,
            "pool": self.pool,
            "entropy": self.entropy,
            "complexity": self.complexity,
            "channels": self.channels,
            "tx_count": self.tx_count,
            "total_output_btc": self.total_output_btc,
            "largest_tx_btc": self.largest_tx_btc,
            "total_fee_btc": self.total_fee_btc,
            "polyphonic": self.polyphonic,
            "era_label": self.era_label,
            "sample_hex": self.sample_hex,
            "plain": self.plain,
            "header_entropy": self.header_entropy,
            "header_complexity": self.header_complexity,
            "script_patterns": self.script_patterns,
            "network_health": self.network_health,
            "polyphony_score": self.polyphony_score,
        }


def build_payload(signals: List[Signal], tip_height: int, window_size: int) -> Dict[str, Any]:
    return {
        "engine": "SOVEREIGN_EAR_V6",
        "tip_height": tip_height,
        "window_size": window_size,
        "signal_count": len(signals),
        "polyphonic_count": sum(1 for s in signals if s.polyphonic),
        "signals": [s.to_dict() for s in signals],
        "generated_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
    }
