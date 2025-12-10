# utils/alert_rail.py

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Literal, Dict, Any
import json
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"
DAILY_STATE = REPORTS_DIR / "chainwalk_daily_state.json"
ALERT_STATE = REPORTS_DIR / "alert_state.json"
ALERT_EVENTS = REPORTS_DIR / "alert_events.jsonl"
SPINE_HISTORY = REPO_ROOT / "chainwalk_spine_history.log"

IRQBand = Literal["reversible", "primed", "irreversible", "floor"]
REIBand = Literal["dormant", "charged", "imminent", "triggered"]
AlertKind = Literal["IRQ", "REI"]

@dataclass
class AlertSnapshot:
    kind: AlertKind
    band: str
    index: float
    date_utc: str
    regime: str
    cti: float
    custody: str
    spine: Optional[str] = None

def load_daily_state() -> Optional[Dict[str, Any]]:
    if not DAILY_STATE.exists():
        return None
    try:
        with DAILY_STATE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def load_alert_state() -> Dict[str, Any]:
    """
    Return {'last_irq_band': str | None, 'last_rei_band': str | None}.
    If file missing, default both to None.
    """
    if not ALERT_STATE.exists():
        return {"last_irq_band": None, "last_rei_band": None}
    try:
        with ALERT_STATE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "last_irq_band": data.get("last_irq_band"),
                "last_rei_band": data.get("last_rei_band"),
            }
    except Exception:
        return {"last_irq_band": None, "last_rei_band": None}

def load_latest_spine() -> Optional[str]:
    if not SPINE_HISTORY.exists():
        return None
    lines = [ln.strip() for ln in SPINE_HISTORY.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return lines[-1] if lines else None

def evaluate_alerts() -> List[AlertSnapshot]:
    """
    Decide whether today's state crosses an IRQ/REI alert boundary
    for the first time.
    """
    daily = load_daily_state()
    if not daily:
        return []

    regime_name = daily.get("regime_label", "")
    if regime_name not in {"COMPRESSION", "STARVATION"}:
        return []  # only pressure regimes

    cti = daily.get("chain_tension_index", 0.0)
    custody_dir = daily.get("custody_direction", "")
    custody_streak = daily.get("custody_streak", 0)
    custody = f"{custody_dir}({custody_streak})"

    irq_data = daily.get("irreversibility", {})
    irq_band = irq_data.get("band", "")
    rei_data = daily.get("resolution", {})
    rei_band = rei_data.get("band", "")

    alert_state = load_alert_state()
    last_irq_band = alert_state.get("last_irq_band")
    last_rei_band = alert_state.get("last_rei_band")

    alerts = []

    # IRQ alert
    if irq_band == "irreversible" and last_irq_band != "irreversible":
        alerts.append(AlertSnapshot(
            kind="IRQ",
            band=irq_band,
            index=irq_data.get("index", 0.0),
            date_utc=daily.get("date_utc", ""),
            regime=regime_name,
            cti=cti,
            custody=custody,
            spine=load_latest_spine(),
        ))

    # REI alert
    if rei_band in {"imminent", "triggered"} and last_rei_band not in {"imminent", "triggered"}:
        alerts.append(AlertSnapshot(
            kind="REI",
            band=rei_band,
            index=rei_data.get("index", 0.0),
            date_utc=daily.get("date_utc", ""),
            regime=regime_name,
            cti=cti,
            custody=custody,
            spine=load_latest_spine(),
        ))

    return alerts

def persist_alerts(alerts: List[AlertSnapshot], new_irq_band: str, new_rei_band: str) -> None:
    """
    Append alerts to alert_events.jsonl, update alert_state.json,
    and write alert_latest.md for the last alert.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Append to events
    with ALERT_EVENTS.open("a", encoding="utf-8") as f:
        for alert in alerts:
            event = {
                "kind": alert.kind,
                "band": alert.band,
                "index": alert.index,
                "date_utc": alert.date_utc,
                "regime": alert.regime,
                "cti": alert.cti,
                "custody": alert.custody,
                "spine": alert.spine,
            }
            f.write(json.dumps(event) + "\n")

    # Update state
    state = {
        "last_irq_band": new_irq_band,
        "last_rei_band": new_rei_band,
        "updated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with ALERT_STATE.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    # Write latest alert
    if alerts:
        last_alert = alerts[-1]
        lines = []
        lines.append(f"# ChainWalk Alert · {last_alert.date_utc}")
        lines.append("")
        lines.append(f"Kind: {last_alert.kind}")
        lines.append(f"Regime: {last_alert.regime}")
        lines.append(f"CTI: {last_alert.cti} / 10")
        lines.append(f"Custody: {last_alert.custody}")
        lines.append("")

        if last_alert.kind == "IRQ":
            lines.append(f"Irreversibility (IRQ): 🟥 irreversible — optionality has collapsed into a single incentive path (IRQ {last_alert.index:.2f}).")
            lines.append("")
            lines.append("This does not guarantee direction in the next block,")
            lines.append("but it does mean the system can no longer unwind cleanly")
            lines.append("without external shock.")
        else:  # REI
            lines.append(f"Resolution Field (REI): 🔻 {last_alert.band} — the coil has moved from charged to resolution-driven (REI {last_alert.index:.2f}).")
            lines.append("")
            lines.append("This marks the first time the system itself prefers settlement")
            lines.append("over further compression.")

        lines.append("")
        lines.append("Latest spine:")
        lines.append(f"`{last_alert.spine or 'N/A'}`")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("**Constraint Stack · Legend**")
        lines.append("")
        lines.append("CTI — chain tension (how tightly Bitcoin’s incentive coil is compressed)  ")
        lines.append("MTI — miner threshold (how much stress producers can absorb before leaning on price)  ")
        lines.append("IRQ — irreversibility (how much optionality has been eliminated; unwind no longer benign)  ")
        lines.append("REI — resolution field (how close the system is to forcing a regime outcome)")

        latest_path = REPORTS_DIR / "alert_latest.md"
        latest_path.write_text("\n".join(lines), encoding="utf-8")