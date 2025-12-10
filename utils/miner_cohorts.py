# utils/miner_cohorts.py

from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List
import json
from collections import Counter, defaultdict
from statistics import mean

@dataclass
class MinerCohortTilt:
    date_utc: str
    dominant_pool: str
    dominant_share: float
    tilt_label: str
    narrative: str

def load_window_blocks(block_catalog_path: Path, window_heights: range) -> List[Dict[str, Any]]:
    """
    block_catalog.jsonl contains full history; we care only about blocks in the given height range.
    Assumes each line has at least: height, pool_name, entropy_score, avg_fee_rate_sat_vb.
    """
    blocks = []
    if not block_catalog_path.exists():
        return blocks
    low = window_heights.start
    high = window_heights.stop
    with block_catalog_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            h = int(row.get("height", -1))
            if h < low or h > high:
                continue
            blocks.append(row)
    return blocks

def compute_miner_cohort_tilt(
    date_utc: str,
    block_catalog_path: Path,
    window_heights: range,
) -> MinerCohortTilt | None:
    blocks = load_window_blocks(block_catalog_path, window_heights)
    if not blocks:
        return None

    by_pool: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for b in blocks:
        pool = b.get("pool_name") or b.get("miner") or "UNKNOWN"
        by_pool[pool].append(b)

    total = sum(len(v) for v in by_pool.values())
    if total == 0:
        return None

    shares = {pool: len(v) / total for pool, v in by_pool.items()}
    dominant_pool = max(shares, key=lambda k: shares[k])
    dominant_share = shares[dominant_pool]

    def pool_stats(pool: str) -> Dict[str, float]:
        group = by_pool[pool]
        ent = [float(x.get("entropy_score", 0.0)) for x in group]
        fees = [float(x.get("avg_fee_rate_sat_vb", 0.0)) for x in group]
        return {
            "entropy": mean(ent) if ent else 0.0,
            "fees": mean(fees) if fees else 0.0,
        }

    stats = pool_stats(dominant_pool)
    ent = stats["entropy"]
    fees = stats["fees"]

    # Simple classification:
    # low entropy + low fees + large share → "coil_enforced"
    # high entropy + high fees → "reliever"
    # otherwise → "neutral"
    if dominant_share > 0.35 and ent < 0.4 and fees < 10.0:
        tilt_label = "coil_enforced"
        narrative = (
            f"Today’s coil is enforced primarily by {dominant_pool}: "
            f"low-entropy, low-fee blocks dominating the window."
        )
    elif ent > 0.7 and fees > 15.0:
        tilt_label = "reliever"
        narrative = (
            f"{dominant_pool} is acting as a pressure release: "
            f"high-entropy, high-fee blocks clearing demand."
        )
    else:
        tilt_label = "neutral"
        narrative = (
            f"Miner cohorts are mixed today — {dominant_pool} leads, "
            f"but block structure remains neutral to the coil."
        )

    return MinerCohortTilt(
        date_utc=date_utc,
        dominant_pool=dominant_pool,
        dominant_share=round(dominant_share, 3),
        tilt_label=tilt_label,
        narrative=narrative,
    )

def save_miner_cohort_tilt(
    reports_dir: Path,
    tilt: MinerCohortTilt,
) -> Dict[str, Any]:
    path = reports_dir / "miner_cohort_state.json"
    data = asdict(tilt)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data