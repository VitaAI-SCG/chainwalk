# utils/apex_deck.py

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Sequence


@dataclass
class BlockSummary:
    height: int
    miner: str
    entropy_delta: float
    custody_direction: str
    total_btc_in: Optional[float] = None
    total_btc_out: Optional[float] = None


def _safe_get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    return d.get(key, default)


def _load_last_wavefunction(path: Path) -> Dict[str, Any]:
    """
    Load the last line from regime_wavefunction.jsonl.
    Returns {} on any error.
    """
    try:
        if not path.exists():
            return {}
        last_line = None
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last_line = line
        if not last_line:
            return {}
        return json.loads(last_line)
    except Exception:
        return {}


def _resolve_wavefunction_dominant(wave: Dict[str, Any], regime_state: Dict[str, Any]) -> str:
    """
    Resolve dominant state with priority:
    1. dominant_state
    2. dominant
    3. state
    4. regime_state["dominant_vector"]
    Fallback: UNKNOWN
    """
    for key in ["dominant_state", "dominant", "state"]:
        if key in wave and wave[key]:
            return str(wave[key])
    if "dominant_vector" in regime_state:
        return str(regime_state["dominant_vector"])
    return "UNKNOWN"


def render_sovereign_oracle_section(daily_state: Dict[str, Any]) -> List[str]:
    oih = daily_state.get("oracle_input_hash")
    short_oih = oih[-8:] if isinstance(oih, str) and len(oih) >= 8 else "N/A"

    lines = []
    lines.append("-------------------------------------")
    lines.append("4.11) SOVEREIGN ORACLE")
    lines.append("-------------------------------------")
    lines.append("ChainWalk is a measurement-only oracle.")
    lines.append("Its inputs are protocol and incentive fields — not price.")
    lines.append(f"Oracle Input Fingerprint: {short_oih}")
    lines.append("Price is used only later to grade honesty, not to shape today's view.")
    lines.append("")
    return lines


def _resolve_wavefunction_expectation(wave: Dict[str, Any]) -> float:
    """
    Resolve expectation bias with priority:
    1. expectation
    2. bias
    3. exp
    Fallback: 0.0
    """
    for key in ["expectation", "bias", "exp"]:
        if key in wave:
            try:
                return float(wave[key])
            except (ValueError, TypeError):
                continue
    return 0.0


Event = Dict[str, Any]


def _load_entropy_events(path: Path) -> Sequence[Event]:
    events: list[Event] = []
    if not path.exists():
        return events
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    return events


def select_block_of_day(
    events: Sequence[Event],
    window_min_height: int,
    window_max_height: int,
) -> Optional[Event]:
    """
    Choose a Block of the Day strictly from the 24h window.

    Priority:
      1. Highest 'master_score' within window, if present.
      2. Fallback: highest 'entropy_delta' within window.
      3. If still nothing, use the *latest* block in the window.
    """
    # restrict to window
    window_events = [
        e for e in events
        if window_min_height <= int(e.get("height", 0)) <= window_max_height
    ]

    if not window_events:
        # No entropy data in window, pick a quiet block from the window
        return {
            "height": window_max_height,
            "pool": "UNKNOWN",
            "custody_action": "quiet",
            "entropy_delta": 0.0,
        }

    def score_fn(e: Event) -> float:
        if "master_score" in e:
            return float(e["master_score"])
        # fallback: entropy + small bump for polyphony / channels
        h = float(e.get("entropy_delta", 0.0))
        poly = float(e.get("poly_score", 0.0))
        return h + 0.1 * poly

    # sort by score descending, height desc as tiebreaker
    window_events.sort(
        key=lambda e: (score_fn(e), int(e.get("height", 0))),
        reverse=True,
    )
    return window_events[0]


def _select_block_of_day(
    block_catalog_path: Path,
    entropy_events_path: Path,
) -> BlockSummary:
    """
    Imperative 'Block of the Day' selector.

    Always returns a BlockSummary, never None.

    Selection priority:
    1. Highest |entropy_delta|
    2. If tie → largest largest_tx_btc (as proxy for miner subsidy change)
    3. If still flat → earliest block in scan window
    4. If no entropy at all → pick any valid block and label as quiet
    """
    candidates = []

    if entropy_events_path.exists():
        try:
            with entropy_events_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    evt = json.loads(line)
                    height = int(evt.get("height", 0))
                    if height > 0:
                        candidates.append(evt)
        except Exception:
            pass

    if not candidates:
        # No entropy data, pick any block from catalog if exists
        if block_catalog_path.exists():
            try:
                with block_catalog_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        blk = json.loads(line)
                        height = int(blk.get("height", 0))
                        if height > 0:
                            return BlockSummary(
                                height=height,
                                miner=blk.get("miner", "UNKNOWN"),
                                entropy_delta=0.0,
                                custody_direction="quiet",
                                total_btc_in=blk.get("total_btc_in"),
                                total_btc_out=blk.get("total_btc_out"),
                            )
            except Exception:
                pass
        # Ultimate fallback
        return BlockSummary(
            height=0,
            miner="UNKNOWN",
            entropy_delta=0.0,
            custody_direction="quiet",
            total_btc_in=None,
            total_btc_out=None,
        )

    # Sort by priority
    candidates.sort(key=lambda evt: (
        -abs(float(evt.get("entropy_delta", 0.0))),  # highest entropy first
        -float(evt.get("largest_tx_btc", 0.0)),     # then largest tx
        int(evt.get("height", 999999999))          # then earliest height
    ))

    best_event = candidates[0]

    # Enrich from block catalog
    miner = "UNKNOWN"
    total_in = None
    total_out = None
    height = int(best_event.get("height", 0))
    custody_direction = best_event.get("custody_direction", "unknown")

    try:
        if block_catalog_path.exists() and height:
            with block_catalog_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    blk = json.loads(line)
                    if int(blk.get("height", -1)) == height:
                        miner = blk.get("miner", miner)
                        total_in = blk.get("total_btc_in", None)
                        total_out = blk.get("total_btc_out", None)
                        break
    except Exception:
        pass

    return BlockSummary(
        height=height,
        miner=miner,
        entropy_delta=float(best_event.get("entropy_delta", 0.0)),
        custody_direction=custody_direction,
        total_btc_in=total_in,
        total_btc_out=total_out,
    )


def _format_block_section(bod_event: Optional[Event], window_min_height: int, window_max_height: int) -> str:
    lines: List[str] = []
    lines.append("-------------------------------------")
    lines.append("5) BLOCK OF THE DAY")
    lines.append("-------------------------------------")

    if bod_event is None:
        lines.append("No qualified block inside the 24h window.")
        lines.append(f"Window: {window_min_height}–{window_max_height}")
    else:
        h = int(bod_event.get("height", 0))
        miner = bod_event.get("pool", "UNKNOWN")
        custody_action = bod_event.get("custody_action", "quiet")
        ent_delta = float(bod_event.get("entropy_delta", 0.0))

        lines.append(f"Height: {h}")
        lines.append(f"Miner: {miner}")
        lines.append(f"Custody Action: {custody_action}")
        lines.append(f"Entropy Δ: {ent_delta:.3f}")

        # Optional soft narrative
        if custody_action == "quiet":
            lines.append("A quiet block inside a tightening coil — nothing escapes, nothing leaks.")

    lines.append("")
    return "\n".join(lines)


def describe_miner_cohort(tilt: str, dominant_pool: str) -> str:
    tilt = (tilt or "neutral").lower()
    pool = (dominant_pool or "UNKNOWN").upper()

    if tilt == "coil_enforced":
        if pool == "UNKNOWN":
            return (
                "Miner Cohort: coil enforced by a distributed set of pools — no single reliever emerged today."
            )
        else:
            return (
                f"Miner Cohort: coil enforced primarily by {pool} — their blocks reinforced compression rather than relieving it."
            )
    elif tilt == "reliever":
        if pool == "UNKNOWN":
            return (
                "Miner Cohort: mild reliever profile — block production slightly eased tension with no dominant pool."
            )
        else:
            return (
                f"Miner Cohort: reliever tilt led by {pool} — their blocks acted as a partial pressure valve today."
            )
    else:
        # neutral or anything else
        if pool == "UNKNOWN":
            return "Miner Cohort: neutral — no clear enforcement or relief emerged from today’s pool mix."
        else:
            return f"Miner Cohort: neutral — {pool} was active but did not materially tilt the coil."


def load_calibration_summary(path: Path) -> Optional[Dict[str, Any]]:
    """
    Read reports/calibration_summary.json if present.
    Return None on any error or missing file.
    """
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _choose_outcome_comment(n: int, brier: Optional[float], auc: Optional[float]) -> str:
    if n < 30:
        return "sample size is too small — HUD is in bootstrap mode."
    if brier is None or auc is None:
        return "metrics unavailable — HUD is in bootstrap mode."
    if brier <= 0.08 and auc >= 0.70:
        return "forecasts are sharp and honest — pressure calls track realized outcomes."
    elif brier <= 0.12 and 0.55 <= auc < 0.70:
        return "forecasts are directionally useful, but calibration still maturing."
    else:
        return "physics stack is under-calibrated — treat coil calls as experimental."

def render_outcome_hud(lines: List[str], summary: Optional[Dict[str, Any]]) -> None:
    lines.append("4.9) OUTCOME HUD")
    lines.append("-------------------------------------")
    if summary is None or summary.get("sample_count", 0) == 0:
        lines.append("Samples (last N days): 0")
        lines.append("Brier score (coil events): n/a")
        lines.append("AUC (pressure score vs events): n/a")
        lines.append("Comment: sample size is too small — HUD is in bootstrap mode.")
        lines.append("")
        return

    # Extract & round
    n = int(summary.get("sample_count", 0))
    brier = summary.get("brier")
    auc = summary.get("auc")

    def fmt(x):
        return "n/a" if x is None else f"{x:.3f}"

    lines.append(f"Samples (last N days): {n}")
    lines.append(f"Brier score (coil events): {fmt(brier)}")
    lines.append(f"AUC (pressure score vs events): {fmt(auc)}")

    # Comment selection per thresholds
    comment = _choose_outcome_comment(n, brier, auc)
    lines.append(f"Comment: {comment}")
    lines.append("")

def render_oracle_honesty(lines: List[str], honesty: Dict[str, Any]) -> None:
    lines.append("4.10) ORACLE HONESTY")
    lines.append("-------------------------")
    samples = honesty.get("samples", 0)
    if samples < 30:
        lines.append("Oracle Honesty: insufficient data — honesty requires history.")
        lines.append("")
        return

    brier = honesty.get("brier")
    auc = honesty.get("auc")

    def fmt(x):
        return "n/a" if x is None else f"{x:.3f}"

    lines.append(f"Brier Score (90d): {fmt(brier)}")
    lines.append(f"AUC (90d): {fmt(auc)}")
    lines.append("Interpretation: lower Brier = more honest forecasts; AUC → discrimination power")
    lines.append("")

def render_miner_field(hashrate_state: Dict[str, Any], miner_threshold: Dict[str, Any]) -> str:
    band = hashrate_state.get("stress_band", "calm")
    score = hashrate_state.get("stress_score", 0.0)
    trend = hashrate_state.get("trend", "unknown")
    label = hashrate_state.get("label", "Miner field unknown — no data.")

    th_band = miner_threshold.get("band", "below")
    th_index = miner_threshold.get("index", 0.0)
    th_at = miner_threshold.get("at_threshold", False)

    # Human line for the APEX deck
    if th_band == "critical":
        threshold_line = f"Threshold: CRITICAL — miners are in survival mode; block rewards are no longer enough to keep them solvent at current prices (MTI {th_index:.2f})."
    elif th_band == "strained":
        threshold_line = f"Threshold: STRAINED — miners have shifted from neutral production into exit-liquidity hunting (MTI {th_index:.2f})."
    elif th_band == "amber":
        threshold_line = f"Threshold: AMBER — stress rising; miners nearing forced-seller territory (MTI {th_index:.2f})."
    else:
        threshold_line = f"Threshold: BELOW — miner stress remains manageable (MTI {th_index:.2f})."

    lines = [
        "### Miner Incentive Field",
        "",
        f"- Hashrate trend: **{trend}**",
        f"- Miner stress: **{score:.1f} / 10** · band: **{band}**",
        f"- {threshold_line}",
    ]
    if th_at:
        lines.append(f"- Note: Hashrate remains {band}, but once fused with CTI and the COMPRESSION regime, miners enter the {th_band.upper()} threshold (MTI {th_index:.2f}).")
    lines.extend([
        f"- Interpretation: {label}",
        "",
    ])
    return "\n".join(lines)


def build_apex_deck(
    *,
    date_utc: str,
    regime_state: Dict[str, Any],
    regime_clock_state: Dict[str, Any],
    memory_state: Dict[str, Any],
    intent_clock_state: Dict[str, Any],
    daily_state: Dict[str, Any],
    entropy_events_path: Path,
    reports_dir: Path,
    window_min_height: int,
    window_max_height: int,
    hashrate_state: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Build the APEX Daily Deck v2.0 and write:
      reports/chainwalk_apex_{date_utc}.md

    Returns the Path to the written file.
    """

    reports_dir.mkdir(parents=True, exist_ok=True)
    project_root = reports_dir.parent

    # Load states
    mempool_state = {}
    mempool_path = reports_dir / "mempool_intent_state.json"
    if mempool_path.exists():
        with mempool_path.open("r", encoding="utf-8") as f:
            mempool_state = json.load(f)

    # 1) Core regime fields
    regime_label = daily_state.get(
        "regime_label",
        regime_state.get("dominant_vector", "UNKNOWN"),
    )
    regime_streak = regime_state.get("current_streak", 0)
    total_flips = regime_state.get("total_flips", 0)

    cti = float(daily_state.get("chain_tension_index", 0.0))
    cti_str = f"{cti:.1f}"

    custody_dir = memory_state.get("custody_direction", "neutral")
    custody_streak = int(memory_state.get("custody_streak", 0))
    entropy_trend = memory_state.get("entropy_trend_7d", "flat")

    price_corridor = daily_state.get("price_corridor", "UNKNOWN")

    # Incentive / trapdoor
    incentive_delta = float(daily_state.get("incentive_delta", 0.0))
    trapdoor = daily_state.get("trapdoor", {})
    trapdoor_label = trapdoor.get(
        "label",
        "Trapdoor state unavailable — no custody/CTI coupling today.",
    )

    # Regime inevitability (outcome line)
    inevitability = "volatility is guaranteed; only timing is unknown"
    # If you have a richer outcome somewhere else, wire it in here.
    # For now, keep the current COMPRESSION phrasing.
    if regime_label != "COMPRESSION":
        # Fallback generic line
        inevitability = f"regime '{regime_label}' remains in force; timing remains path-dependent."

    # 2) Clocks
    intent_clock_line = intent_clock_state.get(
        "clock_line",
        "Intent Clock: no active intent clock state.",
    )
    regime_clock_line = regime_clock_state.get(
        "clock_line",
        "Regime Clock: no active regime clock state.",
    )

    # 3) Wavefunction
    wave = _load_last_wavefunction(project_root / "regime_wavefunction.jsonl")
    dominant_state = _resolve_wavefunction_dominant(wave, regime_state)
    expectation = _resolve_wavefunction_expectation(wave)

    # 4) Drivers
    drivers = daily_state.get("drivers", {})
    cti_driver = float(drivers.get("cti", 0.0))
    custody_driver = float(drivers.get("custody", 0.0))
    intent_driver = float(drivers.get("mempool_intent", 0.0))

    # 5) Mempool intent
    mempool_line = mempool_state.get(
        "line",
        "No mempool intent summary available.",
    )

    # 6) Clocks window
    phase = regime_clock_state.get("phase", "UNKNOWN")
    window_days = regime_clock_state.get("window_days", {})
    rc_min = window_days.get("min_remaining", None)
    rc_max = window_days.get("max_remaining", None)

    if rc_min is not None and rc_max is not None:
        rc_window = f"{int(rc_min)}–{int(rc_max)} days remaining"
    else:
        rc_window = "window unknown"

    ic_days = intent_clock_state.get("max_days_remaining", None)
    if ic_days is not None:
        ic_window = f"{int(ic_days)} days until intent collapses"
    else:
        ic_window = "intent window unknown"

    # 7) Block of the Day
    events = _load_entropy_events(entropy_events_path)
    bod_event = select_block_of_day(events, window_min_height, window_max_height)

    # Safety guard
    if bod_event is not None:
        h = int(bod_event.get("height", 0))
        if not (window_min_height <= h <= window_max_height):
            raise RuntimeError(
                f"Block-of-Day height {h} outside window "
                f"[{window_min_height}, {window_max_height}]"
            )

    # 8) Spine footer
    spine_path = reports_dir / "chainwalk_spine_latest.txt"
    if spine_path.exists():
        spine_line = spine_path.read_text(encoding="utf-8").strip()
    else:
        spine_line = "CWSPINE v0.1 | unavailable"

    # ---------------------------------------
    # Build markdown sections
    # ---------------------------------------
    lines: List[str] = []

    # HEADER
    lines.append("# The ChainWalk Desk — APEX Daily Deck v2.0")
    lines.append(f"Date: {date_utc} · Regime: {regime_label} · Phase: {phase}")
    lines.append(
        f"CTI (Chain Tension Index): {cti_str}/10 — tension stored, not released"
    )
    lines.append(
        f"Custody Vector: {custody_dir} (streak {custody_streak}) · Entropy: {entropy_trend}"
    )
    lines.append(f"Desk Verdict: {inevitability}")
    lines.append("")

    # Regime Integrity one-liner
    ri = daily_state.get("regime_integrity", {})
    if ri:
        if isinstance(ri, str):
            lines.append(f"Regime Integrity: {ri}")
        else:
            lines.append(
                f"Regime Integrity: {ri.get('label', 'UNKNOWN')} — "
                f"trapdoor {ri.get('custody_trapdoor', '?')}, "
                f"miners {ri.get('miner_threshold', '?')}, "
                f"custody {ri.get('custody_direction', 'UNKNOWN')}."
            )
        lines.append("")

    lines.append("-------------------------------------")
    lines.append("1) REGIME OVERVIEW")
    lines.append("-------------------------------------")
    lines.append("1) REGIME OVERVIEW")
    lines.append("-------------------------------------")
    lines.append(f"Regime: {regime_label} (streak {regime_streak}, flips {total_flips})")
    lines.append(f"Outcome: {inevitability}")
    lines.append(f"CTI: {cti_str}/10 — chain tension {'neutral' if 4.0 <= cti <= 6.0 else 'elevated'}")
    lines.append(f"Custody Vector: {custody_dir} (streak {custody_streak})")
    lines.append(f"Entropy Field: {entropy_trend}")
    lines.append(f"Price Corridor: {price_corridor}")
    lines.append("")
    lines.append(
        f"Incentive Delta: {incentive_delta:+.2f}  "
        "(positive = behavior leaning with incentives, negative = fighting them)"
    )
    lines.append(f"Custody Trapdoor: {trapdoor_label}")
    lines.append("")

    # 2) TEMPORAL WINDOWS
    lines.append("-------------------------------------")
    lines.append("2) TEMPORAL WINDOWS")
    lines.append("-------------------------------------")
    lines.append(f"{intent_clock_line}")
    lines.append(f"{regime_clock_line}")
    lines.append("")
    lines.append(f"Intent Window: {ic_window}")
    lines.append(f"Regime Window: {rc_window}")
    lines.append("")

    # 3) WAVEFUNCTION READOUT
    lines.append("-------------------------------------")
    lines.append("3) WAVEFUNCTION READOUT")
    lines.append("-------------------------------------")
    lines.append(f"Dominant Vector: {dominant_state}")
    lines.append(f"Expectation Bias: {expectation:+.3f}")
    lines.append("")
    lines.append("Interpretation:")
    lines.append(
        "- The wavefunction encodes the chain's preference over regime outcomes.\n"
        "- A higher expectation magnitude means the chain is leaning harder into one path."
    )
    lines.append("")

    # 4) DRIVER PANEL
    lines.append("-------------------------------------")
    lines.append("4) DRIVER PANEL")
    lines.append("-------------------------------------")
    lines.append("")

    lines.append("| DRIVER  | STATE              | DIRECTION | WEIGHT |")
    lines.append("|---------|--------------------|----------:|-------:|")
    lines.append(
        f"| CTI     | {cti_str}/10           | "
        f"{'↑' if cti_driver > 0 else ('↓' if cti_driver < 0 else '→')} | {cti_driver:+.2f} |"
    )
    lines.append(
        f"| Custody | {custody_dir} (st {custody_streak}) | "
        f"{'↑' if custody_driver > 0 else ('↓' if custody_driver < 0 else '→')} | {custody_driver:+.2f} |"
    )
    lines.append(
        f"| Intent  | {mempool_state.get('state', 'UNKNOWN')}         | "
        f"{'↑' if intent_driver > 0 else ('↓' if intent_driver < 0 else '→')} | {intent_driver:+.2f} |"
    )
    lines.append("")
    lines.append("Mempool Signal:")
    lines.append(f"- {mempool_line}")
    lines.append("")

    # Miner Incentive Field
    miner_threshold = daily_state.get("miner_threshold", {})
    if hashrate_state:
        lines.append("-------------------------------------")
        lines.append("4.5) MINER INCENTIVE FIELD")
        lines.append("-------------------------------------")
        lines.append(render_miner_field(hashrate_state, miner_threshold))
        lines.append("")

    # Difficulty Epoch
    epoch_state = daily_state.get("difficulty_epoch", {})
    if epoch_state:
        lines.append("-------------------------------------")
        lines.append("4.6) DIFFICULTY EPOCH")
        lines.append("-------------------------------------")
        tension_idx = epoch_state.get("tension_index", 0.0)
        band = epoch_state.get("tension_band", "relaxed")
        label = epoch_state.get("label", "")
        lines.append(f"Epoch tension: {band.upper()} (ETI {tension_idx:.2f}) — {label}")
        lines.append("")

    # Miner Cohort Tilt
    cohort_state = daily_state.get("miner_cohort", {})
    if cohort_state:
        lines.append("-------------------------------------")
        lines.append("4.7) MINER COHORT TILT")
        lines.append("-------------------------------------")
        tilt = cohort_state.get("tilt_label", "neutral")
        dominant_pool = cohort_state.get("dominant_pool", "UNKNOWN")
        lines.append(describe_miner_cohort(tilt, dominant_pool))
        lines.append("")

    # Constraint Stack
    lines.append("-------------------------------------")
    lines.append("4.8) CONSTRAINT STACK")
    lines.append("-------------------------------------")
    lines.append("CTI — chain tension (how tightly Bitcoin’s incentive coil is compressed)")
    lines.append("MTI — miner threshold (how much stress producers can absorb before leaning on price)")
    lines.append("IRQ — irreversibility (how much optionality has been eliminated; unwind no longer benign)")
    lines.append("REI — resolution field (how close the system is to forcing a regime outcome)")
    lines.append("")

    # Uncertainty Quotient
    uncertainty = daily_state.get("uncertainty", {})
    uqi_band = uncertainty.get("band", "unknown")
    uqi_index = uncertainty.get("index", 0.0)
    glyph = uncertainty.get("details", {}).get("glyph", "❓")
    lines.append("-------------------------------------")
    lines.append("4.11) UNCERTAINTY QUOTIENT")
    lines.append("-------------------------------------")
    lines.append(f"Uncertainty Field (UQI): {glyph} {uqi_band} — futures are being removed (UQI {uqi_index:.2f})")
    lines.append("")

    # Outcome HUD
    summary = load_calibration_summary(project_root / "reports" / "calibration_summary.json")
    render_outcome_hud(lines, summary)

    # Oracle Honesty
    from utils.outcome_engine import get_calibration_summary
    honesty = get_calibration_summary(90)
    render_oracle_honesty(lines, honesty)

    # Sovereign Oracle
    lines.extend(render_sovereign_oracle_section(daily_state))

    # 5) BLOCK OF THE DAY
    lines.append(_format_block_section(bod_event, window_min_height, window_max_height))

    # 6) TACTICAL READ
    lines.append("-------------------------------------")
    lines.append("6) TACTICAL READ")
    lines.append("-------------------------------------")
    lines.append(
        "Custody remains {dir} with a streak of {streak}, while CTI holds near {cti}.\n"
        "Incentives are {bias} and the trapdoor is {trap}.\n"
        "Together, this describes how quickly behavior can snap when the regime resolves."
        .format(
            dir=custody_dir,
            streak=custody_streak,
            cti=cti_str,
            bias=(
                "aligned with the chain"
                if incentive_delta > 0.1
                else ("fighting the chain" if incentive_delta < -0.1 else "indecisive")
            ),
            trap=trapdoor.get("band", "latent"),
        )
    )
    lines.append("")
    lines.append("Volatility is not optional; only path and timing remain negotiable.")
    lines.append("")

    # 7) CWSPINE FOOTER
    lines.append("-------------------------------------")
    lines.append("CWSPINE FOOTER")
    lines.append("-------------------------------------")
    lines.append(spine_line)
    lines.append("")

    # Write to file
    out_path = reports_dir / f"chainwalk_apex_{date_utc}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path