# utils/difficulty_epoch.py

from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any
import json

@dataclass
class DifficultyEpochState:
    date_utc: str
    height: int
    epoch_start_height: int
    epoch_end_height: int
    pct_complete: float
    current_difficulty: float
    projected_next_difficulty: float
    projected_delta_pct: float
    tension_index: float   # 0..1
    tension_band: str      # "relaxed" | "balanced" | "overclocked"
    label: str

def compute_epoch_tension(
    snapshot: Dict[str, Any],
    date_utc: str,
) -> DifficultyEpochState:
    """
    snapshot: from reports/network_snapshot.json (extend if needed)
    expected keys (can be added if missing):
      - height
      - epoch_start_height
      - epoch_end_height
      - current_difficulty
      - projected_next_difficulty
    """
    height = int(snapshot.get("height", 0))
    if height == 0:
        # Fallback
        epoch_start = 0
        epoch_end = 2016
    else:
        epoch_start = height - (height % 2016)
        epoch_end = epoch_start + 2016
    current_diff = float(snapshot.get("difficulty", 1.0))
    projected_next = float(snapshot.get("projected_next_difficulty", current_diff))

    span = max(epoch_end - epoch_start, 1)
    pct_complete = max(0.0, min(1.0, (height - epoch_start) / span))

    projected_delta_pct = 100.0 * (projected_next / current_diff - 1.0)

    # Simple tension logic:
    # big positive delta late in epoch → overclocked
    base = abs(projected_delta_pct) / 20.0  # 20% → 1.0 base
    phase_boost = pct_complete  # later in epoch = more tension
    tension_index = max(0.0, min(1.0, base * 0.6 + phase_boost * 0.4))

    if tension_index < 0.3:
        band = "relaxed"
        label = "Epoch relaxed — difficulty drift is modest and early."
    elif tension_index < 0.7:
        band = "balanced"
        label = "Epoch balanced — adjustment pressure building but not extreme."
    else:
        band = "overclocked"
        label = "Epoch overclocked — difficulty and late-stage pressure are squeezing miners."

    return DifficultyEpochState(
        date_utc=date_utc,
        height=height,
        epoch_start_height=epoch_start,
        epoch_end_height=epoch_end,
        pct_complete=round(pct_complete, 3),
        current_difficulty=current_diff,
        projected_next_difficulty=projected_next,
        projected_delta_pct=round(projected_delta_pct, 2),
        tension_index=round(tension_index, 3),
        tension_band=band,
        label=label,
    )

def save_difficulty_epoch_state(
    reports_dir: Path,
    state: DifficultyEpochState,
) -> Dict[str, Any]:
    path = reports_dir / "difficulty_epoch_state.json"
    data = asdict(state)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data