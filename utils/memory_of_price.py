from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"
CTI_HISTORY_PATH = REPORTS_DIR / "cti_history.jsonl"
MEMORY_STATE_PATH = REPORTS_DIR / "memory_of_price_state.json"

@dataclass
class MemorySnapshot:
    cti_last: float
    cti_prev_7d: float | None
    cti_trend_7d: str           # "rising" | "falling" | "flat"
    custody_direction: str      # "vaultward" | "marketward"
    custody_streak: int
    entropy_trend_7d: str       # "rising" | "falling" | "flat"
    miner_fee_trend: str        # "rising" | "flat" | "falling"

def load_cti_history() -> List[Dict[str, Any]]:
    if not CTI_HISTORY_PATH.exists():
        return []
    history = []
    with CTI_HISTORY_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    history.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return history

def save_cti_history(history: List[Dict[str, Any]]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with CTI_HISTORY_PATH.open("w", encoding="utf-8") as f:
        for entry in history:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

def update_memory_state(
    cti_today: float,
    custody_direction: str,
    entropy_stats: Dict[str, Any],
    miner_fee_stats: Dict[str, Any],
    regime: str = "unknown"
) -> MemorySnapshot:
    today_str = datetime.now().date().isoformat()
    entropy_mean = entropy_stats.get("mean", 0.0)
    entropy_gradient_7d = entropy_stats.get("gradient_7d", 0.0)
    miner_fee_bias = miner_fee_stats.get("bias", "flat")

    # Load existing history
    history = load_cti_history()

    # Remove existing entry for today if present
    history = [h for h in history if h.get("as_of") != today_str]

    # Append today's entry
    today_entry = {
        "as_of": today_str,
        "cti": cti_today,
        "custody_direction": custody_direction,
        "entropy_mean": entropy_mean,
        "entropy_gradient_7d": entropy_gradient_7d,
        "miner_fee_bias": miner_fee_bias,
        "regime": regime
    }
    history.append(today_entry)

    # Sort by date
    history.sort(key=lambda x: x["as_of"])

    # Save history
    save_cti_history(history)

    # Compute snapshot
    cti_last = cti_today
    cti_prev_7d = None
    seven_days_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
    for entry in reversed(history):
        if entry["as_of"] <= seven_days_ago:
            cti_prev_7d = entry["cti"]
            break

    # CTI trend
    if cti_prev_7d is not None:
        delta = cti_last - cti_prev_7d
        if delta >= 0.3:
            cti_trend_7d = "rising"
        elif delta <= -0.3:
            cti_trend_7d = "falling"
        else:
            cti_trend_7d = "flat"
    else:
        cti_trend_7d = "flat"

    # Custody streak
    custody_streak = 0
    for entry in reversed(history):
        if entry["custody_direction"] == custody_direction:
            custody_streak += 1
        else:
            break

    # Entropy trend
    if entropy_gradient_7d >= 0.1:
        entropy_trend_7d = "rising"
    elif entropy_gradient_7d <= -0.1:
        entropy_trend_7d = "falling"
    else:
        entropy_trend_7d = "flat"

    # Miner fee trend
    miner_fee_trend = miner_fee_bias

    # Save state
    state = {
        "last_update": today_str,
        "cti_last": cti_last,
        "cti_prev_7d": cti_prev_7d,
        "cti_trend_7d": cti_trend_7d,
        "custody_streak": custody_streak,
        "custody_direction": custody_direction,
        "entropy_trend_7d": entropy_trend_7d,
        "miner_fee_trend": miner_fee_trend,
        "memory_comment": f"CTI {cti_trend_7d} with {custody_direction} custody streak of {custody_streak} and {entropy_trend_7d} entropy."
    }
    with MEMORY_STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    return MemorySnapshot(
        cti_last=cti_last,
        cti_prev_7d=cti_prev_7d,
        cti_trend_7d=cti_trend_7d,
        custody_direction=custody_direction,
        custody_streak=custody_streak,
        entropy_trend_7d=entropy_trend_7d,
        miner_fee_trend=miner_fee_trend
    )