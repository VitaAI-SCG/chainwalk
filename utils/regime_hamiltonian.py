from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import json
from pathlib import Path
from datetime import datetime

REGIME_BASIS = ["STARVATION", "COMPRESSION", "DISTRIBUTION", "ASCENT"]
REGIME_TO_INDEX = {name: i for i, name in enumerate(REGIME_BASIS)}
INDEX_TO_REGIME = {i: name for i, name in enumerate(REGIME_BASIS)}

@dataclass
class RegimeHamiltonianState:
    basis: List[str]
    transition_matrix: List[List[float]]
    horizon_days: int
    p_today: List[float]
    p_horizon: List[float]
    last_date: str
    sample_size: int

def load_daily_regime_sequence(regime_state_path: str = "reports/regime_state.json") -> List[Dict]:
    """
    Return a list of daily regime snapshots, most recent last.
    Each item: {"date": "YYYY-MM-DD", "regime": "COMPRESSION"}
    """
    path = Path(regime_state_path)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    history = data.get("history", [])
    daily_map = {}

    for entry in history:
        ts = entry.get("ts", "")
        if not ts:
            continue
        date_str = ts.split("T")[0]  # YYYY-MM-DD
        regime = entry.get("regime", "")
        if regime:
            daily_map[date_str] = regime  # Last entry per day

    # Sort chronologically
    daily_sequence = [{"date": date, "regime": regime} for date, regime in sorted(daily_map.items())]
    return daily_sequence

def estimate_transition_matrix(daily_sequence: List[Dict]) -> Tuple[List[List[float]], int]:
    """
    Estimate 4x4 transition matrix with Laplace smoothing.
    """
    if len(daily_sequence) < 2:
        # Fallback near-identity
        T = [[0.85 if i == j else 0.05 for j in range(4)] for i in range(4)]
        return T, 0

    # Laplace smoothing: start counts at 1.0
    counts = [[1.0 for _ in range(4)] for _ in range(4)]
    transitions = 0

    for i in range(len(daily_sequence) - 1):
        prev_regime = daily_sequence[i]["regime"]
        curr_regime = daily_sequence[i + 1]["regime"]
        if prev_regime in REGIME_TO_INDEX and curr_regime in REGIME_TO_INDEX:
            prev_idx = REGIME_TO_INDEX[prev_regime]
            curr_idx = REGIME_TO_INDEX[curr_regime]
            counts[prev_idx][curr_idx] += 1.0
            transitions += 1

    # Normalize rows
    T = []
    for row in counts:
        row_sum = sum(row)
        if row_sum > 0:
            T.append([val / row_sum for val in row])
        else:
            T.append([0.25 for _ in range(4)])  # Uniform if zero

    return T, transitions

def classify_horizon(p_vec: List[float], threshold: float = 0.08) -> Tuple[str, Optional[str]]:
    """
    p_vec: list of regime probabilities [C, A, S, D] (floats 0-1)
    threshold: minimum spread required to call directional bias
    returns: ("coil", None) or ("biased", dominant_regime)
    """
    p_max = max(p_vec)
    p_min = min(p_vec)
    spread = p_max - p_min

    if spread < threshold:
        return ("coil", None)

    idx = p_vec.index(p_max)
    dominant = REGIME_BASIS[idx]
    return ("biased", dominant)

def propagate_distribution(p0: List[float], T: List[List[float]], horizon_days: int = 7) -> List[float]:
    """
    Compute p_horizon = p0 @ T^horizon_days
    """
    p = p0[:]
    for _ in range(horizon_days):
        p_next = [0.0] * 4
        for i in range(4):
            for j in range(4):
                p_next[j] += p[i] * T[i][j]
        p = p_next
    return p

def compute_regime_horizon(
    horizon_days: int = 7,
    regime_state_path: str = "reports/regime_state.json",
    wavefunction_path: str = "reports/regime_wavefunction.jsonl",
    out_state_path: str = "reports/regime_hamiltonian_state.json",
) -> Dict:
    """
    Main entrypoint.
    """
    # Load daily sequence
    daily_sequence = load_daily_regime_sequence(regime_state_path)

    # Estimate T
    T, sample_size = estimate_transition_matrix(daily_sequence)

    # Determine p_today
    p_today = [0.0] * 4
    wave_path = Path(wavefunction_path)
    if wave_path.exists():
        try:
            with wave_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    last_line = lines[-1].strip()
                    data = json.loads(last_line)
                    probs = data.get("regime_probabilities", {})
                    p_today = [probs.get("S", 0.0), probs.get("C", 0.0), probs.get("D", 0.0), probs.get("A", 0.0)]
        except:
            pass

    # Fallback to one-hot if all zero
    if all(p == 0.0 for p in p_today):
        if daily_sequence:
            last_regime = daily_sequence[-1]["regime"]
            if last_regime in REGIME_TO_INDEX:
                idx = REGIME_TO_INDEX[last_regime]
                p_today[idx] = 1.0

    # Propagate
    p_horizon = propagate_distribution(p_today, T, horizon_days)

    # Classify horizon
    horizon_mode, dominant_regime = classify_horizon(p_horizon)

    # Last date
    last_date = datetime.now().date().isoformat()

    # Compose state
    state = RegimeHamiltonianState(
        basis=REGIME_BASIS,
        transition_matrix=T,
        horizon_days=horizon_days,
        p_today=p_today,
        p_horizon=p_horizon,
        last_date=last_date,
        sample_size=sample_size
    )

    # Add horizon classification to state (extend dataclass if needed, or return dict)
    # For now, return dict with extra fields
    state_dict = {
        "basis": state.basis,
        "transition_matrix": state.transition_matrix,
        "horizon_days": state.horizon_days,
        "p_today": state.p_today,
        "p_horizon": state.p_horizon,
        "last_date": state.last_date,
        "sample_size": state.sample_size,
        "horizon_mode": horizon_mode,
        "dominant_regime": dominant_regime
    }

    # Save to JSON
    with Path(out_state_path).open("w", encoding="utf-8") as f:
        json.dump(state_dict, f, indent=2)

    return state_dict