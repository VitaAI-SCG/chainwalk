from dataclasses import dataclass
from typing import Dict, Literal

Trend = Literal["rising", "falling", "flat"]
StressBand = Literal["calm", "strained", "distress"]


@dataclass
class HashrateInputs:
    # raw network state (daily or last-24h snapshot)
    hashrate_eh: float          # current network hashrate (EH/s)
    hashrate_eh_prev: float     # previous day's hashrate (EH/s)
    hashrate_eh_ma7: float      # 7d moving average (EH/s)

    difficulty: float           # current difficulty
    difficulty_prev: float      # previous difficulty

    subsidy_btc: float          # block subsidy (e.g., 3.125)
    fees_24h_btc: float         # total fees in last 24h (sum over 144 blocks)
    price_usd: float            # BTCUSD spot used elsewhere in ChainWalk


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return default if b == 0 else a / b


def compute_hashrate_trend(inp: HashrateInputs) -> Trend:
    """Direction of hashrate vs 7d baseline."""
    delta = inp.hashrate_eh - inp.hashrate_eh_ma7
    thresh = max(inp.hashrate_eh_ma7 * 0.01, 1.0)  # 1% or 1 EH/s minimum
    if delta > thresh:
        return "rising"
    if delta < -thresh:
        return "falling"
    return "flat"


def compute_revenue_per_eh(inp: HashrateInputs) -> float:
    """
    Approximate miner revenue per EH per day (USD).
    Very rough, but *relative* moves are what matter.
    """
    blocks_per_day = 144.0
    total_btc_per_day = (inp.subsidy_btc * blocks_per_day) + inp.fees_24h_btc
    total_usd_per_day = total_btc_per_day * inp.price_usd
    # EH/s → TH/s: 1 EH = 1e6 TH
    return _safe_div(total_usd_per_day, inp.hashrate_eh * 1e6)


def compute_miner_stress(inp: HashrateInputs) -> Dict:
    trend = compute_hashrate_trend(inp)
    rev_now = compute_revenue_per_eh(inp)

    # Baseline: 7d proxy via hashrate + fees (cheap but consistent)
    # We treat fees_24h_btc as "current"; for baseline, approximate using same fees.
    rev_baseline = rev_now  # if you want, later plug a 7d avg here
    # For now, stress is driven mainly by trend + difficulty
    # and sign flips when difficulty ↑ and hashrate ↑.

    # Difficulty pressure: positive when difficulty has recently increased
    diff_change = _safe_div(inp.difficulty - inp.difficulty_prev, inp.difficulty_prev, 0.0)

    # Rev "squeeze": we encode as 0 for now, but we keep the field so swapping
    # in a real 7d baseline later is trivial.
    rev_squeeze = 0.0

    raw = 0.0

    if trend == "rising":
        # Rising hash into rising difficulty = pressure
        raw += max(diff_change * 20.0, 0.0)  # scale difficulty impact
        raw += max(-rev_squeeze * 10.0, 0.0)  # stronger if revenue is falling
    elif trend == "falling":
        # Falling hash + flat difficulty = easing
        raw += max(-diff_change * 10.0, 0.0) * 0.5

    # Clamp to [0, 10]
    stress_score = max(0.0, min(10.0, raw))

    if stress_score < 3.0:
        band: StressBand = "calm"
        label = "Miner field calm — producer pressure not yet directional."
    elif stress_score < 6.0:
        band = "strained"
        label = "Miner field strained — rising hash into tightening difficulty."
    else:
        band = "distress"
        label = "Miner field distressed — hash and difficulty force exit liquidity."

    return {
        "trend": trend,
        "difficulty_change": round(diff_change, 4),
        "rev_per_eh_usd": round(rev_now, 4),
        "stress_score": round(stress_score, 2),
        "stress_band": band,
        "label": label,
    }


def hashrate_to_json(date_utc: str, inp: HashrateInputs) -> Dict:
    state = compute_miner_stress(inp)
    state["date_utc"] = date_utc
    state["hashrate_eh"] = inp.hashrate_eh
    state["hashrate_eh_prev"] = inp.hashrate_eh_prev
    state["hashrate_eh_ma7"] = inp.hashrate_eh_ma7
    return state