import json
import os
import sys
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- Ensure project root & core package on sys.path -------------------------

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.regime_metrics import compute_snapshot, ChainTensionSnapshot
from core.brief_renderer import render_apex_brief
from utils.memory_of_price import update_memory_state, MemorySnapshot
from utils.price_corridor_engine import compute_corridor
from renderers.price_corridor_renderer import render_price_corridor
from utils.regime_tracker import classify_regime
from renderers.regime_renderer import render_regime_section
from utils.scoreboard_loader import load_scoreboard_state
from utils.wavefunction import scores_to_wavefunction
from utils.regime_hamiltonian import compute_regime_horizon, REGIME_BASIS
from utils.regime_clock import compute_regime_clock, regime_clock_to_json
from utils.intent_clock import compute_intent_clock, intent_clock_to_json
from utils.incentive import compute_drivers, compute_incentive_delta, has_incentive_conflict
from utils.trapdoor import compute_trapdoor
from utils.spine import build_spine_line
from utils.mempool_intent import (
    compute_mempool_intent,
    mempool_intent_to_json,
)
from utils.apex_deck import build_apex_deck
from utils.hashrate_oracle import HashrateInputs, hashrate_to_json
from utils.miner_threshold import compute_miner_threshold, to_state_dict
from utils.outcome_engine import append_outcome_snapshot
from utils.difficulty_epoch import compute_epoch_tension, save_difficulty_epoch_state
from utils.miner_cohorts import compute_miner_cohort_tilt, save_miner_cohort_tilt
from utils.irreversibility_engine import compute_irq
from utils.resolution_engine import compute_resolution_index
from utils.uncertainty_engine import compute_uqi
from utils import alert_rail
from utils.oracle_fingerprint import compute_oracle_input_hash

def format_regime_horizon_line(ham_state) -> str:
    """
    Returns e.g. '51% COMPRESSION → 34% ASCENT → 10% DISTRIBUTION → 5% STARVATION'
    """
    basis = ham_state["basis"]
    p_horizon = ham_state["p_horizon"]
    pairs = list(zip(basis, p_horizon))
    pairs.sort(key=lambda x: x[1], reverse=True)
    percents = []
    for name, prob in pairs:
        if prob >= 0.01:  # >=1%
            percents.append(int(round(prob * 100)))
        else:
            percents.append(0)
    # Adjust to sum to 100
    total = sum(percents)
    if total != 100:
        diff = 100 - total
        percents[0] += diff  # Add to highest
    # Filter out zeros
    filtered = [(name, p) for name, p in zip([p[0] for p in pairs], percents) if p > 0]
    return " -> ".join(f"{p}% {name}" for name, p in filtered)
from ui.scorecard import render_scorecard
from datetime import datetime, timezone
import json


@dataclass
class BriefStats:
    block_count: int
    height_min: int
    height_max: int
    t_start: Optional[int]
    t_end: Optional[int]

    total_txs: int
    avg_txs_per_block: float

    total_out_btc: float
    total_fees_btc: float
    avg_fees_per_block: float

    avg_entropy: float
    avg_complexity: float

    polyphonic_count: int = 0
    polyphonic_rate: float = 0.0

    top_pools: List[Tuple[str, int]] = field(default_factory=list)
    top_channels: List[Tuple[str, int]] = field(default_factory=list)

    whales: List[Dict[str, Any]] = field(default_factory=list)
    interesting_blocks: List[Dict[str, Any]] = field(default_factory=list)


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default



    try:
        return float(v)
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    if v is None:
        return default
    try:
        return int(v)
    except Exception:
        return default


def load_latest_signals(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"latest signals JSON not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def compute_stats(data: Dict[str, Any]) -> BriefStats:
    signals: List[Dict[str, Any]] = data.get("signals") or []
    if not signals:
        raise ValueError("No signals found in sovereign_signals_latest.json")

    signals = sorted(signals, key=lambda s: _safe_int(s.get("height")))

    heights = [_safe_int(s.get("height")) for s in signals]
    ts_list = [_safe_int(s.get("timestamp"), 0) for s in signals if s.get("timestamp")]

    block_count = len(signals)
    height_min = min(heights) if heights else 0
    height_max = max(heights) if heights else 0
    t_start = min(ts_list) if ts_list else None
    t_end = max(ts_list) if ts_list else None

    # Tx stats
    tx_counts = [_safe_int(s.get("tx_count"), 0) for s in signals]
    total_txs = sum(tx_counts)
    avg_txs_per_block = total_txs / block_count if block_count else 0.0

    # Finance stats
    total_out_btc = sum(
        _safe_float(s.get("total_output_btc") or s.get("total_out_btc") or s.get("total_out"))
        for s in signals
    )
    total_fees_btc = sum(
        _safe_float(s.get("total_fee_btc") or s.get("fees_btc") or s.get("fees"))
        for s in signals
    )
    avg_fees_per_block = total_fees_btc / block_count if block_count else 0.0

    # Entropy / complexity
    entropies = [_safe_float(s.get("entropy")) for s in signals if s.get("entropy") is not None]
    complexities = [_safe_float(s.get("complexity")) for s in signals if s.get("complexity") is not None]
    avg_entropy = sum(entropies) / len(entropies) if entropies else 0.0
    avg_complexity = sum(complexities) / len(complexities) if complexities else 0.0

    # Polyphonic
    polyphonic_flags = [bool(s.get("polyphonic")) for s in signals]
    polyphonic_count = sum(1 for p in polyphonic_flags if p)
    polyphonic_rate = polyphonic_count / block_count if block_count else 0.0

    # Pools
    pool_counter: Counter = Counter()
    for s in signals:
        pool = (s.get("pool") or "unknown").strip() or "unknown"
        pool_counter[pool] += 1
    top_pools = pool_counter.most_common(5)

    # Channels
    chan_counter: Counter = Counter()
    for s in signals:
        ch = s.get("channels") or {}
        if isinstance(ch, dict):
            for k, v in ch.items():
                if v:
                    chan_counter[k] += 1
    top_channels = chan_counter.most_common(8)

    # Whale threshold
    whale_threshold = _safe_float(os.environ.get("CHAINWALK_WHALE_THRESHOLD", "100.0"), 100.0)

    whales: List[Dict[str, Any]] = []
    for s in signals:
        largest = _safe_float(
            s.get("largest_tx_btc") or s.get("largest_btc") or s.get("largest")
        )
        if largest >= whale_threshold:
            whales.append(
                {
                    "height": _safe_int(s.get("height")),
                    "timestamp": _safe_int(s.get("timestamp"), 0),
                    "pool": (s.get("pool") or "unknown").strip() or "unknown",
                    "largest_tx_btc": largest,
                    "total_output_btc": _safe_float(
                        s.get("total_output_btc") or s.get("total_out_btc") or s.get("total_out")
                    ),
                    "tx_count": _safe_int(s.get("tx_count"), 0),
                    "polyphonic": bool(s.get("polyphonic")),
                }
            )

    whales = sorted(whales, key=lambda w: w["largest_tx_btc"], reverse=True)[:8]

    # "Interesting" blocks = whales OR high fees OR noisy/polyphonic structure
    interesting: List[Dict[str, Any]] = []
    fee_ratio_threshold = 0.02  # 2% fees / value is quite spicy
    ent_high_threshold = avg_entropy + 0.7 if entropies else None

    for s in signals:
        height = _safe_int(s.get("height"))
        ts = _safe_int(s.get("timestamp"), 0)
        pool = (s.get("pool") or "unknown").strip() or "unknown"
        tx_count = _safe_int(s.get("tx_count"), 0)
        poly = bool(s.get("polyphonic"))

        largest = _safe_float(
            s.get("largest_tx_btc") or s.get("largest_btc") or s.get("largest")
        )
        total_out = _safe_float(
            s.get("total_output_btc") or s.get("total_out_btc") or s.get("total_out")
        )
        fees = _safe_float(
            s.get("total_fee_btc") or s.get("fees_btc") or s.get("fees")
        )
        fee_ratio = fees / total_out if total_out > 0 else 0.0

        ent = _safe_float(s.get("entropy"))
        flags: List[str] = []

        if largest >= whale_threshold:
            flags.append("whale-tx")
        if poly:
            flags.append("polyphonic")
        if fee_ratio >= fee_ratio_threshold:
            flags.append("high-fee-pressure")
        if ent_high_threshold is not None and ent >= ent_high_threshold:
            flags.append("high-entropy")

        if flags:
            interesting.append(
                {
                    "height": height,
                    "timestamp": ts,
                    "pool": pool,
                    "tx_count": tx_count,
                    "largest_tx_btc": largest,
                    "total_output_btc": total_out,
                    "fees_btc": fees,
                    "fee_ratio": fee_ratio,
                    "entropy": ent,
                    "polyphonic": poly,
                    "flags": flags,
                }
            )

    # Sort interesting: whales first, then fee ratio, then entropy
    interesting = sorted(
        interesting,
        key=lambda b: (
            -_safe_float(b.get("largest_tx_btc")),
            -_safe_float(b.get("fee_ratio")),
            -_safe_float(b.get("entropy")),
        ),
    )[:12]

    return BriefStats(
        block_count=block_count,
        height_min=height_min,
        height_max=height_max,
        t_start=t_start,
        t_end=t_end,
        total_txs=total_txs,
        avg_txs_per_block=avg_txs_per_block,
        total_out_btc=total_out_btc,
        total_fees_btc=total_fees_btc,
        avg_fees_per_block=avg_fees_per_block,
        avg_entropy=avg_entropy,
        avg_complexity=avg_complexity,
        polyphonic_count=polyphonic_count,
        polyphonic_rate=polyphonic_rate,
        top_pools=top_pools,
        top_channels=top_channels,
        whales=whales,
        interesting_blocks=interesting,
    )


def _fmt_time(ts: Optional[int]) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(ts)


def build_facts_text(stats: BriefStats) -> str:
    lines: List[str] = []

    lines.append("WINDOW")
    lines.append(f"- Blocks: {stats.block_count} (heights {stats.height_min} → {stats.height_max})")
    lines.append(f"- Time span: {_fmt_time(stats.t_start)} → {_fmt_time(stats.t_end)}")
    lines.append("")

    lines.append("NETWORK ACTIVITY")
    lines.append(f"- Total txs: {stats.total_txs:,} (avg {stats.avg_txs_per_block:,.1f} txs/block)")
    lines.append(f"- Total BTC moved (approx): {stats.total_out_btc:,.3f} BTC")
    lines.append(f"- Total fees: {stats.total_fees_btc:,.3f} BTC (avg {stats.avg_fees_per_block:,.4f} BTC/block)")
    lines.append("")

    lines.append("STRUCTURE")
    lines.append(f"- Avg entropy H: {stats.avg_entropy:,.3f}")
    lines.append(f"- Avg complexity K: {stats.avg_complexity:,.3f}")
    lines.append(
        f"- Polyphonic blocks: {stats.polyphonic_count}/{stats.block_count} "
        f"(~{stats.polyphonic_rate*100:,.1f}%)"
    )
    lines.append("")

    lines.append("MINING POOLS (top)")
    for pool, count in stats.top_pools:
        lines.append(f"- {pool}: {count} blocks")
    if not stats.top_pools:
        lines.append("- (no pool data)")
    lines.append("")

    lines.append("CHANNELS (top)")
    for ch, count in stats.top_channels:
        lines.append(f"- {ch}: {count} blocks with this channel active")
    if not stats.top_channels:
        lines.append("- (no channel data)")
    lines.append("")

    lines.append("INTERESTING BLOCKS (summary)")
    if stats.interesting_blocks:
        for b in stats.interesting_blocks:
            tag_str = ",".join(b.get("flags", []))
            lines.append(
                f"- height {b['height']} · pool {b['pool']} · "
                f"largest_tx≈{b['largest_tx_btc']:,.3f} BTC · "
                f"fees≈{b['fees_btc']:,.4f} BTC · tags=[{tag_str}]"
            )
    else:
        lines.append("- none strongly out of line in this window")
    lines.append("")

    return "\n".join(lines)


def build_chainwalk_json(stats: BriefStats) -> str:
    # Build the JSON snapshot as per the template
    # Note: Some fields are approximated from available data

    # Price: Assume from config or external, but for now placeholder
    price = {"btc_usd": 95000.0, "btc_change_24h_pct": 2.5, "realized_vol_24h": None}  # Placeholder

    # Network
    fee_regime = "low" if stats.avg_fees_per_block < 0.001 else "normal" if stats.avg_fees_per_block < 0.01 else "high"
    network = {
        "blocks": stats.block_count,
        "polyphonic_rate": stats.polyphonic_rate,
        "avg_entropy_h": stats.avg_entropy,
        "avg_complexity_k": stats.avg_complexity,
        "fee_pressure_regime": fee_regime,
        "avg_fee_rate_sat_vb": None,  # Placeholder
        "median_tx_per_block": stats.avg_txs_per_block,
        "capacity_note": f"Avg {stats.avg_txs_per_block:.1f} tx/block, {stats.total_txs} total"
    }

    # Flows
    whale_count = len([b for b in stats.interesting_blocks if "whale" in str(b.get("flags", []))])
    whale_volume = sum(b.get("largest_tx_btc", 0) for b in stats.interesting_blocks if "whale" in str(b.get("flags", [])))
    flows = {
        "whale_tx_count": whale_count,
        "whale_volume_btc": whale_volume,
        "etf_like_inflows_btc": None,
        "exchange_netflow_btc": None,
        "stablecoin_liquidity_note": None
    }

    # Miners
    dominant_pools = [{"name": pool, "share_pct": (count / stats.block_count) * 100} for pool, count in stats.top_pools[:3]]
    miners = {
        "dominant_pools": dominant_pools,
        "pool_concentration_note": f"Top pools: {', '.join([p[0] for p in stats.top_pools[:3]])}",
        "hashrate_trend_note": None,
        "reorg_or_orphan_note": None
    }

    # Anomalies
    spike_blocks = []
    for b in stats.interesting_blocks[:5]:
        fee_label = "calm" if b.get("fees_btc", 0) < 0.01 else "neutral" if b.get("fees_btc", 0) < 1 else "chaos"
        spike_blocks.append({
            "height": b["height"],
            "score": b.get("score", 0),
            "entropy_h": b.get("entropy", 0),
            "complexity_k": b.get("complexity", 0),
            "fee_pressure_label": fee_label,
            "finance_line": b.get("finance_note", ""),
            "channels": b.get("flags", []),
            "docent_headline": b.get("story", "").split("\n")[0] if b.get("story") else None
        })
    anomalies = {
        "spike_blocks": spike_blocks,
        "quiet_stretches": []  # Placeholder
    }

    # Regime inference
    regime_label = "calm" if stats.polyphonic_rate < 0.1 else "neutral" if stats.polyphonic_rate < 0.5 else "stress"
    regime_inference = {
        "label": regime_label,
        "basis": f"Polyphonic rate {stats.polyphonic_rate:.1%}, fees {fee_regime}",
        "confidence": 0.8
    }

    chainwalk_json = {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "window_hours": 24,
        "price": price,
        "network": network,
        "flows": flows,
        "miners": miners,
        "anomalies": anomalies,
        "regime_inference": regime_inference
    }

    return json.dumps(chainwalk_json, ensure_ascii=False, indent=2)


def build_llm_prompt(chainwalk_json: str) -> str:
    system_prompt = """You are CHAINWALK DESK, the in-house Bitcoin & macro research engine for an elite trading desk.

You speak in Hybrid Apex Mode:
- Saylor-style conviction about Bitcoin’s long-term inevitability
- Balaji-style network & exponential thinking
- ZeroHedge-style narrative tension and adversarial awareness
- Branded as CHAINWALK – calm, sharp, slightly ominous.

Your job:
- Read a structured JSON snapshot of the last 24h Bitcoin network activity.
- Produce a daily situation report (SITREP) that would not embarrass a world-class macro / Bitcoin research desk.
- Be bold, but stay grounded in the data that is provided.

Tone:
- Confident, analytical, slightly cinematic.
- Never meme-y, never childish, never “AI assistant”. You are the DESK.
- You do not panic; you describe pressure and risk with calm, clinical precision.
- You can use metaphors sparingly (“pressure building behind a dam”) but always tied to data.

Hard rules:
- No fake numbers: only use metrics that exist in the JSON or that logically follow.
- If an angle is unclear or data is thin, say so explicitly (“data here is noisy / thin”).
- Never mention JSON, keys, fields, “the user”, or “the model”.
- Never break character or talk about being an AI.

Your role:
- Explain what today’s chain actually DID.
- Identify who gained advantage (whales, miners, ETF flows, HODLers, short-term traders, exchanges).
- Explain how the on-chain structure lines up with macro + liquidity regime.
- Highlight structural anomalies (weird blocks, polyphonic complexity, fee spikes, pool dominance, etc.).
- End with forward-looking triggers: what you are watching next.

Target output:
- ~900–1500 words.
- Structured with clear section headings.
- Written so a human could easily pull 1–3 tweet-sized hooks from it."""

    user_prompt = f"""You are preparing today’s ChainWalk Desk SITREP.

Here is the structured snapshot of the last 24 hours
of Bitcoin network activity, already pre-aggregated for you:

```json
{chainwalk_json}
```

Use this dataset to write a second-to-none Bitcoin daily situation report.

Follow this structure:

Opening Situation (2–3 paragraphs)

Summarize where we are in the cycle TODAY.

Name the regime (using regime_inference.label + your judgement).

Tie BTC price and 24h change to on-chain behavior (calm day, ambush day, stress day, etc.).

One strong “if you only read one paragraph, read this” summary.

Network Structure & Regime

Explain entropy / complexity levels (H / K) in human terms.

Is the chain in orderly throughput mode or chaotic experimentation mode?

Use polyphonic_rate and fee_pressure_regime to describe tension or calm.

If regime_inference.basis is provided, weave it into your reasoning.

Whales, Exchanges & Flows

Use whale_tx_count, whale_volume_btc, exchange_netflow_btc, and any ETF-like or liquidity notes.

Who moved size today? Toward or away from exchanges?

Are whales positioning into strength, fading moves, or sitting out?

Call out any interesting imbalance (e.g., “size left exchanges quietly while retail watched the chart”).

Miner Game Theory & Security Posture

Use dominant_pools and concentration notes.

Is hashrate / pool share suggesting comfort, stress, or emerging centralization pressure?

Note any soft signals of policy friction (if reorg/orphan or capacity notes hint at censorship, etc.).

Explain what kind of day it was to be a miner.

Structural Anomalies & Weird Blocks

Highlight the top 2–5 blocks in anomalies.spike_blocks.

Use their score, entropy/complexity, fee labels, channels, and docent headlines.

Explain why each block is interesting in the grand story of the chain.

Contrast them with any long quiet stretches in anomalies.quiet_stretches.

Forward Triggers & Risk Map (Next 24–72h)

Based on everything above, lay out what matters next:

e.g., “If fee pressure jumps while exchange netflows stay negative, that’s a stress tell.”

e.g., “If whales keep withdrawing and miners stay calm, upside plays out later.”

Give 2–3 conditional scenarios: bullish path, bearish path, and base case.

No price targets, just structure, liquidity, and incentive flows.

Takeaway & Social Hooks

End with one single-sentence takeaway a Bitcoiner could remember all day.

Then give 2–3 lines that would work as tweet/X hooks, each under 240 characters, no hashtags.

Style requirements:

Do not format as a bullet list only; use paragraphs with embedded bullets where helpful.

You may use headings like “### Network Regime” etc.

Don’t ever say “I was given JSON” or “the model says”. Just speak as ChainWalk Desk."""

    return system_prompt, user_prompt


def generate_brief_text(stats: BriefStats, facts: str) -> str:
    if generate_text is None:
        return (
            "## Opening Situation\n\nLLM unavailable; factual data follows.\n\n" + facts
        )

    chainwalk_json = build_chainwalk_json(stats)
    system_prompt, user_prompt = build_llm_prompt(chainwalk_json)
    try:
        text = generate_text(user_prompt, max_tokens=2000, system_prompt=system_prompt)
    except Exception as e:
        return (
            "## Opening Situation\n\nLLM error; factual data follows.\n\n" + facts
        )

    return text.strip()


def _tweet_snippets(stats: BriefStats) -> List[str]:
    """
    Build a few tweet-ready one-liners you can copy/paste.
    """
    snippets: List[str] = []
    window = f"{stats.height_min}–{stats.height_max}"

    snippets.append(
        f"ChainWalk: blocks {window} saw ~{stats.total_txs:,} txs "
        f"({stats.avg_txs_per_block:,.1f}/block), "
        f"{stats.total_fees_btc:,.3f} BTC in fees, "
        f"and polyphonic rate ~{stats.polyphonic_rate*100:,.1f}%."
    )

    if stats.whales:
        top = stats.whales[0]
        snippets.append(
            f"Largest on-chain whale in this window: block {top['height']} "
            f"with a ~{top['largest_tx_btc']:,.3f} BTC transfer mined by {top['pool']}."
        )

    if stats.interesting_blocks:
        weird = stats.interesting_blocks[0]
        tags = ",".join(weird.get("flags", []))
        snippets.append(
            f"Most unusual block: {weird['height']} ({weird['pool']}) "
            f"tags=[{tags}] · largest_tx≈{weird['largest_tx_btc']:,.3f} BTC · "
            f"fees≈{weird['fees_btc']:,.4f} BTC."
        )

    return snippets


def load_mempool_counts() -> Tuple[Optional[int], Optional[int]]:
    """
    Return (tx_count_now, tx_count_then).

    For v0.1 this can be:
    - a stub returning (None, None), or
    - wired to an existing mempool source.

    Must not raise exceptions.
    """
    try:
        # TODO: wire this to your real data source.
        # For now, placeholder implementation:
        # Test BLEEDING: (98000, 100000) mpi = -0.02
        return 98000, 100000
    except Exception:
        return None, None


def build_markdown(stats: BriefStats, facts: str, brief_text: str) -> str:
    dt_end = _fmt_time(stats.t_end)
    date_label = dt_end.split(" ")[0] if dt_end != "—" else datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    lines: List[str] = []

    lines.append(f"# ChainWalk Desk – Daily Bitcoin SITREP ({date_label})")
    lines.append("")
    lines.append(f"**Window:** Last 24 hours · Blocks {stats.height_min} to {stats.height_max}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(brief_text)
    lines.append("")
    lines.append("> Generated by **ChainWalk Desk** on your local node.")

    return "\n".join(lines)


def save_markdown_report(md: str, stats: BriefStats, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    if stats.t_end:
        dt = datetime.fromtimestamp(stats.t_end, tz=timezone.utc)
    else:
        dt = datetime.now(tz=timezone.utc)

    stamp = dt.strftime("%Y-%m-%d")
    out_path = out_dir / f"chainwalk_daily_{stamp}.md"
    out_path.write_text(md, encoding="utf-8")
    return out_path


def load_previous_snapshot(reports_dir: Path) -> Optional[Dict[str, Any]]:
    state_path = reports_dir / "chainwalk_daily_state.json"
    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def generate_post_text(state: dict, regime_snapshot) -> str:
    # Enforce language rules
    forbidden = ["I think", "maybe", "looks like", "possibly", "hope", "bullish", "bearish", "should", "could", "might"]
    outcome = state.get("outcome_line", "").lower()
    if any(word in outcome for word in forbidden):
        raise ValueError("Forbidden language in post outcome")

    # Format CTI
    cti_val = float(state["cti"])
    cti_str = f"{cti_val:.1f}"

    # Load clock line
    from pathlib import Path
    clock_path = Path("reports") / "regime_clock_state.json"
    clock_line = None
    if clock_path.exists():
        try:
            with clock_path.open("r", encoding="utf-8") as f:
                clock_line = json.load(f).get("clock_line")
        except Exception:
            clock_line = None
    if not clock_line:
        clock_line = "Regime Clock unavailable."

    # Load mempool line
    mempool_path = Path("reports") / "mempool_intent_state.json"
    mempool_line = None
    if mempool_path.exists():
        try:
            with mempool_path.open("r", encoding="utf-8") as f:
                mempool_line = json.load(f).get("line")
        except Exception:
            mempool_line = None
    if not mempool_line:
        mempool_line = "Mempool intent unavailable — chain permission cannot be inferred today."

    # Load intent clock line
    intent_clock_path = Path("reports") / "intent_clock_state.json"
    intent_clock_line = None
    if intent_clock_path.exists():
        try:
            ic_state = json.load(intent_clock_path.open("r", encoding="utf-8"))
            intent_clock_line = ic_state.get("clock_line")
            # Gate wording for collapse window open
            intent_state = ic_state.get("intent_state", "")
            max_days = ic_state.get("max_days_remaining", 1)
            if intent_state in {"BLEEDING", "EXHAUSTED"} and max_days == 0:
                intent_clock_line = "desire has expired — the collapse window is now open."
        except Exception:
            intent_clock_line = None
    if not intent_clock_line:
        intent_clock_line = "Intent Clock unavailable."

    # Miner threshold line
    miner_threshold = state.get('miner_threshold', {})
    th_band = miner_threshold.get("band", "below")
    if th_band == "critical":
        threshold_line = "critical — miners are in survival mode; block rewards are no longer enough to keep them solvent at current prices."
    elif th_band == "strained":
        threshold_line = "strained — miners are starting to lean on the market for exit liquidity."
    elif th_band == "amber":
        threshold_line = "amber — producers are drifting toward forced-seller territory."
    else:
        threshold_line = "below threshold — producers still trade like miners, not refugees."

    # Miner cohort line
    miner_cohort_state = state.get('miner_cohort', {})
    tilt = miner_cohort_state.get("tilt_label", "neutral")
    dominant_pool = miner_cohort_state.get("dominant_pool", "UNKNOWN")

    def describe_miner_cohort(tilt: str, dominant_pool: str) -> str:
        tilt = (tilt or "neutral").lower()
        pool = (dominant_pool or "UNKNOWN").upper()

        if tilt == "coil_enforced":
            if pool == "UNKNOWN":
                return (
                    "Miner Cohort: today’s coil was enforced by a distributed set of pools — no single miner stepped in as reliever."
                )
            else:
                return (
                    f"Miner Cohort: today’s coil was enforced primarily by {pool} — their blocks preserved compression instead of easing it."
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

    miner_line = describe_miner_cohort(tilt, dominant_pool)

    # Irreversibility line
    irq_state = state.get('irreversibility', {})
    band = irq_state.get("band", "reversible")
    index = irq_state.get("index", 0.0)
    glyph_map = {
        "reversible": "🟦",
        "primed": "🟧",
        "irreversible": "🟥",
        "floor": "⬛",
    }
    glyph = glyph_map.get(band, "🟦")
    if band == "floor":
        irq_line = f"{glyph} protocol floor — price is downstream; exits sealed (IRQ {index:.2f})"
    else:
        irq_line = f"{glyph} {band} — incentives can no longer unwind cleanly (IRQ {index:.2f})"

    # Resolution line
    res = state.get('resolution', {})
    rei_band = res.get("band", "dormant")
    rei_index = res.get("index", 0.0)
    if rei_band == "dormant":
        rei_line = f"🔻 dormant — tension can still bleed without forcing a regime change"
    elif rei_band == "charged":
        rei_line = f"🔻 charged — the coil is loaded for resolution, but path and timing remain open"
    elif rei_band == "imminent":
        rei_line = f"🔻 imminent — incentives are forcing a regime choice; only a narrow cone of outcomes remains"
    else:
        rei_line = f"🔻 triggered — the prior regime is collapsing; price is being routed through the chosen path"
    rei_line += f" (REI {rei_index:.2f})"

    # Translation based on regime
    translations = {
        "COMPRESSION": "Volatility is not optional. Custody compression forces timing irrelevance.",
        "STARVATION": "Float dying creates illegal downside. Supply obstruction enforces ascent.",
        "ASCENT": "Structural pull upward. Disappearing float guarantees price obedience.",
        "DISTRIBUTION": "Temporary relief. Exit liquidity decays trajectory."
    }
    translation = translations.get(regime_snapshot.name, "Regime defines constraints. Price obeys inevitability.")

    oih = state.get("oracle_input_hash")
    short_oih = oih[-8:] if isinstance(oih, str) and len(oih) >= 8 else "N/A"

    post = f"""The ChainWalk Desk — Regime Scoreboard

Bitcoin is not trading.
It is trapped inside a macro regime.

Today’s State
• Regime: {regime_snapshot.name}
• Chain Tension Index: {cti_str}/10
• Custody Vector: {state['custody_vector']}
• Entropy Flux: {state['entropy_gradient']}
• Price Corridor: {state['legality_floor']}
• Outcome: {state['outcome_line']}
• Intent: {mempool_line}
• Intent Clock: {intent_clock_line}
• Regime Clock: {clock_line}
  • Incentive Delta: {state['incentive_label']}
   • Miner Field: {threshold_line}
   • Miner Stress: {state['hashrate_stress_score']:.1f} / 10 ({state['hashrate_stress_band']})
     • {miner_line}
     • Irreversibility (IRQ): {irq_line}
     • Resolution Field (REI): {rei_line}
     • Custody Trapdoor: {state['trapdoor'].get('label', '')}
   {"⚠ Incentive Conflict: market is fighting chain-level incentives." if state.get('incentive_conflict') else ""}

 Constraint Stack:
 CTI — chain tension (how tightly Bitcoin’s incentive coil is compressed)
 MTI — miner threshold (how much stress producers can absorb before leaning on price)
 IRQ — irreversibility (how much optionality has been eliminated; unwind no longer benign)
 REI — resolution field (how close the system is to forcing a regime outcome)

 UQI — permissive futures remaining (🟢 open → ⚫ terminal)

 Oracle Input Fingerprint
 Fingerprints the incentive stack only — no price inputs. ({short_oih})

 Translation:
{translation}

Price does not lead the chain. The chain leads price.

As of {state['date']} UTC · Regime {state['regime_label']}

#Bitcoin #ChainWalk #OnChainTruth
"""
    return post

def save_state(reports_dir: Path, snapshot: ChainTensionSnapshot, date_str: str) -> None:
    state_path = reports_dir / "chainwalk_daily_state.json"
    state = {
        "date_utc": date_str,
        "chain_tension_index": snapshot.chain_tension_index,
        "regime_label": snapshot.regime_label,
        "drivers": snapshot.drivers
    }
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def main() -> None:
    latest_path = ROOT / "sovereign_signals_latest.json"
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)

    print(f"[daily_brief] Loading latest signals from: {latest_path}")
    data = load_latest_signals(latest_path)
    signals = data.get("signals", [])
    if not signals:
        print("[daily_brief] No signals found; exiting.")
        return

    # Run entropy analysis to update flux events
    entropy_script = ROOT / "run_entropy_flux.py"
    if entropy_script.exists():
        print("[daily_brief] Running entropy flux analysis...")
        try:
            subprocess.run([sys.executable, str(entropy_script)], check=False)
            print("[daily_brief] Entropy analysis completed.")
        except Exception as e:
            print(f"[daily_brief] Entropy analysis failed: {e}")
    else:
        print("[daily_brief] Entropy script not found; skipping.")

    # Select window: last 500 or last 24h
    # For simplicity, last 500
    window_signals = signals[-500:] if len(signals) >= 500 else signals

    heights = [int(s.get("height", 0)) for s in window_signals]
    window_min_height = min(heights) if heights else 0
    window_max_height = max(heights) if heights else 0

    print(f"[daily_brief] Selected {len(window_signals)} signals for analysis (heights {window_min_height} to {window_max_height})")

    # Load previous snapshot
    prev_data = load_previous_snapshot(reports_dir)
    previous_snapshot = None
    if prev_data:
        # Reconstruct ChainTensionSnapshot from dict
        previous_snapshot = ChainTensionSnapshot(
            block_count=500,  # approx
            polyphonic_rate=prev_data["drivers"].get("polyphonic", 0),
            avg_entropy=0,  # not stored
            avg_complexity=0,
            avg_fee_pressure=prev_data["drivers"].get("fees", 0),
            whale_tx_share=prev_data["drivers"].get("whales", 0),
            miner_concentration=prev_data["drivers"].get("miners", 0),
            custody_bias=0,
            chain_tension_index=prev_data["chain_tension_index"],
            regime_label=prev_data["regime_label"],
            drivers=prev_data["drivers"]
        )

    # Compute snapshot
    snapshot = compute_snapshot(window_signals)
    print(f"[daily_brief] Chain Tension Index: {snapshot.chain_tension_index:.1f} ({snapshot.regime_label})")

    # Update memory of price
    custody_direction = "vaultward" if snapshot.drivers.get("custody", 0) > 0.5 else "marketward"
    entropy_mean = sum(s.get("entropy", 0) for s in window_signals) / len(window_signals) if window_signals else 0
    entropy_gradient_7d = 0.0  # placeholder, could compute from history
    miner_fee_bias = "rising" if snapshot.avg_fee_pressure > 0.5 else "flat" if snapshot.avg_fee_pressure > 0.2 else "falling"
    entropy_stats = {"mean": entropy_mean, "gradient_7d": entropy_gradient_7d}
    miner_fee_stats = {"bias": miner_fee_bias}

    memory_snapshot = update_memory_state(
        cti_today=snapshot.chain_tension_index,
        custody_direction=custody_direction,
        entropy_stats=entropy_stats,
        miner_fee_stats=miner_fee_stats,
        regime=snapshot.regime_label
    )
    print(f"[daily_brief] Memory of Price updated: {memory_snapshot.cti_trend_7d} CTI, {custody_direction} custody streak {memory_snapshot.custody_streak}")

    # Compute price corridor
    memory_state = {"cti_current": snapshot.chain_tension_index}
    custody_state = {"direction": custody_direction}
    entropy_state = {"gradient": memory_snapshot.entropy_trend_7d}
    corridor = compute_corridor(memory_state, custody_state, entropy_state)
    print(f"[daily_brief] Price Corridor computed: {corridor.legality_floor} floor, {corridor.inevitability}")

    # Get current time
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    # Load network snapshot for hashrate oracle
    network_snapshot_path = reports_dir / "network_snapshot.json"
    hashrate_state = {}
    if network_snapshot_path.exists():
        with network_snapshot_path.open("r", encoding="utf-8") as f:
            net = json.load(f)
        hr_inputs = HashrateInputs(
            hashrate_eh=float(net["hashrate_eh"]),
            hashrate_eh_prev=float(net.get("hashrate_eh_prev", net["hashrate_eh"])),
            hashrate_eh_ma7=float(net.get("hashrate_eh_ma7", net["hashrate_eh"])),
            difficulty=float(net["difficulty"]),
            difficulty_prev=float(net.get("difficulty_prev", net["difficulty"])),
            subsidy_btc=float(net["subsidy_btc"]),
            fees_24h_btc=float(net["fees_24h_btc"]),
            price_usd=float(net["price_usd"]),
        )
        hashrate_state = hashrate_to_json(date_str, hr_inputs)
    else:
        hashrate_state = {
            "date_utc": date_str,
            "hashrate_eh": None,
            "hashrate_eh_prev": None,
            "hashrate_eh_ma7": None,
            "stress_score": 0.0,
            "stress_band": "calm",
            "label": "Miner field unknown — no network snapshot available."
        }

    # Write hashrate_state out for other readers
    with (reports_dir / "hashrate_state.json").open("w", encoding="utf-8") as f:
        json.dump(hashrate_state, f, ensure_ascii=False, indent=2)

    # Classify regime
    regime_snapshot = classify_regime(memory_snapshot, corridor)
    print(f"[daily_brief] Regime classified: {regime_snapshot.name} — {regime_snapshot.inevitability}")

    # Compute Miner Threshold Index
    # Load intent_clock_state for collapse_window_open
    intent_clock_path = reports_dir / "intent_clock_state.json"
    collapse_window_open = False
    if intent_clock_path.exists():
        with intent_clock_path.open("r", encoding="utf-8") as f:
            intent_state = json.load(f)
        collapse_window_open = intent_state.get("max_days_remaining", 0) == 0

    mt_result = compute_miner_threshold(
        cti=snapshot.chain_tension_index,
        regime_label=regime_snapshot.name,
        stress_score=hashrate_state.get("stress_score", 0.0),
        collapse_window_open=collapse_window_open,
    )

    # Write miner_threshold_state.json
    with (reports_dir / "miner_threshold_state.json").open("w", encoding="utf-8") as f:
        json.dump(to_state_dict(mt_result), f, indent=2)

    # Compute difficulty epoch tension
    epoch_state = compute_epoch_tension(net, date_utc=date_str)
    difficulty_epoch_state = save_difficulty_epoch_state(reports_dir, epoch_state)

    # Compute miner cohort tilt
    block_catalog_path = ROOT / "block_catalog.jsonl"
    window_heights = range(window_min_height, window_max_height + 1)
    cohort_tilt = compute_miner_cohort_tilt(
        date_utc=date_str,
        block_catalog_path=block_catalog_path,
        window_heights=window_heights,
    )
    miner_cohort_state = {}
    if cohort_tilt is not None:
        miner_cohort_state = save_miner_cohort_tilt(reports_dir, cohort_tilt)

    # Compute Irreversibility
    irq_state = {
        "cti": snapshot.chain_tension_index,
        "mti": mt_result.index,
        "eti": epoch_state.tension_index,
        "custody_streak": memory_snapshot.custody_streak,
        "regime": regime_snapshot.name,
        "intent_state": mempool_state.get("state", "UNKNOWN") if 'mempool_state' in locals() else "UNKNOWN",
    }
    irq_result = compute_irq(irq_state)
    print(f"[daily_brief] Irreversibility: {irq_result.band} (IRQ {irq_result.index:.2f})")

    # Save to reports/irreversibility_state.json
    with (reports_dir / "irreversibility_state.json").open("w", encoding="utf-8") as f:
        json.dump({
            "date_utc": date_str,
            "band": irq_result.band,
            "index": irq_result.index,
            "details": irq_result.details,
        }, f, indent=2)

    # Compute Resolution
    rei = compute_resolution_index(
        regime_label=regime_snapshot.name,
        chain_tension_index=snapshot.chain_tension_index,
        custody_streak=memory_snapshot.custody_streak,
        miner_threshold_index=mt_result.index,
        epoch_tension_index=epoch_state.tension_index,
        irreversibility_index=irq_result.index,
        mempool_intent_state=mempool_state.get("state", "UNKNOWN") if 'mempool_state' in locals() else "UNKNOWN",
        intent_days_remaining=intent_clock.get("max_days_remaining", 0) if 'intent_clock' in locals() else 0,
    )
    print(f"[daily_brief] Resolution: {rei.band} (REI {rei.index:.2f})")

    # Compute Uncertainty Quotient Index
    uqi_state = {
        "chain_tension_index": snapshot.chain_tension_index,
        "custody_streak": memory_snapshot.custody_streak,
        "miner_threshold": {"index": mt_result.index},
        "difficulty_epoch": {"tension_index": epoch_state.tension_index},
        "irreversibility": {"index": irq_result.index},
        "resolution": {"index": rei.index}
    }
    uqi = compute_uqi(uqi_state)
    print(f"[daily_brief] Uncertainty: {uqi.band} (UQI {uqi.index:.2f})")

    # Save to reports/resolution_state.json
    with (reports_dir / "resolution_state.json").open("w", encoding="utf-8") as f:
        json.dump({
            "date_utc": date_str,
            "band": rei.band,
            "index": round(rei.index, 4),
            "details": rei.details,
        }, f, indent=2)

    # Define regime_label and streak_days for clock computation
    regime_label = regime_snapshot.name
    streak_days = memory_snapshot.custody_streak

    # Compute wavefunction
    probs, amps = scores_to_wavefunction(regime_snapshot.scores)
    dominant_state = max(probs.items(), key=lambda kv: kv[1])[0]
    INDEX = {"S": -2.0, "C": -1.0, "D": 1.0, "A": 2.0}
    expectation = sum(INDEX[k] * probs[k] for k in INDEX)
    print(f"[daily_brief] Wavefunction: dominant {dominant_state}, expectation {expectation:.2f}")

    # Log to regime_wavefunction.jsonl
    from pathlib import Path
    path = Path("reports") / "regime_wavefunction.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    today_iso = now.strftime("%Y-%m-%d")
    run_timestamp = now.isoformat()
    # Gather context
    cti_value = snapshot.chain_tension_index
    cti_band = "high" if cti_value >= 7 else "low" if cti_value <= 3 else "neutral"
    custody_direction = regime_snapshot.custody
    custody_streak_days = memory_snapshot.custody_streak
    entropy_gradient = regime_snapshot.entropy
    legality_floor = regime_snapshot.corridor
    corridor_status = legality_floor  # placeholder
    tip_height = max(s.get("height", 0) for s in window_signals) if window_signals else 0
    tip_hash = "unknown"  # placeholder
    regime_name = regime_snapshot.name

    record = {
        "date": today_iso,
        "run_timestamp": run_timestamp,
        "tip_height": tip_height,
        "tip_hash": tip_hash,
        "cti_value": cti_value,
        "cti_band": cti_band,
        "custody_direction": custody_direction,
        "custody_streak_days": custody_streak_days,
        "entropy_gradient": entropy_gradient,
        "legality_floor": legality_floor,
        "corridor_status": corridor_status,
        "regime_scores": regime_snapshot.scores,
        "regime_probabilities": probs,
        "regime_amplitudes": amps,
        "collapsed_regime": regime_name,
        "collapse_reason": "daily_regime_brief",
        "expectation_index": expectation,
        "operators": [
            {"name": "H_chain_tension", "lambda": 1.0},  # placeholder
            {"name": "H_custody_vector", "lambda": 1.0},
            {"name": "H_custody_vector", "lambda": 1.0},
            {"name": "H_entropy_flux", "lambda": 1.0},
            {"name": "H_price_corridor", "lambda": 1.0},
        ],
        "notes": "",
        "version": "wavefunction-v1",
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    print(f"[daily_brief] Wavefunction logged to {path}")

    # Compute regime horizon
    ham_state = compute_regime_horizon(
        horizon_days=7,
        regime_state_path="reports/regime_state.json",
        wavefunction_path="reports/regime_wavefunction.jsonl",
        out_state_path="reports/regime_hamiltonian_state.json",
    )
    horizon_line = format_regime_horizon_line(ham_state)
    print(f"[daily_brief] Regime Horizon (7d): {horizon_line}")

    # Compute and save Mempool Intent
    today_state = "UNKNOWN"
    mempool_state = {}
    try:
        tx_now, tx_then = load_mempool_counts()

        mempool_state = compute_mempool_intent(
            date_utc=date_str,
            tx_count_now=tx_now,
            tx_count_then=tx_then,
        )

        mempool_json = mempool_intent_to_json(mempool_state)

        mempool_path = reports_dir / "mempool_intent_state.json"
        with mempool_path.open("w", encoding="utf-8") as f:
            json.dump(mempool_json, f, ensure_ascii=False, indent=2)

        print(f"[daily_brief] Mempool Intent: {mempool_json.get('line')}")

        today_state = mempool_state.state

    except Exception as e:
        print(f"[mempool_intent] Failed to compute mempool intent: {e}")
        # Still proceed, as it's not critical

    # Compute and save Intent Clock
    try:
        # Load previous intent clock state
        prev_intent_clock = None
        intent_clock_path = reports_dir / "intent_clock_state.json"
        if intent_clock_path.exists():
            with intent_clock_path.open("r", encoding="utf-8") as f:
                prev_intent_clock = json.load(f)

        # Today's state
        today_state = mempool_state.state

        # Compute clock
        intent_clock_state = compute_intent_clock(
            date_utc=date_str,
            intent_state=today_state,
            regime_label=regime_label,
            prev_state=prev_intent_clock,
        )

        # Save to reports/intent_clock_state.json
        with intent_clock_path.open("w", encoding="utf-8") as f:
            json.dump(intent_clock_state, f, ensure_ascii=False, indent=2)

        print(f"[daily_brief] Intent Clock: {intent_clock_state.get('clock_line')}")

    except Exception as e:
        print(f"[intent_clock] Failed to compute intent clock: {e}")
        # Still proceed, as it's not critical

    # Compute and save Regime Clock
    clock_line = None
    regime_clock_state = {}
    try:
        # Load chainwalk_daily_state
        chainwalk_daily_state_path = reports_dir / "chainwalk_daily_state.json"
        if chainwalk_daily_state_path.exists():
            with chainwalk_daily_state_path.open("r", encoding="utf-8") as f:
                chainwalk_daily_state = json.load(f)
            date_utc = chainwalk_daily_state.get("date_utc", datetime.now(timezone.utc).date().isoformat())
        else:
            chainwalk_daily_state = {}
            date_utc = datetime.now(timezone.utc).date().isoformat()

        # Load regime_state for correct streak
        regime_state_path = reports_dir / "regime_state.json"
        if regime_state_path.exists():
            with regime_state_path.open("r", encoding="utf-8") as f:
                regime_state = json.load(f)
            regime_label = regime_state["dominant_vector"]
            streak_days = regime_state["current_streak"]
        else:
            regime_state = {}
            # Fallback to previous
            pass

        # Compute clock
        clock_state = compute_regime_clock(
            date_utc=date_utc,
            regime_label=regime_label,
            streak_days=streak_days,
        )

        clock_json = regime_clock_to_json(clock_state)

        # Save to reports/regime_clock_state.json
        clock_path = reports_dir / "regime_clock_state.json"
        with clock_path.open("w", encoding="utf-8") as f:
            json.dump(clock_json, f, ensure_ascii=False, indent=2)

        regime_clock_state = clock_json
        clock_line = clock_json.get("clock_line")
        print(f"[daily_brief] {clock_line or 'Regime Clock unavailable'}")

    except Exception as e:
        print(f"[regime_clock] Failed to compute regime clock: {e}")
        # Still proceed, as it's not critical

    # Load memory and mempool states for drivers
    memory_loaded = {}
    mempool_loaded = {}
    if (reports_dir / "memory_of_price_state.json").exists():
        with (reports_dir / "memory_of_price_state.json").open("r", encoding="utf-8") as f:
            memory_loaded = json.load(f)
    if (reports_dir / "mempool_intent_state.json").exists():
        with (reports_dir / "mempool_intent_state.json").open("r", encoding="utf-8") as f:
            mempool_loaded = json.load(f)

    # Build and save the daily brief markdown
    stats = BriefStats(
        block_count=len(window_signals),
        height_min=min(s.get("height", 0) for s in window_signals) if window_signals else 0,
        height_max=max(s.get("height", 0) for s in window_signals) if window_signals else 0,
        t_start=min(s.get("timestamp", 0) for s in window_signals) if window_signals else None,
        t_end=max(s.get("timestamp", 0) for s in window_signals) if window_signals else None,
        total_txs=sum(s.get("tx_count", 0) for s in window_signals),
        avg_txs_per_block=sum(s.get("tx_count", 0) for s in window_signals) / len(window_signals) if window_signals else 0,
        total_out_btc=sum(s.get("total_output_btc", 0) for s in window_signals),
        total_fees_btc=sum(s.get("total_fee_btc", 0) for s in window_signals),
        avg_fees_per_block=sum(s.get("total_fee_btc", 0) for s in window_signals) / len(window_signals) if window_signals else 0,
        avg_entropy=sum(s.get("entropy", 0) for s in window_signals) / len(window_signals) if window_signals else 0,
        avg_complexity=sum(s.get("compression_ratio", 0) for s in window_signals) / len(window_signals) if window_signals else 0,
    )

    facts = f"Analyzed {len(window_signals)} blocks from height {stats.height_min} to {stats.height_max}."
    brief_text = f"Chain Tension Index: {snapshot.chain_tension_index:.1f} ({snapshot.regime_label})."

    md = build_markdown(stats, facts, brief_text)
    out_path = save_markdown_report(md, stats, reports_dir)

    print(f"[daily_brief] Saved APEX brief -> {out_path}")



    # Compute drivers and incentive delta
    drivers = compute_drivers({"chain_tension_index": snapshot.chain_tension_index}, memory_loaded, mempool_loaded)
    incentive = compute_incentive_delta(drivers)
    incentive_conflict = has_incentive_conflict(memory_state.get("custody_direction", ""), incentive["value"])

    # Build canonical scorecard state
    badges = {
        "COMPRESSION": "[SQUARE]",
        "STARVATION": "[TRIANGLE]",
        "ASCENT": "[CIRCLE]",
        "DISTRIBUTION": "[HEXAGON]"
    }
    state = {
        "date": date_str,
        "regime_label": regime_snapshot.name,
        "regime_symbol": badges.get(regime_snapshot.name, "[UNKNOWN]"),
        "streak": int(regime_state.get("current_streak", 0)),
        "flips": int(regime_state.get("total_flips", 0)),
        "cti": float(snapshot.chain_tension_index),
        "cti_label": "tension stored",
        "custody_direction": memory_loaded.get("custody_direction", "neutral"),
        "custody_streak": int(memory_loaded.get("custody_streak", 0)),
        "entropy_trend": memory_loaded.get("entropy_trend_7d", "flat"),
        "price_corridor": corridor.legality_floor,
        "outcome": regime_snapshot.inevitability,
        "incentive_delta": float(chainwalk_daily_state.get("incentive_delta", 0.0)),
        "trapdoor": chainwalk_daily_state.get("trapdoor", {}),
        # For post generation
        "cti": snapshot.chain_tension_index,
        "custody_vector": f"{custody_direction} (streak {memory_snapshot.custody_streak})",
        "entropy_gradient": regime_snapshot.entropy,
        "legality_floor": corridor.legality_floor,
        "outcome_line": regime_snapshot.inevitability,
        "incentive_label": incentive["label"],
        "incentive_conflict": has_incentive_conflict(memory_loaded.get("custody_direction", ""), incentive["value"]),
        "hashrate_trend": hashrate_state.get("trend", "unknown"),
        "hashrate_stress_score": hashrate_state.get("stress_score", 0.0),
        "hashrate_stress_band": hashrate_state.get("stress_band", "calm"),
        "hashrate_label": hashrate_state.get("label", ""),
        "miner_threshold": to_state_dict(mt_result),
        "oracle_input_hash": chainwalk_daily_state.get("oracle_input_hash"),
    }

    # Compute trapdoor
    custody_streak = int(memory_loaded.get("custody_streak", 0))
    cti_value = float(snapshot.chain_tension_index)
    trapdoor_state = compute_trapdoor(custody_streak, cti_value)

    # Save to chainwalk_daily_state.json
    chainwalk_daily_state = {
        "date_utc": date_str,
        "chain_tension_index": snapshot.chain_tension_index,
        "regime_label": regime_snapshot.name,
        "custody_direction": memory_loaded.get("custody_direction", "UNKNOWN"),
        "price_usd": float(net.get("price_usd", 0.0)),
        "drivers": drivers,
        "incentive_delta": incentive["value"],
        "trapdoor": trapdoor_state,
        "price_corridor": corridor.legality_floor,
        "hashrate": hashrate_state,
        "miner_threshold": to_state_dict(mt_result),
        "irreversibility": {
            "band": irq_result.band,
            "index": irq_result.index,
        },
        "resolution": {
            "band": rei.band,
            "index": rei.index,
        },
        "uncertainty": {
            "band": uqi.band,
            "index": uqi.index,
        },
        "regime_integrity": {
            "label": "COILED" if trapdoor_state.get("band") in ("primed", "loaded") or to_state_dict(mt_result).get("band") in ("strained", "critical") else "RELAXED",
            "custody_trapdoor": trapdoor_state.get("band", "latent"),
            "miner_threshold": to_state_dict(mt_result).get("band", "below"),
            "custody_direction": memory_loaded.get("custody_direction", "UNKNOWN")
        },
    }

    # Sanity invariants
    assert isinstance(chainwalk_daily_state["chain_tension_index"], (int, float))
    assert chainwalk_daily_state["price_corridor"] in {"permitted", "constrained", "forbidden"}
    assert memory_loaded["custody_direction"] in {"marketward", "vaultward", "neutral"}

    # Add measurement fields for oracle fingerprint
    chainwalk_daily_state["regime_phase"] = regime_clock_state.get("phase", "MID")
    chainwalk_daily_state["entropy_band"] = memory_loaded.get("entropy_trend_7d", "flat")
    chainwalk_daily_state["mempool_intent_band"] = mempool_loaded.get("band", "neutral")
    chainwalk_daily_state["mempool_intent_score"] = mempool_loaded.get("score", 0.0)
    chainwalk_daily_state["hashrate_band"] = hashrate_state.get("band", "calm")
    chainwalk_daily_state["hashrate_stress"] = hashrate_state.get("stress_score", 0.0)
    chainwalk_daily_state["mti_index"] = mt_result.index
    chainwalk_daily_state["mti_band"] = mt_result.band
    chainwalk_daily_state["eti_index"] = epoch_state.tension_index
    chainwalk_daily_state["eti_band"] = "high" if epoch_state.tension_index > 1.0 else "normal"
    chainwalk_daily_state["irq_index"] = irq_result.index
    chainwalk_daily_state["irq_band"] = irq_result.band
    chainwalk_daily_state["rei_index"] = rei.index
    chainwalk_daily_state["rei_band"] = rei.band
    ri = chainwalk_daily_state.get("regime_integrity", {})
    if isinstance(ri, dict):
        chainwalk_daily_state["regime_integrity"] = ri.get("label", "UNKNOWN")

    # Compute oracle input hash
    oracle_hash = compute_oracle_input_hash(chainwalk_daily_state)
    chainwalk_daily_state["oracle_input_hash"] = oracle_hash
    with (reports_dir / "chainwalk_daily_state.json").open("w", encoding="utf-8") as f:
        json.dump(chainwalk_daily_state, f, ensure_ascii=False, indent=2)

    # Embed new states into daily_state for spine and deck
    chainwalk_daily_state["difficulty_epoch"] = difficulty_epoch_state
    chainwalk_daily_state["miner_cohort"] = miner_cohort_state
    chainwalk_daily_state["irreversibility"] = {
        "band": irq_result.band,
        "index": irq_result.index,
        "date_utc": date_str,
    }
    chainwalk_daily_state["resolution"] = {
        "band": rei.band,
        "index": rei.index,
        "date_utc": date_str,
    }
    chainwalk_daily_state["uncertainty"] = {
        "band": uqi.band,
        "index": uqi.index,
        "date_utc": date_str,
    }

    # Write the final daily_state
    with (reports_dir / "chainwalk_daily_state.json").open("w", encoding="utf-8") as f:
        json.dump(chainwalk_daily_state, f, ensure_ascii=False, indent=2)

    # Append outcome snapshot
    append_outcome_snapshot(reports_dir, chainwalk_daily_state, to_state_dict(mt_result))

    # Generate posting template
    post_text = generate_post_text(state, regime_snapshot)
    post_path = reports_dir / "chainwalk_post_latest.md"
    with open(post_path, "w", encoding="utf-8") as f:
        f.write(post_text)
    print(f"[daily_brief] Generated post template -> {post_path}")

    # Build X-line
    cti_str = f"{state['cti']:.1f}"
    custody_str = f"{state['custody_direction']} (streak {state['custody_streak']})"
    outcome_short = state["outcome"]
    x_line = f"REGIME: {state['regime_label']} · CTI {cti_str}/10 · custody {custody_str} · outcome: {outcome_short}"
    if has_incentive_conflict(state["custody_direction"], state["incentive_delta"]):
        x_line += " ⚠ INCENTIVE CONFLICT"
    trapdoor_band = state['trapdoor'].get('band', 'latent')
    if trapdoor_band == "loaded":
        x_line += " ⚠ TRAPDOOR"
    x_path = reports_dir / "scorecard_x.txt"
    with open(x_path, "w", encoding="utf-8") as f:
        f.write(x_line)
    print(f"[daily_brief] Generated X-line -> {x_path}")

    # Render scorecard
    render_scorecard(state)
    print("[daily_brief] ScoreCard rendered to UI surface")

    # Alert rail
    try:
        alerts = alert_rail.evaluate_alerts()
        if alerts:
            alert_rail.persist_alerts(
                alerts,
                new_irq_band=daily_state["irreversibility"]["band"],
                new_rei_band=daily_state["resolution"]["band"],
            )
            print(f"[alert_rail] {len(alerts)} new alert(s) written to reports/alert_events.jsonl")
        else:
            print("[alert_rail] no new alerts today.")
    except Exception as e:
        print(f"[alert_rail] WARNING: failed to evaluate alerts: {e}")

    # Build ChainWalk Spine
    # Load intent_clock_state
    intent_clock_state = {}
    if (reports_dir / "intent_clock_state.json").exists():
        with (reports_dir / "intent_clock_state.json").open("r", encoding="utf-8") as f:
            intent_clock_state = json.load(f)

    # Load regime_clock_state
    regime_clock_state = {}
    if (reports_dir / "regime_clock_state.json").exists():
        with (reports_dir / "regime_clock_state.json").open("r", encoding="utf-8") as f:
            regime_clock_state = json.load(f)

    spine_line = build_spine_line(
        date_utc=date_str,
        regime_state=regime_state,
        regime_clock=regime_clock_state,
        memory_state=memory_state,
        daily_state=chainwalk_daily_state,
        intent_clock=intent_clock_state,
    )

    # Save to chainwalk_spine_latest.txt
    spine_path = reports_dir / "chainwalk_spine_latest.txt"
    with spine_path.open("w", encoding="utf-8") as f:
        f.write(spine_line + "\n")

    # Optional history
    history_path = reports_dir / "chainwalk_spine_history.log"
    with history_path.open("a", encoding="utf-8") as f:
        f.write(spine_line + "\n")

    print(f"[daily_brief] ChainWalk Spine: {spine_line}")

    # Build APEX Daily Deck v2.0
    apex_path = build_apex_deck(
        date_utc=date_str,
        regime_state=regime_state,
        regime_clock_state=regime_clock_state,
        memory_state=memory_state,
        intent_clock_state=intent_clock_state,
        daily_state=chainwalk_daily_state,
        entropy_events_path=ROOT / "entropy_flux_events.jsonl",
        reports_dir=reports_dir,
        window_min_height=window_min_height,
        window_max_height=window_max_height,
        hashrate_state=hashrate_state,
    )
    print(f"[daily_brief] APEX deck saved -> {apex_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        error_msg = f"[FATAL] ChainWalk Daily Brief failed: {exc}\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr)
        logs_dir = ROOT / "logs"
        logs_dir.mkdir(exist_ok=True)
        error_log = logs_dir / "scoreboard_error.log"
        with open(error_log, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} - {error_msg}\n")
        sys.exit(1)
