# utils/evaluate_outcomes.py

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Any, Tuple

OUTCOME_PATH = Path(__file__).resolve().parent.parent / "reports" / "outcome_history.jsonl"

def load_outcome_history(window_days: int | None = None) -> List[Dict[str, Any]]:
    """
    Load outcome_history.jsonl and optionally filter to last `window_days`.
    Each line is a JSON dict written by the Outcome Engine.
    """
    if not OUTCOME_PATH.exists():
        return []

    rows = []
    try:
        with OUTCOME_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    rows.append(row)
                except json.JSONDecodeError:
                    print(f"[outcome] warning: skipping malformed line: {line[:50]}...")
    except Exception as e:
        print(f"[outcome] error loading {OUTCOME_PATH}: {e}")
        return []

    if window_days is not None:
        # Assume rows have 'date_utc' as YYYY-MM-DD
        # For simplicity, take last N rows (assuming chronological order)
        rows = rows[-window_days:] if len(rows) > window_days else rows

    return rows

def derive_event_flags(
    rows: List[Dict[str, Any]],
    vol_key: str = "realized_vol_72h",
    vol_threshold: float = 0.06,
    regime_break_key: str = "regime_break_72h",
    coil_resolved_key: str = "coil_resolved_72h",
) -> List[Tuple[Dict[str, Any], int]]:
    """
    For each outcome row, derive E_d ∈ {0,1}:
      E_d = 1 if a structural resolution occurred within the horizon:
        - realized_vol_72h >= vol_threshold
        - OR regime_break_72h == 1
        - OR coil_resolved_72h == 1
      else 0.

    Returns list of (row, event_flag).
    """
    result = []
    for row in rows:
        e = 0
        if row.get(vol_key, 0.0) >= vol_threshold:
            e = 1
        elif row.get(regime_break_key, 0) == 1:
            e = 1
        elif row.get(coil_resolved_key, 0) == 1:
            e = 1
        result.append((row, e))
    return result

def fused_pressure_score(row: Dict[str, Any]) -> float:
    """
    Compute a scalar pressure score in [0,1] from CTI, MTI, IRQ, and ETI.

    Assumes row has:
      - cti_raw (0–10)
      - mti (0–1)
      - eti (0–1) or may be missing
      - irq_index (0–1) or may be missing

    Weights are initial guesses; can be tuned later.
    """
    cti_raw = float(row.get("cti_raw", row.get("cti", 0.0)))
    cti_norm = max(0.0, min(1.0, cti_raw / 10.0))

    mti = float(row.get("mti", 0.0))
    mti = max(0.0, min(1.0, mti))

    eti = float(row.get("eti", 0.0))
    eti = max(0.0, min(1.0, eti))

    irq = float(row.get("irq_index", 0.0))
    irq = max(0.0, min(1.0, irq))

    # Initial fusion: CTI + MTI dominance, IRQ/ETI as modifiers
    score = (
        0.35 * cti_norm +
        0.35 * mti +
        0.15 * irq +
        0.15 * eti
    )
    return max(0.0, min(1.0, score))

def implied_probability(score: float) -> float:
    """
    Map fused pressure score in [0,1] to an implied probability p̂ ∈ [0,1].

    Start with a simple linear mapping. We can upgrade to logistic later.
    """
    # modest sharpening: ensure low pressure not overstated
    # p̂ = 0.1 + 0.8 * score  ∈ [0.1, 0.9]
    p_hat = 0.1 + 0.8 * max(0.0, min(1.0, score))
    return max(0.0, min(1.0, p_hat))

def brier_score(p_hats: List[float], events: List[int]) -> float:
    assert len(p_hats) == len(events)
    if not p_hats:
        return float("nan")
    sq = [(p - e) ** 2 for p, e in zip(p_hats, events)]
    return sum(sq) / len(sq)

def reliability_bins(p_hats: List[float], events: List[int], bin_width: float = 0.2):
    """
    Group forecasts into bins in [0,1] of size bin_width.

    Returns list of dicts:
      {
        "low": float,
        "high": float,
        "count": int,
        "avg_p": float,
        "event_rate": float,
      }
    """
    assert len(p_hats) == len(events)
    if not p_hats:
        return []

    bins: Dict[Tuple[float, float], List[Tuple[float, int]]] = defaultdict(list)

    for p, e in zip(p_hats, events):
        # clamp
        p = max(0.0, min(1.0, p))
        idx = int(p // bin_width)
        low = idx * bin_width
        high = min(1.0, low + bin_width)
        bins[(low, high)].append((p, e))

    out = []
    for (low, high) in sorted(bins.keys()):
        vals = bins[(low, high)]
        count = len(vals)
        avg_p = sum(v[0] for v in vals) / count
        event_rate = sum(v[1] for v in vals) / count
        out.append(
            {
                "low": low,
                "high": high,
                "count": count,
                "avg_p": avg_p,
                "event_rate": event_rate,
            }
        )
    return out

def roc_points(scores: List[float], events: List[int]):
    """
    Compute ROC curve points from scores and binary labels.

    Returns list of (fpr, tpr) sorted by threshold descending.
    """
    assert len(scores) == len(events)
    if not scores:
        return []

    # sort by score descending
    paired = sorted(zip(scores, events), key=lambda x: x[0], reverse=True)
    P = sum(e for _, e in paired)  # positives
    N = len(paired) - P            # negatives
    if P == 0 or N == 0:
        return []

    tp = 0
    fp = 0
    prev_score = None
    points = []

    for score, label in paired:
        if prev_score is not None and score != prev_score:
            tpr = tp / P
            fpr = fp / N
            points.append((fpr, tpr))
        if label == 1:
            tp += 1
        else:
            fp += 1
        prev_score = score

    # final point
    tpr = tp / P
    fpr = fp / N
    points.append((fpr, tpr))

    # add origin and (1,1) for completeness
    points = [(0.0, 0.0)] + points + [(1.0, 1.0)]
    return points

def auc_from_roc(points: List[Tuple[float, float]]) -> float:
    """
    Approximate AUC via trapezoidal rule over ROC points.
    """
    if len(points) < 2:
        return float("nan")
    points = sorted(points)  # sort by FPR
    auc = 0.0
    for (x0, y0), (x1, y1) in zip(points[:-1], points[1:]):
        auc += (x1 - x0) * (y0 + y1) / 2.0
    return auc

CALIB_REPORT_PATH = Path(__file__).resolve().parent.parent / "reports" / "calibration_report.md"

def write_calibration_report(
    rows: List[Dict[str, Any]],
    window_days: int,
    brier: float,
    auc: float,
    bins: List[Dict[str, Any]],
    by_band: Dict[str, Dict[str, int]],
):
    CALIB_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    dates = [r.get("date_utc") for r in rows if r.get("date_utc")]
    start = min(dates) if dates else "n/a"
    end = max(dates) if dates else "n/a"

    lines: List[str] = []
    lines.append("# ChainWalk Outcome Calibration Report")
    lines.append("")
    lines.append(f"_Window_: last **{window_days}** days")
    lines.append(f"_Range_: `{start}` → `{end}`")
    lines.append(f"_Samples_: **{len(rows)}**")
    lines.append("")
    lines.append("## 1. Global Metrics")
    lines.append("")
    lines.append(f"- **Brier score**: `{brier:.3f}`")
    lines.append(f"- **ROC AUC**    : `{auc:.3f}`")
    lines.append("")

    # Reliability table
    lines.append("## 2. Reliability by Forecast Bin")
    lines.append("")
    if not bins:
        lines.append("_No bins available (insufficient data)._")
    else:
        lines.append("| Bin (p̂) | Count | Avg p̂ | Event rate |")
        lines.append("|---------|-------|--------|------------|")
        for b in bins:
            low = b["low"]
            high = b["high"]
            count = b["count"]
            avg_p = b["avg_p"]
            er = b["event_rate"]
            lines.append(
                f"| {low:.1f}–{high:.1f} | {count} | {avg_p:.3f} | {er:.3f} |"
            )
    lines.append("")

    # Band table
    lines.append("## 3. Irreversibility Band Outcomes")
    lines.append("")
    if not by_band:
        lines.append("_No IRQ band data available._")
    else:
        lines.append("| IRQ band | Days | Event frequency |")
        lines.append("|----------|------|-----------------|")
        for band, stats in by_band.items():
            c = stats["count"]
            e = stats["events"]
            freq = e / c if c else 0.0
            lines.append(f"| {band} | {c} | {freq:.3f} |")
    lines.append("")

    lines.append("## 4. Notes")
    lines.append("")
    lines.append("- Brier score closer to 0 indicates better calibration and sharpness.")
    lines.append("- ROC AUC > 0.5 indicates discriminatory power; > 0.7 is strong.")
    lines.append("- IRQ band frequencies help validate whether 🟧/🟥/⬛ language is honest.")
    lines.append("")

    CALIB_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"[outcome] wrote calibration report -> {CALIB_REPORT_PATH}")

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-days", type=int, default=90)
    args = parser.parse_args(argv)

    rows = load_outcome_history(window_days=args.window_days)
    if not rows:
        print(f"[outcome] evaluation (last {args.window_days}d): no records")
        return

    # 1) derive events
    rows_with_event = derive_event_flags(rows)
    events = [e for _, e in rows_with_event]

    # 2) compute scores + implied probabilities
    scores = [fused_pressure_score(r) for (r, _) in rows_with_event]
    p_hats = [implied_probability(s) for s in scores]

    # 3) aggregate metrics
    brier = brier_score(p_hats, events)
    bins = reliability_bins(p_hats, events)
    roc_pts = roc_points(scores, events)
    auc = auc_from_roc(roc_pts)

    # 4) band-wise stats (by IRQ band)
    by_band = {}
    for (row, e) in rows_with_event:
        band = row.get("irq_band", "UNKNOWN")
        if band not in by_band:
            by_band[band] = {"count": 0, "events": 0}
        by_band[band]["count"] += 1
        by_band[band]["events"] += e

    # 5) write calibration_report.md
    write_calibration_report(
        rows=rows,
        window_days=args.window_days,
        brier=brier,
        auc=auc,
        bins=bins,
        by_band=by_band,
    )

    # 6) write calibration_summary.json
    import json
    from datetime import datetime
    summary = {
        "generated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": args.window_days,
        "sample_count": len(rows),
        "brier": brier if not math.isnan(brier) else None,
        "auc": auc if not math.isnan(auc) else None,
    }
    summary_path = CALIB_REPORT_PATH.parent / "calibration_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"[outcome] wrote calibration summary -> {summary_path}")

    # 7) console summary
    print(f"[outcome] evaluation (last {args.window_days}d):")
    print(f"  count: {len(rows)}")
    print(f"  Brier: {brier:.3f}")
    print(f"  AUC  : {auc:.3f}")

if __name__ == "__main__":
    main()