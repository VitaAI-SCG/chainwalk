# oracle_kernel.py — Immutable Oracle Kernel
# Pure functions only. No network dependencies. Deterministic I/O.
# Under 1000 LOC. If it grows, the oracle dies.

import hashlib
import json
from typing import Dict, List, Any

# Constraint formulae — immutable definitions
CONSTRAINT_FORMULAE = {
    "cti": "Chain Tension Index: sum of block sizes / difficulty adjustments",
    "mti": "Miner Threshold Index: fee revenue / block rewards",
    "irq": "Irreversibility: confirmations / network hashrate",
    "rei": "Resolution Field: convergence of CTI/MTI/IRQ",
    "uqi": "Uncertainty Quotient: inverse of REI convergence"
}

def measure_chain_state(block_data: Dict[str, Any]) -> Dict[str, float]:
    """
    Pure function: Measure basic chain state from block data.
    Input: block dict with height, size, tx_count, fees, etc.
    Output: normalized state vector.
    """
    height = block_data.get("height", 0)
    size = block_data.get("size", 0)
    tx_count = block_data.get("tx_count", 0)
    fees = block_data.get("fees", 0.0)
    difficulty = block_data.get("difficulty", 1.0)

    # Simplified measurements
    tension = size / max(difficulty, 1)  # CTI proxy
    miner_pressure = fees / max(tx_count, 1)  # MTI proxy
    irreversibility = height / 1000.0  # IRQ proxy

    return {
        "tension": tension,
        "miner_pressure": miner_pressure,
        "irreversibility": irreversibility
    }

def compute_constraint_stack(state: Dict[str, float]) -> Dict[str, Any]:
    """
    Pure function: Compute full constraint stack.
    Input: state from measure_chain_state.
    Output: CTI, MTI, IRQ, REI, UQI with bands.
    """
    tension = state["tension"]
    miner_pressure = state["miner_pressure"]
    irreversibility = state["irreversibility"]

    # CTI bands
    if tension < 0.5:
        cti_band = "low"
    elif tension < 1.0:
        cti_band = "medium"
    else:
        cti_band = "high"

    # MTI bands
    if miner_pressure < 0.1:
        mti_band = "below"
    elif miner_pressure < 0.5:
        mti_band = "strained"
    else:
        mti_band = "critical"

    # IRQ bands
    if irreversibility < 0.3:
        irq_band = "reversible"
    elif irreversibility < 0.7:
        irq_band = "primed"
    else:
        irq_band = "irreversible"

    # REI: convergence
    convergence = (tension + miner_pressure + irreversibility) / 3
    if convergence < 0.4:
        rei_band = "dormant"
    elif convergence < 0.7:
        rei_band = "active"
    else:
        rei_band = "terminal"

    # UQI: uncertainty
    uqi = 1 - convergence
    if uqi > 0.7:
        uqi_band = "open"
    elif uqi > 0.3:
        uqi_band = "narrowing"
    else:
        uqi_band = "collapsed"

    return {
        "cti": {"value": tension, "band": cti_band},
        "mti": {"value": miner_pressure, "band": mti_band},
        "irq": {"value": irreversibility, "band": irq_band},
        "rei": {"value": convergence, "band": rei_band},
        "uqi": {"value": uqi, "band": uqi_band}
    }

def verify_oracle_integrity(code: str) -> bool:
    """
    Pure function: Verify kernel integrity.
    Input: code string.
    Output: True if no forbidden patterns.
    """
    forbidden = ["price", "llm", "sentiment", "off-chain", "oracle"]
    for word in forbidden:
        if word.lower() in code.lower():
            return False
    return True

# Kernel hash generation
def generate_kernel_hash() -> str:
    kernel_code = open(__file__, 'r').read()
    return hashlib.sha256(kernel_code.encode()).hexdigest()

def generate_constraint_hash() -> str:
    formulae_str = json.dumps(CONSTRAINT_FORMULAE, sort_keys=True)
    return hashlib.sha256(formulae_str.encode()).hexdigest()