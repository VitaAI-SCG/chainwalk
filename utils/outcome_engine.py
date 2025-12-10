# utils/outcome_engine.py

from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal, Dict, Any, List, Optional
import json
import math
from statistics import mean

OutcomeDirection = Literal["up", "down", "flat"]
VolBucket = Literal["low", "medium", "high"]

@dataclass
class OutcomeSnapshot:
    date_utc: str
    # Inputs at decision time
    regime_label: str
    cti: float
    custody_direction: str
    miner_threshold_band: str
    miner_threshold_index: float
    # Price info
    price_usd: float
    prev_price_usd: Optional[float]
    realized_return_1d: Optional[float]
    realized_abs_return_1d: Optional[float]
    realized_direction_1d: Optional[OutcomeDirection]
    vol_bucket_1d: Optional[VolBucket]

    # Convenience flags for later analysis
    predicted_high_vol: bool  # e.g., COMPRESSION/STARVATION & CTI above threshold
    oracle_input_hash: Optional[str] = None
    # Later we can add directional probabilistic forecasts.

def _infer_direction(ret: float, eps: float = 0.002) -> OutcomeDirection:
    if ret > eps:
        return "up"
    if ret < -eps:
        return "down"
    return "flat"

def _bucket_abs_return(abs_ret: float) -> VolBucket:
    if abs_ret < 0.01:
        return "low"
    if abs_ret < 0.03:
        return "medium"
    return "high"

def load_outcome_history(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def append_outcome_snapshot(
    reports_dir: Path,
    daily_state: Dict[str, Any],
    miner_threshold_state: Dict[str, Any],
) -> None:
    """
    Append a new OutcomeSnapshot row for today.
    Realized 1d metrics are computed for *yesterday* when we have prev_price_usd.
    """
    history_path = reports_dir / "outcome_history.jsonl"

    history = load_outcome_history(history_path)
    prev = history[-1] if history else None

    date_utc = daily_state["date_utc"]
    regime_label = daily_state.get("regime_label", "UNKNOWN")
    cti = float(daily_state.get("chain_tension_index", 0.0))
    custody_direction = daily_state.get("custody_direction", "UNKNOWN")

    price_usd = float(daily_state.get("price_usd", 0.0))

    mt_band = miner_threshold_state.get("band", "none")
    mt_index = float(miner_threshold_state.get("index", 0.0))

    oracle_input_hash = daily_state.get("oracle_input_hash")

    prev_price = float(prev["price_usd"]) if prev and "price_usd" in prev else None

    realized_return_1d = None
    realized_abs_return_1d = None
    realized_direction_1d = None
    vol_bucket_1d = None

    if prev_price and prev_price > 0:
        realized_return_1d = (price_usd / prev_price) - 1.0
        realized_abs_return_1d = abs(realized_return_1d)
        realized_direction_1d = _infer_direction(realized_return_1d)
        vol_bucket_1d = _bucket_abs_return(realized_abs_return_1d)

    # Simple "predicted high vol" rule:
    predicted_high_vol = (
        regime_label in {"COMPRESSION", "STARVATION"}
        and cti >= 5.0
    )

    snap = OutcomeSnapshot(
        date_utc=date_utc,
        regime_label=regime_label,
        cti=cti,
        custody_direction=custody_direction,
        miner_threshold_band=mt_band,
        miner_threshold_index=mt_index,
        price_usd=price_usd,
        prev_price_usd=prev_price,
        realized_return_1d=realized_return_1d,
        realized_abs_return_1d=realized_abs_return_1d,
        realized_direction_1d=realized_direction_1d,
        vol_bucket_1d=vol_bucket_1d,
        predicted_high_vol=predicted_high_vol,
        oracle_input_hash=oracle_input_hash,
    )

    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(snap)) + "\n")


def evaluate_outcomes(
    reports_dir: Path,
    window_days: int = 60,
) -> Dict[str, Any]:
    """
    Read outcome_history.jsonl and compute simple calibration metrics
    for the last N days: hit rate and a rough Brier-like score on high-vol prediction.
    """
    history_path = reports_dir / "outcome_history.jsonl"
    rows = load_outcome_history(history_path)
    if not rows:
        return {"window_days": window_days, "count": 0}

    recent = rows[-window_days:]

    hits = []
    brier_terms = []

    for row in recent:
        pred = row.get("predicted_high_vol", False)
        bucket = row.get("vol_bucket_1d")
        if bucket is None:
            continue
        # treat medium/high as "vol happened"
        actual = bucket in {"medium", "high"}
        hits.append(int(pred == actual))
        # Brier with p=1 if pred True else 0
        p = 1.0 if pred else 0.0
        o = 1.0 if actual else 0.0
        brier_terms.append((p - o) ** 2)

    metrics = {
        "window_days": window_days,
        "count": len(hits),
    }
    if hits:
        metrics["hit_rate_high_vol"] = mean(hits)
    if brier_terms:
        metrics["brier_high_vol"] = mean(brier_terms)

    return metrics

def get_calibration_summary(window_days: int = 90) -> Dict[str, Any]:
    """
    Returns a dict:
    {
      "brier": float or None,
      "auc": float or None,
      "samples": int
    }
    """
    from collections import defaultdict
    from typing import Tuple

    history_path = Path(__file__).resolve().parent.parent / "reports" / "outcome_history.jsonl"
    rows = load_outcome_history(history_path)
    if not rows:
        return {"brier": None, "auc": None, "samples": 0}

    if window_days:
        rows = rows[-window_days:] if len(rows) > window_days else rows

    # Derive events: high vol or regime break
    events = []
    scores = []
    for row in rows:
        # Event: high vol
        vol_bucket = row.get("vol_bucket_1d")
        e = 1 if vol_bucket in {"medium", "high"} else 0
        events.append(e)

        # Score: predicted_high_vol as probability
        pred = row.get("predicted_high_vol", False)
        score = 1.0 if pred else 0.0
        scores.append(score)

    if not events or not scores:
        return {"brier": None, "auc": None, "samples": len(rows)}

    # Brier
    brier = sum((p - e) ** 2 for p, e in zip(scores, events)) / len(events)

    # ROC AUC
    paired = sorted(zip(scores, events), key=lambda x: x[0], reverse=True)
    P = sum(e for _, e in paired)
    N = len(paired) - P
    if P == 0 or N == 0:
        auc = float("nan")
    else:
        tp = fp = 0
        auc = 0.0
        prev_score = None
        for score, label in paired:
            if prev_score is not None and score != prev_score:
                auc += (fp / N) * (tp / P - (tp - (1 if label == 1 else 0)) / P)
            if label == 1:
                tp += 1
            else:
                fp += 1
            prev_score = score
        auc = 1 - auc  # Adjust for descending order

    return {
        "brier": brier if not math.isnan(brier) else None,
        "auc": auc if not math.isnan(auc) else None,
        "samples": len(rows),
    }