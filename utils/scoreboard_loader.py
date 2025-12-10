import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"

def load_scoreboard_state():
    regime_state_path = REPORTS_DIR / "regime_state.json"
    memory_state_path = REPORTS_DIR / "memory_of_price_state.json"

    date = datetime.now().date().isoformat()

    # Default values
    state = {
        "date": date,
        "regime": "COMPRESSION",
        "regime_streak_days": 0,
        "regime_flips_this_month": 0,
        "cti": 5.5,
        "cti_min": 0.0,
        "cti_max": 10.0,
        "custody_vector": "MARKETWARD",
        "custody_streak": 0,
        "entropy_gradient": "FLAT",
        "legality_floor": "PERMITTED",
        "outcome": "VOLATILITY GUARANTEED — TIMING IRRELEVANT",
        "tagline": "Price does not lead the chain. The chain leads price."
    }

    # Load regime_state.json
    if regime_state_path.exists():
        try:
            with regime_state_path.open("r", encoding="utf-8") as f:
                r_state = json.load(f)
            if r_state.get("history"):
                latest_regime = r_state["history"][-1]["regime"]
                state["regime"] = latest_regime
            state["regime_streak_days"] = r_state.get("current_streak", 0)
            state["regime_flips_this_month"] = r_state.get("total_flips", 0)
        except Exception as e:
            print(f"[scoreboard_loader] Error loading regime_state: {e}")

    # Load memory_of_price_state.json
    if memory_state_path.exists():
        try:
            with memory_state_path.open("r", encoding="utf-8") as f:
                m_state = json.load(f)
            state["cti"] = m_state.get("cti_last", 5.5)
            state["custody_vector"] = m_state.get("custody_direction", "MARKETWARD").upper()
            state["custody_streak"] = m_state.get("custody_streak", 0)
            state["entropy_gradient"] = m_state.get("entropy_trend_7d", "FLAT").upper()
            # For legality_floor, placeholder
            state["legality_floor"] = "PERMITTED"
        except Exception as e:
            print(f"[scoreboard_loader] Error loading memory_state: {e}")

    # Set outcome based on regime
    regime = state["regime"].upper()
    if regime == "COMPRESSION":
        state["outcome_line"] = "VOLATILITY GUARANTEED - TIMING IRRELEVANT"
    elif regime == "STARVATION":
        state["outcome_line"] = "FLOAT DYING"
    elif regime == "ASCENT":
        state["outcome_line"] = "ASCENT ENFORCED"
    elif regime == "DISTRIBUTION":
        state["outcome_line"] = "RELIEF TEMPORARY"
    else:
        state["outcome_line"] = "VOLATILITY GUARANTEED - TIMING IRRELEVANT"

    # Strip unicode for Windows compatibility
    for key, value in state.items():
        if isinstance(value, str):
            state[key] = value.encode('ascii', 'ignore').decode('ascii')

    return state