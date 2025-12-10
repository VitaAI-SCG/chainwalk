# utils/sanity_check.py

import json
import re
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def load_json(name: str) -> dict:
    path = REPORTS / name
    if not path.exists():
        raise FileNotFoundError(f"Missing required JSON: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_text(name: str) -> str:
    path = REPORTS / name
    if not path.exists():
        raise FileNotFoundError(f"Missing required text: {path}")
    return path.read_text(encoding="utf-8")


def check_cti(daily: dict, scorecard: str, post: str, errors: List[str]) -> None:
    cti = float(daily.get("chain_tension_index", 0.0))
    cti_str = f"{cti:.1f}"

    sc_lower = scorecard.lower()
    post_lower = post.lower()

    sc_match = re.search(r"cti:.*?(\d+\.\d)/10", sc_lower)
    if not sc_match:
        errors.append("CTI check: could not parse CTI line from scorecard.")
    elif sc_match.group(1) != cti_str:
        errors.append(
            f"CTI mismatch (scorecard): daily={cti_str}, scorecard={sc_match.group(1)}"
        )

    post_match = re.search(r"chain tension index:\s*(\d+\.\d)/10", post_lower)
    if not post_match:
        errors.append("CTI check: could not parse Chain Tension Index from post.")
    elif post_match.group(1) != cti_str:
        errors.append(
            f"CTI mismatch (post): daily={cti_str}, post={post_match.group(1)}"
        )


def check_custody(memory: dict, scorecard: str, post: str, errors: List[str]) -> None:
    direction = str(memory.get("custody_direction", "")).strip()
    streak = int(memory.get("custody_streak", 0))

    expected_sc = f"-> {direction} (streak {streak})".lower()
    expected_post = f"{direction} (streak {streak})".lower()

    sc_lower = scorecard.lower()
    post_lower = post.lower()

    if expected_sc not in sc_lower:
        errors.append(
            f"Custody mismatch (scorecard): expected fragment '{expected_sc}' not found."
        )

    post_match = re.search(r"custody vector:\s*(.+)", post_lower)
    if not post_match or expected_post not in post_match.group(1):
        errors.append(
            f"Custody mismatch (post): expected fragment '{expected_post}' not found."
        )


def check_corridor(daily: dict, scorecard: str, post: str, errors: List[str]) -> None:
    corridor = str(daily.get("price_corridor", "")).strip().lower()
    sc_lower = scorecard.lower()
    post_lower = post.lower()

    sc_match = re.search(r"price corridor:\s*([a-z]+)", sc_lower)
    if not sc_match:
        errors.append("Corridor check: could not parse PRICE CORRIDOR from scorecard.")
    elif sc_match.group(1) != corridor:
        errors.append(
            f"Corridor mismatch (scorecard): daily={corridor}, scorecard={sc_match.group(1)}"
        )

    post_match = re.search(r"price corridor:\s*([a-z]+)", post_lower)
    if not post_match:
        errors.append("Corridor check: could not parse Price Corridor from post.")
    elif post_match.group(1) != corridor:
        errors.append(
            f"Corridor mismatch (post): daily={corridor}, post={post_match.group(1)}"
        )


def check_intent_clock(intent_clock: dict, post: str, errors: List[str]) -> None:
    post_lower = post.lower()
    max_days = int(intent_clock.get("max_days_remaining", 0))

    # Grab the Intent Clock line for better error messages
    line_match = re.search(r"intent clock:(.*)", post_lower)
    intent_line = line_match.group(0) if line_match else "(no intent clock line)"

    if max_days == 0:
        # At edge: must NOT mention "1 days remain", etc.
        if re.search(r"\d+\s+days remain before intent collapses", intent_line):
            errors.append(
                f"Intent clock edge mismatch: max_days_remaining=0 but line still uses 'days remain' form → {intent_line!r}"
            )
    else:
        pattern = rf"{max_days}\s+days remain before intent collapses"
        if not re.search(pattern, intent_line):
            errors.append(
                f"Intent clock mismatch: expected '{max_days} days remain before intent collapses' in line → {intent_line!r}"
            )

    # Optional spine check
    spine_path = REPORTS / "chainwalk_spine_latest.txt"
    if spine_path.exists():
        spine = spine_path.read_text(encoding="utf-8").lower()
        spine_match = re.search(r"ic=(\d+)d", spine)
        if spine_match:
            ic_days = int(spine_match.group(1))
            if ic_days != max_days:
                errors.append(
                    f"Intent clock mismatch (spine): intent_clock_state={max_days}d, spine={ic_days}d"
                )


def check_oracle_provenance(errors: List[str]) -> None:
    """Oracle Provenance Guard: Reject impurity."""
    from core.oracle_kernel import verify_oracle_integrity

    # Check kernel integrity
    kernel_path = Path(__file__).resolve().parent.parent / "core" / "oracle_kernel.py"
    if kernel_path.exists():
        kernel_code = kernel_path.read_text(encoding="utf-8")
        if not verify_oracle_integrity(kernel_code):
            errors.append("[SOVEREIGN-VIOLATION] Oracle kernel contains forbidden references (price, LLM, sentiment, off-chain)")

    # Check for modified constraint symbols (placeholder: assume fixed)
    # In future, compare against immutable hash

    # Check for mutated band semantics (placeholder)
    # Ensure bands like CTI low/medium/high are not altered

    # Check for illegal dependencies (e.g., no new imports referencing forbidden things)
    # Placeholder: scan for forbidden imports

def main() -> None:
    errors: List[str] = []

    reports_dir = Path(__file__).resolve().parent.parent / "reports"

    check_oracle_provenance(errors)

    daily = load_json("chainwalk_daily_state.json")
    memory = load_json("memory_of_price_state.json")
    _mempool = load_json("mempool_intent_state.json")  # reserved for future checks
    _regime = load_json("regime_state.json")
    _regime_clock = load_json("regime_clock_state.json")
    intent_clock = load_json("intent_clock_state.json")

    scorecard = load_text("scorecard_latest.md")
    post = load_text("chainwalk_post_latest.md")
    spine = load_text("chainwalk_spine_latest.txt")

    # Oracle Input Hash presence + shape
    oih = daily.get("oracle_input_hash")
    if not (isinstance(oih, str) and len(oih) == 64):
        errors.append("[OIH-STATE-MISSING] oracle_input_hash missing or malformed in daily_state.")

    # Date consistency
    date_utc = daily.get("date_utc", "")
    if date_utc not in spine:
        errors.append(f"Date mismatch between daily_state ({date_utc}) and spine")

    # Difficulty epoch date
    epoch_state = daily.get("difficulty_epoch", {})
    if epoch_state and epoch_state.get("date_utc") != date_utc:
        errors.append(f"Difficulty epoch date mismatch: {epoch_state.get('date_utc')} != {date_utc}")

    # Miner cohort date
    cohort_state = daily.get("miner_cohort", {})
    if cohort_state and cohort_state.get("date_utc") != date_utc:
        errors.append(f"Miner cohort date mismatch: {cohort_state.get('date_utc')} != {date_utc}")

    # Outcome history last row date
    from .outcome_engine import load_outcome_history
    history = load_outcome_history(REPORTS / "outcome_history.jsonl")
    if history:
        last_date = history[-1].get("date_utc")
        if last_date != date_utc:
            errors.append(f"Outcome history last date mismatch: {last_date} != {date_utc}")
        # OIH coherence
        last_oih = history[-1].get("oracle_input_hash")
        if last_oih != oih:
            errors.append(f"[OIH-OUTCOME-MISMATCH] outcome_history oracle_input_hash {last_oih} != daily_state {oih}")

    # Spine EP and MC
    if "EP=" not in spine:
        errors.append("Spine missing EP= encoding")
    if cohort_state and "MC=" not in spine:
        errors.append("Spine missing MC= encoding when cohort present")

    # Spine OIH echo
    spine_match = re.search(r"OIH=(\w{8})", spine)
    if not spine_match:
        errors.append("[OIH-SPINE-MISSING] Spine missing OIH= encoding")
    else:
        spine_oih = spine_match.group(1)
        expected_short = oih[-8:]
        if spine_oih != expected_short:
            errors.append(f"[OIH-SPINE-MISMATCH] spine OIH {spine_oih} does not match daily_state suffix {expected_short}")

    check_cti(daily, scorecard, post, errors)
    check_custody(memory, scorecard, post, errors)
    check_corridor(daily, scorecard, post, errors)
    check_intent_clock(intent_clock, post, errors)

    # Regime integrity checks
    regime_integrity = daily.get("regime_integrity", {})
    trapdoor = daily.get("trapdoor", {})
    miner_threshold = daily.get("miner_threshold", {})
    if isinstance(regime_integrity, dict):
        if regime_integrity.get("custody_trapdoor") != trapdoor.get("band"):
            errors.append(f"Regime integrity custody_trapdoor mismatch: {regime_integrity.get('custody_trapdoor')} != {trapdoor.get('band')}")
        if regime_integrity.get("miner_threshold") != miner_threshold.get("band"):
            errors.append(f"Regime integrity miner_threshold mismatch: {regime_integrity.get('miner_threshold')} != {miner_threshold.get('band')}")

    # Irreversibility checks
    irreversibility = daily.get("irreversibility", {})
    irq_band = irreversibility.get("band", "reversible")
    irq_index = float(irreversibility.get("index", 0.0))
    regime_label = daily.get("regime_label", "")

    # Band monotonic coherence (irreversible only in pressure regimes)
    if irq_band == "irreversible" and regime_label not in {"COMPRESSION", "STARVATION"}:
        errors.append(f"Irreversibility band 'irreversible' but regime {regime_label} not in {{COMPRESSION, STARVATION}}")

    # Floor conditions
    if irq_band == "floor":
        mti = miner_threshold.get("index", 0.0)
        cti = daily.get("chain_tension_index", 0.0)
        if not (mti >= 0.85 and cti >= 6.5):
            errors.append(f"Irreversibility band 'floor' but MTI {mti:.2f} < 0.85 or CTI {cti:.1f} < 6.5")

    # Date consistency (checked for separate state files, not embedded)

    # Resolution checks
    resolution = daily.get("resolution", {})
    rei_band = resolution.get("band", "dormant")
    rei_index = float(resolution.get("index", 0.0))

    # Band ↔ value coherence
    if rei_index < 0.30 and rei_band != "dormant":
        errors.append(f"REI band '{rei_band}' but index {rei_index:.2f} < 0.30 (should be dormant)")
    elif 0.30 <= rei_index < 0.55 and rei_band != "charged":
        errors.append(f"REI band '{rei_band}' but index {rei_index:.2f} in [0.30, 0.55) (should be charged)")
    elif 0.55 <= rei_index < 0.78 and rei_band != "imminent":
        errors.append(f"REI band '{rei_band}' but index {rei_index:.2f} in [0.55, 0.78) (should be imminent)")
    elif rei_index >= 0.78 and rei_band != "triggered":
        errors.append(f"REI band '{rei_band}' but index {rei_index:.2f} >= 0.78 (should be triggered)")

    # Pressure regime gating
    if rei_band in {"imminent", "triggered"}:
        if regime_label not in {"COMPRESSION", "STARVATION"}:
            errors.append(f"REI band '{rei_band}' but regime {regime_label} not in {{COMPRESSION, STARVATION}}")
        if daily.get("chain_tension_index", 0.0) < 6.5:
            errors.append(f"REI band '{rei_band}' but CTI {daily.get('chain_tension_index', 0.0):.1f} < 6.5")
        if miner_threshold.get("index", 0.0) < 0.78:
            errors.append(f"REI band '{rei_band}' but MTI {miner_threshold.get('index', 0.0):.2f} < 0.78")
        if irq_index < 0.78:
            errors.append(f"REI band '{rei_band}' but IRQ {irq_index:.2f} < 0.78")

    # Uncertainty checks
    uncertainty = daily.get("uncertainty", {})
    uqi_band = uncertainty.get("band", "open")
    uqi_index = float(uncertainty.get("index", 0.0))

    # Band ↔ value coherence
    if uqi_index < 0.33 and uqi_band != "open":
        errors.append(f"UQI band '{uqi_band}' but index {uqi_index:.2f} < 0.33 (should be open)")
    elif 0.33 <= uqi_index < 0.66 and uqi_band != "narrowing":
        errors.append(f"UQI band '{uqi_band}' but index {uqi_index:.2f} in [0.33, 0.66) (should be narrowing)")
    elif 0.66 <= uqi_index < 0.88 and uqi_band != "thin":
        errors.append(f"UQI band '{uqi_band}' but index {uqi_index:.2f} in [0.66, 0.88) (should be thin)")
    elif uqi_index >= 0.88 and uqi_band != "terminal":
        errors.append(f"UQI band '{uqi_band}' but index {uqi_index:.2f} >= 0.88 (should be terminal)")

    # Illegal state checks
    custody_streak = int(memory.get("custody_streak", 0))
    cohort = daily.get("miner_cohort", {})
    tilt = cohort.get("tilt_label", "neutral")

    if uqi_band == "terminal":
        if irq_band not in {"irreversible", "floor"} and rei_band not in {"imminent", "triggered"}:
            errors.append(f"UQI terminal but IRQ {irq_band} not in {{irreversible, floor}} and REI {rei_band} not in {{imminent, triggered}}")

    if uqi_band == "open" and custody_streak >= 6:
        errors.append(f"UQI open but custody_streak {custody_streak} >= 6")

    if uqi_band == "thin" and tilt == "neutral":
        errors.append(f"UQI thin but miner cohort tilt '{tilt}' == neutral")

    # Constraint Stack check
    apex_path = reports_dir / f"chainwalk_apex_{date_utc}.md"
    if apex_path.exists():
        with apex_path.open("r", encoding="utf-8") as f:
            content = f.read()
        if "4.8) CONSTRAINT STACK" not in content:
            errors.append("APEX deck missing CONSTRAINT STACK section")
        else:
            # Check order and purity
            lines = content.split('\n')
            stack_start = None
            for i, line in enumerate(lines):
                if "4.8) CONSTRAINT STACK" in line:
                    stack_start = i + 2  # after header
                    break
            if stack_start:
                expected = [
                    "CTI — chain tension (how tightly Bitcoin’s incentive coil is compressed)",
                    "MTI — miner threshold (how much stress producers can absorb before leaning on price)",
                    "IRQ — irreversibility (how much optionality has been eliminated; unwind no longer benign)",
                    "REI — resolution field (how close the system is to forcing a regime outcome)",
                ]
                for j, exp in enumerate(expected):
                    if stack_start + j >= len(lines) or exp not in lines[stack_start + j]:
                        errors.append(f"[UX-STACK-ORDER-ERROR] Constraint block out of canonical order or polluted with runtime fields")
                        break

        # Oracle Honesty check
        if "4.10) ORACLE HONESTY" not in content:
            errors.append("[UX-HONESTY-LINE-MISSING] APEX deck missing ORACLE HONESTY section")

        # Sovereign Oracle check
        if "4.11) SOVEREIGN ORACLE" not in content:
            errors.append("[UX-SOVEREIGN-ORACLE-MISSING] APEX deck missing SOVEREIGN ORACLE section")
        if "Oracle Input Fingerprint" not in content:
            errors.append("[UX-OIH-FINGERPRINT-MISSING] APEX deck missing Oracle Input Fingerprint")

    # Outcome HUD check
    summary_path = reports_dir / "calibration_summary.json"
    if summary_path.exists():
        try:
            with summary_path.open("r", encoding="utf-8") as f:
                summary = json.load(f)
            n = summary.get("sample_count", 0)
            brier = summary.get("brier")
            auc = summary.get("auc")
            if n < 0:
                errors.append("[CAL-HUD-RANGE-ERROR] sample_count < 0")
            if brier is not None and not (0.0 <= brier <= 1.0):
                errors.append(f"[CAL-HUD-RANGE-ERROR] brier {brier} not in [0,1]")
            if auc is not None and not (0.0 <= auc <= 1.0):
                errors.append(f"[CAL-HUD-RANGE-ERROR] auc {auc} not in [0,1]")
        except Exception as e:
            errors.append(f"[CAL-HUD-ERROR] failed to load calibration_summary.json: {e}")

    # Spine echo
    # Parse REI=band,index from chainwalk_spine_history.log latest line and assert it matches daily_state["resolution"]

    # Hashrate checks
    hashrate = daily.get("hashrate", {})
    band = hashrate.get("stress_band", "calm")
    score = float(hashrate.get("stress_score", 0.0))

    if band == "calm" and score >= 3.0:
        errors.append("Miner field band 'calm' but stress_score >= 3.0")

    if band == "distress" and score <= 6.0:
        errors.append("Miner field band 'distress' but stress_score <= 6.0")

    # Miner threshold checks
    th = load_json("miner_threshold_state.json")
    idx = th["index"]
    th_band = th["band"]

    # Range check
    if not (0.0 <= idx <= 1.0):
        errors.append(f"Miner threshold index {idx} out of [0,1] range.")

    # Band coherence
    if th_band == "below":
        if idx >= 0.60:
            errors.append(f"Threshold band BELOW but index {idx} >= 0.60")
    elif th_band == "amber":
        if not (0.40 <= idx < 0.70):
            errors.append(f"Threshold band AMBER but index {idx} outside [0.40, 0.70)")
    elif th_band == "strained":
        if not (0.60 <= idx < 0.90):
            errors.append(f"Threshold band STRAINED but index {idx} outside [0.60, 0.90)")
    elif th_band == "critical":
        if idx < 0.80:
            errors.append(f"Threshold band CRITICAL but index {idx} < 0.80")

    # Spine echo
    spine = load_text("chainwalk_spine_latest.txt")
    spine_match = re.search(r"TH=([^,]+),([\d.]+)", spine)
    if not spine_match:
        errors.append("Spine TH encoding not found in chainwalk_spine_latest.txt")
    else:
        spine_band = spine_match.group(1)
        spine_index = float(spine_match.group(2))
        if spine_band != th_band:
            errors.append(f"Spine TH band mismatch: state={th_band}, spine={spine_band}")
        if abs(spine_index - idx) > 0.02:
            errors.append(f"Spine TH index drift: state={idx:.3f}, spine={spine_index:.3f}")

    # Regime gating
    if th.get("at_threshold", False):
        regime_label = _regime.get("dominant_vector", "")
        if regime_label != "COMPRESSION":
            errors.append(f"At threshold but regime {regime_label} != COMPRESSION")
        ic_days = intent_clock.get("max_days_remaining", 1)
        if ic_days != 0:
            errors.append(f"At threshold but intent clock days remaining {ic_days} != 0")

    if errors:
        print("[sanity] [FAIL] ChainWalk sanity check FAILED:")
        for e in errors:
            print("   -", e)
        sys.exit(1)
    else:
        print("[sanity] [PASS] ChainWalk sanity check PASSED — all surfaces coherent.")
        sys.exit(0)


if __name__ == "__main__":
    main()