from dataclasses import dataclass, asdict
from typing import Dict, Any

MIN_STREAK_DAYS = 40
MAX_STREAK_DAYS = 70


def classify_phase(streak_days: int,
                   min_total: int = MIN_STREAK_DAYS,
                   max_total: int = MAX_STREAK_DAYS) -> str:
    """
    Map current streak into a coarse phase: EARLY / MID / LATE.
    - Uses ratio of streak_days / max_total.
    - Always returns one of {"EARLY","MID","LATE"}.
    """
    if max_total <= 0:
        return "EARLY"  # defensive fallback

    ratio = streak_days / max_total

    if ratio < 1.0 / 3.0:
        return "EARLY"
    elif ratio < 2.0 / 3.0:
        return "MID"
    else:
        return "LATE"


@dataclass
class RegimeClockState:
    date_utc: str
    regime_label: str
    streak_days: int
    phase: str
    window_days: Dict[str, int]
    clock_line: str


def compute_regime_clock(
    *,
    date_utc: str,
    regime_label: str,
    streak_days: int,
    min_total: int = MIN_STREAK_DAYS,
    max_total: int = MAX_STREAK_DAYS,
) -> RegimeClockState:
    """
    Pure, side-effect free builder for RegimeClockState.
    Does not touch disk; consumer is responsible for saving.
    """

    if streak_days < 0:
        streak_days = 0  # defensive

    min_remaining = max(0, min_total - streak_days)
    max_remaining = max(0, max_total - streak_days)

    phase = classify_phase(streak_days, min_total, max_total)

    # Build a compact human line for direct use in posts.
    # Example: "Regime Clock: MID COMPRESSION — 10–40 days left in this coil."
    if max_remaining == 0:
        remaining_part = "coil at terminal stretch."
    else:
        remaining_part = f"{min_remaining}–{max_remaining} days left in this coil."

    pretty_regime = regime_label.upper()

    clock_line = f"{phase} {pretty_regime} — {remaining_part}"

    return RegimeClockState(
        date_utc=date_utc,
        regime_label=regime_label,
        streak_days=streak_days,
        phase=phase,
        window_days={
            "min_total": min_total,
            "max_total": max_total,
            "min_remaining": min_remaining,
            "max_remaining": max_remaining,
        },
        clock_line=clock_line,
    )


def regime_clock_to_json(clock: RegimeClockState) -> Dict[str, Any]:
    """Helper to convert to a plain dict ready for json.dump."""
    return asdict(clock)