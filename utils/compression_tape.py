# utils/compression_tape.py

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[1]
SPINE_HISTORY_PATH = REPO_ROOT / "chainwalk_spine_history.log"
REPORTS_DIR = REPO_ROOT / "reports"

@dataclass
class SpineSnapshot:
    date_utc: str
    regime: str              # e.g. "COMPRESSION,MID"
    cti: float               # numeric
    custody: str             # e.g. "marketward(5)"
    intent_clock: str        # e.g. "0d"
    hashrate: str            # e.g. "rising,calm,0.5"
    threshold: str           # e.g. "strained,0.63"
    epoch: str               # e.g. "relaxed,0.00"
    cohort: str              # e.g. "coil_enforced,UNKNOWN"
    irq: str                 # e.g. "primed,0.46"
    rei: str                 # e.g. "charged,0.43"
    raw: str                 # full spine line

def load_spine_history(path: Path = SPINE_HISTORY_PATH) -> List[SpineSnapshot]:
    """
    Parse chainwalk_spine_history.log into SpineSnapshot objects.

    Each line looks like:
    CWSPINE v0.1 | 2025-12-09 | R=COMPRESSION,MID | CTI=5.3 | ... | IRQ=primed,0.46 | REI=charged,0.43
    """
    snapshots = []
    if not path.exists():
        return snapshots

    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or not line.startswith("CWSPINE"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 3:
                    continue
                date_utc = parts[1]
                fields = {}
                for part in parts[2:]:
                    if "=" in part:
                        key, value = part.split("=", 1)
                        fields[key] = value

                try:
                    snapshot = SpineSnapshot(
                        date_utc=date_utc,
                        regime=fields.get("R", ""),
                        cti=float(fields.get("CTI", "0")),
                        custody=fields.get("CUST", ""),
                        intent_clock=fields.get("IC", ""),
                        hashrate=fields.get("HR", ""),
                        threshold=fields.get("TH", ""),
                        epoch=fields.get("EP", ""),
                        cohort=fields.get("MC", ""),
                        irq=fields.get("IRQ", ""),
                        rei=fields.get("REI", ""),
                        raw=line,
                    )
                    snapshots.append(snapshot)
                except ValueError:
                    continue  # skip malformed
    except Exception as e:
        print(f"[compression_tape] error loading spine history: {e}")

    return snapshots

def select_recent_compression(
    snapshots: List[SpineSnapshot],
    days: int = 7
) -> List[SpineSnapshot]:
    """
    Return snapshots for the last `days` distinct dates where regime starts with 'COMPRESSION'.
    Sorted ascending by date_utc.
    """
    # Filter to COMPRESSION
    compression_snaps = [s for s in snapshots if s.regime.startswith("COMPRESSION")]

    # Get unique dates, latest first
    seen_dates = set()
    recent = []
    for snap in reversed(compression_snaps):  # latest first
        if snap.date_utc not in seen_dates:
            seen_dates.add(snap.date_utc)
            recent.append(snap)
            if len(recent) >= days:
                break

    # Reverse to oldest -> newest
    recent.reverse()
    return recent

def write_compression_tape(
    selected: List[SpineSnapshot],
    out_path: Optional[Path] = None
) -> Path:
    """
    Render a thread-ready Markdown 'compression tape' from a sequence of SpineSnapshots.

    Returns the path of the file written.
    """
    if not selected:
        raise ValueError("No snapshots to write")

    end_date = selected[-1].date_utc
    n = len(selected)

    if out_path is None:
        out_path = REPORTS_DIR / f"compression_tape_{end_date}.md"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"# ChainWalk Compression Tape · {end_date}")
    lines.append("")
    lines.append(f"Window: last {n} days in COMPRESSION")
    lines.append("Constraint Stack: CTI, MTI, IRQ, REI")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, snap in enumerate(selected, 1):
        lines.append(f"## Day {i} · {snap.date_utc}")
        lines.append("")
        lines.append(f"Spine: `{snap.raw}`")
        lines.append("")
        lines.append(f"- Regime: {snap.regime}")
        lines.append(f"- CTI (Chain Tension Index): {snap.cti} / 10")
        lines.append(f"- Custody: {snap.custody}")
        lines.append(f"- Miner Threshold (MTI): {snap.threshold}")
        lines.append(f"- Irreversibility (IRQ): {snap.irq}")
        lines.append(f"- Resolution Field (REI): {snap.rei}")
        lines.append(f"- Epoch Tension (ETI): {snap.epoch}")
        lines.append(f"- Miner Cohort: {snap.cohort}")
        lines.append("")
        lines.append("**Translation:**  ")
        lines.append("TODO: human summary (to be generated by future LLM pass).")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Constraint Stack Legend
    lines.append("### Constraint Stack · Legend")
    lines.append("")
    lines.append("CTI — chain tension (how tightly Bitcoin’s incentive coil is compressed)  ")
    lines.append("MTI — miner threshold (how much stress producers can absorb before leaning on price)  ")
    lines.append("IRQ — irreversibility (how much optionality has been eliminated; unwind no longer benign)  ")
    lines.append("REI — resolution field (how close the system is to forcing a regime outcome)")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path

def main(days: int = 7) -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    snaps = load_spine_history()
    selected = select_recent_compression(snaps, days=days)
    if not selected:
        print("[compression_tape] no COMPRESSION days found in history; nothing to do.")
        return
    out_path = write_compression_tape(selected)
    latest_path = REPORTS_DIR / "compression_tape_latest.md"
    latest_path.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[compression_tape] wrote tape -> {out_path}")
    print(f"[compression_tape] updated latest -> {latest_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    main(days=args.days)