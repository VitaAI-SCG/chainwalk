from dataclasses import dataclass
from typing import Dict
from utils.memory_of_price import MemorySnapshot
from utils.price_corridor_engine import CorridorSnapshot
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"
REGIME_STATE_PATH = REPORTS_DIR / "regime_state.json"

@dataclass
class RegimeSnapshot:
    name: str
    custody: str
    tension: float
    entropy: str
    corridor: str
    inevitability: str
    scores: Dict[str, float]

def classify_regime(memory_snapshot: MemorySnapshot, corridor_snapshot: CorridorSnapshot) -> RegimeSnapshot:
    # Extract values
    custody = memory_snapshot.custody_direction  # vaultward or marketward
    tension = memory_snapshot.cti_last
    entropy = memory_snapshot.entropy_trend_7d  # rising, falling, flat
    corridor = corridor_snapshot.legality_floor  # structurally illegal, fragile, permitted

    # Compute raw scores
    scores = {"S": 0.0, "C": 0.0, "D": 0.0, "A": 0.0}

    # CTI upper band
    if tension >= 7:
        scores["C"] += 1.0
        scores["A"] += 1.0

    # CTI lower band and weak custody
    if tension <= 3 and custody == "marketward":
        scores["D"] += 1.0
        if entropy == "rising":  # starvation pattern
            scores["S"] += 1.0

    # Custody marketward with streak
    if custody == "marketward" and memory_snapshot.custody_streak > 0:
        streak_factor = min(memory_snapshot.custody_streak / 10.0, 1.0)  # cap at 1.0
        scores["C"] += 0.5 * streak_factor
        scores["A"] += 0.5 * streak_factor
        scores["D"] -= 0.5

    # Corridor
    if corridor == "structurally illegal":
        scores["C"] += 0.5
        scores["A"] += 0.5
    elif corridor == "fragile":
        scores["D"] += 0.5
    elif corridor == "permitted":
        scores["C"] += 0.2
        scores["A"] += 0.2

    # Classify regime (mirror existing logic)
    if custody == "marketward" and entropy == "rising" and tension > 6 and corridor == "structurally illegal":
        name = "STARVATION"
        inevitability = "float cannot survive at current depth"
    elif 5 <= tension <= 6 and entropy in ["rising", "flat"] and custody != "marketward":
        name = "COMPRESSION"
        inevitability = "volatility is guaranteed, only timing is unknown"
    elif custody == "marketward" and corridor == "fragile":
        name = "DISTRIBUTION"
        inevitability = "liquidity decays trajectory, relief is temporary"
    elif memory_snapshot.cti_trend_7d == "rising" and custody == "vaultward" and corridor == "structurally illegal":
        name = "ASCENT"
        inevitability = "price is being pulled upward by disappearing float"
    else:
        # Default to COMPRESSION if no match
        name = "COMPRESSION"
        inevitability = "volatility is guaranteed, only timing is unknown"

    # Update regime state
    update_regime_state(name)

    return RegimeSnapshot(
        name=name,
        custody=custody,
        tension=tension,
        entropy=entropy,
        corridor=corridor,
        inevitability=inevitability,
        scores=scores
    )

def update_regime_state(current_regime: str):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().date().isoformat()

    # Load existing
    if REGIME_STATE_PATH.exists():
        try:
            with REGIME_STATE_PATH.open("r", encoding="utf-8") as f:
                state = json.load(f)
        except:
            state = {"history": []}
    else:
        state = {"history": []}

    # Append today's regime
    state["history"].append({"date": today_str, "regime": current_regime})

    # Keep last 30
    state["history"] = state["history"][-30:]

    # Compute streaks, flips, dominant
    history = state["history"]
    if history:
        regimes = [h["regime"] for h in history]
        dominant = max(set(regimes), key=regimes.count)
        current_streak = 0
        for r in reversed(regimes):
            if r == current_regime:
                current_streak += 1
            else:
                break
        flips = sum(1 for i in range(1, len(regimes)) if regimes[i] != regimes[i-1])
        state["dominant_vector"] = dominant
        state["current_streak"] = current_streak
        state["total_flips"] = flips

    # Save
    with REGIME_STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)