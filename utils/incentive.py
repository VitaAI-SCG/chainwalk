from typing import Dict, Any

def compute_drivers(daily_state: Dict[str, Any],
                    memory_state: Dict[str, Any],
                    mempool_state: Dict[str, Any]) -> Dict[str, float]:
    # CTI driver
    cti = float(daily_state.get("chain_tension_index", 0.0))
    cti_driver = max(0.0, min(1.0, cti / 10.0))

    # Custody driver
    direction = memory_state.get("custody_direction", "neutral")
    streak = int(memory_state.get("custody_streak", 0))
    streak_factor = min(max(streak, 0) / 7.0, 1.0)

    if direction == "marketward":
        custody_driver = +1.0 * streak_factor
    elif direction == "vaultward":
        custody_driver = -1.0 * streak_factor
    else:
        custody_driver = 0.0

    # Mempool driver
    intent_state = mempool_state.get("state", "NEUTRAL")
    mpi = float(mempool_state.get("mpi", 0.0))

    if intent_state in ("SURGING", "ELEVATING"):
        base = +1.0
    elif intent_state in ("BLEEDING", "PURGE"):
        base = -1.0
    else:
        base = 0.0

    mpi_factor = max(0.0, min(abs(mpi), 0.5)) / 0.5 if mpi is not None else 0.0
    mempool_driver = base * (0.5 + 0.5 * mpi_factor)

    return {
        "cti": round(cti_driver, 3),
        "custody": round(custody_driver, 3),
        "mempool_intent": round(mempool_driver, 3),
    }


def compute_incentive_delta(drivers: Dict[str, float]) -> Dict[str, Any]:
    custody = drivers.get("custody", 0.0)
    mempool = drivers.get("mempool_intent", 0.0)

    incentive_delta = custody + mempool

    if incentive_delta > 0.5:
        label = "market is aligned with the chain’s incentives."
    elif incentive_delta < -0.5:
        label = "market is fighting the chain’s incentives."
    else:
        label = "market is indecisive relative to chain incentives."

    return {
        "value": round(incentive_delta, 3),
        "label": label,
    }


def has_incentive_conflict(custody_direction: str, incentive_delta: float) -> bool:
    """
    Returns True when custody direction and incentive_delta are meaningfully opposed.
    Threshold of 0.25 avoids micro-wiggle false positives.
    """
    if custody_direction == "marketward" and incentive_delta < -0.25:
        return True
    if custody_direction == "vaultward" and incentive_delta > +0.25:
        return True
    return False