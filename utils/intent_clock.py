from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, Optional

HALF_LIFE = 15  # days of patience before desire expires

@dataclass
class IntentClockState:
    date_utc: str
    intent_state: str
    streak_days: int
    half_life_days: int
    max_days_remaining: int
    stress: str
    clock_line: str

def compute_intent_clock(
    date_utc: str,
    intent_state: str,
    regime_label: str,
    prev_state: Optional[Dict[str, Any]] = None,
    half_life_days: int = 15,
) -> Dict[str, Any]:
    """
    Update Intent Clock in a day-aware, idempotent way.
    Re-running on the same date does NOT advance streak_days or decay max_days_remaining.
    """
    current_date = datetime.fromisoformat(date_utc).date()

    if prev_state is None or intent_state != prev_state.get("intent_state"):
        # New streak
        streak_days = 1
        max_days_remaining = half_life_days - streak_days
    else:
        prev_date_str = prev_state.get("date_utc")
        if prev_date_str:
            prev_date = datetime.fromisoformat(prev_date_str).date()
            if current_date == prev_date:
                # Same day, idempotent
                streak_days = prev_state["streak_days"]
                max_days_remaining = prev_state["max_days_remaining"]
            else:
                # Days passed
                delta_days = (current_date - prev_date).days
                streak_days = prev_state["streak_days"] + delta_days
                max_days_remaining = max(0, half_life_days - streak_days)
        else:
            # Fallback
            streak_days = 1
            max_days_remaining = half_life_days - streak_days

    # Compute stress
    stress = "HIGH" if regime_label == "COMPRESSION" and intent_state in ("BLEEDING","PURGE") and max_days_remaining < 10 else "NORMAL"

    if intent_state in ("ELEVATING","SURGING"):
        line = f"desire is building — {max_days_remaining} days until intent overflows into resolution."
    elif intent_state == "BLEEDING":
        if max_days_remaining == 0:
            line = "desire has expired — the collapse window is now open."
        else:
            line = f"desire is decaying — {max_days_remaining} days remain before intent collapses."
    elif intent_state == "PURGE":
        line = "desire reset — the queue has been flushed."
    else:
        line = f"intent steady — {max_days_remaining} days before patience runs out."

    return {
        "date_utc": date_utc,
        "intent_state": intent_state,
        "streak_days": streak_days,
        "half_life_days": half_life_days,
        "max_days_remaining": max_days_remaining,
        "stress": stress,
        "clock_line": line,
    }

def intent_clock_to_json(clock: IntentClockState):
    return asdict(clock)