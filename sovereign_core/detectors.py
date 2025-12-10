from __future__ import annotations

from collections import deque
from typing import Dict, List, Tuple

from .entropy import shannon_entropy, compression_ratio
from .providers import SimpleBlock
from .schema import Channels, Signal


class DetectorState:
    def __init__(self, max_recent: int = 256):
        self.recent_samples = deque(maxlen=max_recent)
        self.last_timestamp: int | None = None


def _decode_coinbase(script: bytes) -> str:
    """Decode coinbase script to readable text."""
    try:
        return script.decode('utf-8', errors='replace')
    except Exception:
        return "⟨binary⟩"


def classify_quadrant(entropy: float, complexity: float) -> str:
    if entropy < 4.0 and complexity < 0.9:
        return "low_entropy_low_complexity"
    if entropy < 4.0 and complexity >= 0.9:
        return "low_entropy_high_complexity"
    if entropy >= 4.0 and complexity < 0.9:
        return "high_entropy_low_complexity"
    return "high_entropy_high_complexity"


def _detect_era(height: int) -> str:
    """Enhanced era detection with more granular periods."""
    if height < 100_000:
        return "satoshi_early"
    elif height < 200_000:
        return "satoshi_late"
    elif height < 300_000:
        return "gpu_early"
    elif height < 400_000:
        return "gpu_late"
    elif height < 450_000:
        return "asic_transition"
    elif height < 500_000:
        return "asic_wars"
    elif height < 600_000:
        return "taproot_prep"
    elif height < 700_000:
        return "segwit"
    elif height < 800_000:
        return "taproot"
    else:
        return "post_etf"


def _enhance_pool_hint(pool_hint: str, coinbase: bytes) -> str:
    """Improve pool identification using coinbase patterns."""
    if not pool_hint or pool_hint == "unknown":
        cb_str = coinbase.decode('utf-8', errors='ignore').lower()
        if 'foundry' in cb_str:
            return "Foundry USA"
        elif 'viabtc' in cb_str:
            return "ViaBTC"
        elif 'antpool' in cb_str:
            return "AntPool"
        elif 'f2pool' in cb_str:
            return "F2Pool"
        elif 'binance' in cb_str:
            return "Binance Pool"
        elif 'luxor' in cb_str:
            return "Luxor"
    return pool_hint or "unknown"


def _analyze_script_patterns(coinbase: bytes) -> Dict[str, any]:
    """Analyze coinbase for miner signaling patterns."""
    patterns = {
        "has_pattern": False,
        "ascii_art": False,
        "version_signaling": False,
        "pool_message": False,
        "technical_data": False,
    }

    try:
        cb_str = coinbase.decode('utf-8', errors='ignore')

        # ASCII art detection (repeated characters, symbols)
        if any(char * 3 in cb_str for char in "!@#$%^&*()_+-=[]{}|;:,.<>?"):
            patterns["ascii_art"] = True

        # Version signaling (common patterns)
        if any(sig in cb_str.lower() for sig in ["/segwit", "/taproot", "/bip"]):
            patterns["version_signaling"] = True

        # Pool messages
        if any(msg in cb_str.lower() for msg in ["mempool", "block", "hash", "pool"]):
            patterns["pool_message"] = True

        # Technical data (hex-like patterns)
        hex_chars = set("0123456789abcdefABCDEF")
        if sum(1 for c in cb_str if c in hex_chars) / len(cb_str) > 0.6:
            patterns["technical_data"] = True

        patterns["has_pattern"] = any(patterns.values())

    except Exception:
        pass

    return patterns


def _analyze_network_health(block: SimpleBlock, entropy: float, complexity: float) -> Dict[str, any]:
    """Analyze block for network health indicators."""
    health = {
        "miner_competition": "normal",
        "fee_market": "normal",
        "block_efficiency": "normal",
        "unusual_activity": False,
    }

    # Miner competition (based on tx count and fees)
    if block.tx_count and block.tx_count > 4000:
        health["miner_competition"] = "high"
    elif block.tx_count and block.tx_count < 1000:
        health["miner_competition"] = "low"

    # Fee market pressure
    if block.total_fee_btc and block.total_output_btc:
        fee_ratio = block.total_fee_btc / block.total_output_btc
        if fee_ratio > 0.005:
            health["fee_market"] = "high_pressure"
        elif fee_ratio < 0.0001:
            health["fee_market"] = "low_pressure"

    # Block efficiency (entropy/complexity balance)
    if entropy > 6.0 and complexity < 0.8:
        health["block_efficiency"] = "high_entropy_efficient"
    elif entropy < 3.0 and complexity > 1.2:
        health["block_efficiency"] = "low_entropy_complex"

    # Unusual activity flag
    health["unusual_activity"] = (
        health["miner_competition"] in ["high", "low"] or
        health["fee_market"] in ["high_pressure", "low_pressure"] or
        health["block_efficiency"] != "normal"
    )

    return health


def detect_signals(blocks: List[SimpleBlock]) -> Tuple[List[Signal], DetectorState]:
    state = DetectorState()

    stats: List[Dict] = []
    for b in blocks:
        cb = b.coinbase_script
        cb_entropy = shannon_entropy(cb)
        cb_complexity = compression_ratio(cb)

        tail_bytes = bytes.fromhex(b.block_hash[-32:]) if b.block_hash else b""
        tail_entropy = shannon_entropy(tail_bytes)
        tail_complexity = compression_ratio(tail_bytes)

        # Additional analysis: script patterns
        script_patterns = _analyze_script_patterns(cb)

        stats.append(
            {
                "block": b,
                "cb_entropy": cb_entropy,
                "cb_complexity": cb_complexity,
                "tail_entropy": tail_entropy,
                "tail_complexity": tail_complexity,
                "script_patterns": script_patterns,
            }
        )

    if not stats:
        return [], state

    # Sort by height for time-series analysis
    stats.sort(key=lambda s: s["block"].height)

    signals: List[Signal] = []
    for i, stat in enumerate(stats):
        b = stat["block"]

        # Coinbase analysis
        cb_entropy = stat["cb_entropy"]
        cb_complexity = stat["cb_complexity"]
        quadrant = classify_quadrant(cb_entropy, cb_complexity)

        # Header tail analysis
        tail_entropy = stat["tail_entropy"]
        tail_complexity = stat["tail_complexity"]

        # Script pattern analysis
        script_patterns = stat["script_patterns"]

        # Time delta analysis (compare with previous)
        time_delta_weird = False
        if i > 0:
            prev_timestamp = stats[i-1]["block"].timestamp
            current_timestamp = b.timestamp
            expected_delta = 600  # 10 minutes
            actual_delta = current_timestamp - prev_timestamp
            time_delta_weird = abs(actual_delta - expected_delta) > 120  # >2 min deviation

        # Enhanced channels
        channels = Channels(
            coinbase_low_entropy=cb_entropy < 4.0,
            coinbase_low_complexity=cb_complexity < 0.9,
            header_tail_anomaly=tail_entropy > 6.0 or tail_complexity > 1.2,
            time_delta_weird=time_delta_weird,
            finance_whale_tx=b.largest_tx_btc >= 1000.0 if b.largest_tx_btc else False,
            finance_high_fees=b.total_fee_btc >= 5.0 if b.total_fee_btc else False,
            script_pattern=script_patterns.get("has_pattern", False),
            utxo_pressure=b.tx_count > 3000 if b.tx_count else False,  # High tx count
            fee_pressure=b.total_fee_btc / max(b.total_output_btc, 0.001) > 0.001 if b.total_fee_btc and b.total_output_btc else False,
        )

        # Polyphony: multiple active channels (weighted)
        channel_weights = {
            "coinbase_low_entropy": 1,
            "coinbase_low_complexity": 1,
            "header_tail_anomaly": 2,
            "time_delta_weird": 3,
            "finance_whale_tx": 2,
            "finance_high_fees": 2,
            "script_pattern": 1,
            "utxo_pressure": 1,
            "fee_pressure": 1,
        }
        polyphony_score = sum(channel_weights.get(k, 1) for k, v in channels.__dict__.items() if v)
        polyphonic = polyphony_score >= 3

        # Era detection (enhanced)
        era = _detect_era(b.height)

        # APEX signals
        risk_vector = "→"  # neutral
        if channels.finance_high_fees or channels.finance_whale_tx:
            risk_vector = "↑"
        elif channels.coinbase_low_entropy:
            risk_vector = "↓"

        custody_state = "market"
        if channels.utxo_pressure or channels.finance_whale_tx:
            custody_state = "vault"

        # Pool enhancement
        enhanced_pool = _enhance_pool_hint(b.pool_hint, cb)

        # APEX miner motive - predictive flows
        miner_motive = "preparing scarcity regime"  # default inevitability
        major_pools = ["antpool", "foundry", "binance", "f2pool"]
        if enhanced_pool.lower() in major_pools:
            if channels.finance_high_fees:
                miner_motive = "positioning for fee dominance"
            elif b.total_fee_btc < 0.1:  # low fee
                miner_motive = "exiting price discovery"
            else:
                miner_motive = "front-running regulatory choke points"

        # Network health signals
        network_signals = _analyze_network_health(b, cb_entropy, cb_complexity)

        signal = Signal(
            height=b.height,
            timestamp=b.timestamp,
            pool=enhanced_pool,
            entropy=round(cb_entropy, 3),
            complexity=round(cb_complexity, 3),
            channels=channels.__dict__,
            tx_count=b.tx_count,
            total_output_btc=round(b.total_output_btc, 8),
            largest_tx_btc=round(b.largest_tx_btc, 8) if b.largest_tx_btc else 0.0,
            total_fee_btc=round(b.total_fee_btc, 8) if b.total_fee_btc else 0.0,
            polyphonic=polyphonic,
            risk_vector=risk_vector,
            custody_state=custody_state,
            miner_motive=miner_motive,
            era_label=era,
            sample_hex=b.coinbase_script.hex()[:80] if b.coinbase_script else "",
            plain=_decode_coinbase(b.coinbase_script),
            # New fields
            header_entropy=round(tail_entropy, 3),
            header_complexity=round(tail_complexity, 3),
            script_patterns=script_patterns,
            network_health=network_signals,
            polyphony_score=polyphony_score,
        )

        signals.append(signal)

        # Update state with more data
        state.recent_samples.append(
            {
                "height": b.height,
                "entropy": cb_entropy,
                "complexity": cb_complexity,
                "polyphonic": polyphonic,
                "era": era,
                "pool": enhanced_pool,
            }
        )
        state.last_timestamp = b.timestamp

    return signals, state
