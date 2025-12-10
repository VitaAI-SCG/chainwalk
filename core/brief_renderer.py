from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from core.regime_metrics import ChainTensionSnapshot
from core.llm_client import generate_text
from utils.memory_of_price import MemorySnapshot

Signal = Dict[str, Any]

def assert_conviction(line: str) -> str:
    weak = ["maybe", "possibly", "seems", "nothing unusual", "neutral", "typical", "appears", "suggests", "indicates"]
    if any(w in line.lower() for w in weak):
        raise ValueError("WEAK LANGUAGE DETECTED — VIOLATION OF APEX V4 CONVICTION RULE")
    return line

def get_miner_persona(pool: str) -> str:
    pool_lower = pool.lower()
    if "antpool" in pool_lower:
        return "Industrial China"
    elif "foundry" in pool_lower:
        return "Institutional US"
    elif "binance" in pool_lower:
        return "Global exchange vector"
    else:
        return "Independent miner"

def select_block_of_the_day(signals: List[Signal]) -> Dict[str, Any]:
    if not signals:
        return {}

    # Sort by master_score if exists, else by entropy + complexity + poly bonus
    def score_signal(s: Signal) -> float:
        ms = s.get("master_score")
        if ms is not None:
            return ms
        h = s.get("entropy_h") or s.get("entropy") or 0
        k = s.get("complexity_k") or s.get("complexity") or 0
        poly_bonus = 1.0 if s.get("polyphonic") else 0.0
        return h + k + poly_bonus

    best = max(signals, key=score_signal)

    return {
        "height": best["height"],
        "pool": best.get("pool", "unknown"),
        "persona": get_miner_persona(best.get("pool", "unknown")),
        "time_utc": datetime.utcfromtimestamp(best["timestamp"]),
        "entropy_h": best.get("entropy_h") or best.get("entropy") or 0.0,
        "complexity_k": best.get("complexity_k") or best.get("complexity") or 0.0,
        "fees_pct": best.get("fees_pct") or 0.0,
        "total_output_btc": best.get("total_output_btc") or 0.0,
        "largest_tx_btc": best.get("largest_tx_btc") or 0.0,
        "channels": best.get("channels", {}),
        "finance_note": best.get("finance_note") or "(no finance note provided)"
    }

def derive_regime_flip_narrative(snapshot: ChainTensionSnapshot, previous: Optional[ChainTensionSnapshot]) -> str:
    if not previous:
        return "No previous data; regime stability unknown."

    delta_cti = snapshot.chain_tension_index - previous.chain_tension_index
    if delta_cti > 0.8:
        return "Pressure building towards regime flip"
    elif delta_cti < -0.8:
        return "System exhaling; flip risk fading"
    else:
        return "Regime stable; watch drivers, not noise"

def render_apex_brief(
    date_utc: datetime,
    snapshot: ChainTensionSnapshot,
    signals: List[Signal],
    previous_snapshot: Optional[ChainTensionSnapshot] = None,
    memory_snapshot: Optional[MemorySnapshot] = None,
    horizon_line: Optional[str] = None,
) -> str:
    bod = select_block_of_the_day(signals)
    regime_flip = derive_regime_flip_narrative(snapshot, previous_snapshot)

    # LLM for narrative
    narrative_prompt = f"""
You are the senior analyst on the ChainWalk Desk, an elite Bitcoin macro desk.

You have COLLECTED the metrics already; do NOT invent numbers. Just interpret.

Write ONE cohesive paragraph (5–8 sentences) in a tone that blends:
- Michael Saylor conviction
- Balaji's systems thinking
- ZeroHedge's narrative tension
- and ChainWalk's calm, mathematical voice.

Facts you may reference:

- Chain Tension Index (0–10): {snapshot.chain_tension_index:.2f}
- Current regime: {snapshot.regime_label}
- Drivers:
  - Polyphonic rate: {snapshot.polyphonic_rate:.3f}
  - Fee pressure: {snapshot.avg_fee_pressure:.3f}
  - Whale share: {snapshot.whale_tx_share:.3f}
  - Miner concentration: {snapshot.miner_concentration:.3f}
  - Custody tension proxy: {snapshot.drivers.get("custody", 0.0):.3f}

- Block of the Day:
  - Height: {bod.get("height", 0)}
  - Pool: {bod.get("pool", "unknown")}
  - Entropy / Complexity: H={bod.get("entropy_h", 0):.2f} K={bod.get("complexity_k", 0):.2f}
  - Finance: txs: {bod.get("total_output_btc", 0):.3f} BTC total out, fees: {bod.get("fees_pct", 0):.4f}%, largest: {bod.get("largest_tx_btc", 0):.3f} BTC
  - Channels: {", ".join([k for k,v in bod.get("channels", {}).items() if v]) or "none"}

Rules:
- Do NOT give trading advice.
- Do NOT mention 'not financial advice'.
- No bullet lists, no headings, just a clean, flowing paragraph.
- Focus on explaining how today's tension profile fits into the bigger Bitcoin story.
"""
    ai_narrative = generate_text(narrative_prompt, max_tokens=380)
    ai_narrative = ai_narrative.encode('ascii', 'ignore').decode('ascii') if ai_narrative else "Narrative unavailable."

    # Viral quote - enforce conviction rule
    quote_prompt = f"""
You are writing a single, stand-alone sentence that could be posted on Twitter/X
by the ChainWalk Desk.

Summarize today's Bitcoin network state in ONE sentence with a causal chain and punch.
Must be tattoo-worthy, inevitable, not probabilistic.

Base it on:
- Chain Tension Index: {snapshot.chain_tension_index:.2f} ({snapshot.regime_label})
- Main drivers: polyphonic={snapshot.polyphonic_rate:.3f}, whales={snapshot.whale_tx_share:.3f}, miners={snapshot.miner_concentration:.3f}

Examples: “Bitcoin starves sellers and feeds time; every delay raises the exit price.”
“Miners don’t predict bull markets—they manufacture them.”

DO NOT mention 'ChainWalk', 'tweet', 'this report', or 'followers'.
Output ONLY the sentence, no quotes.
"""
    viral_quote = generate_text(quote_prompt, max_tokens=64).strip()
    viral_quote = viral_quote.encode('ascii', 'ignore').decode('ascii')  # strip unicode for Windows

    # Compute required variables with conviction
    custody_direction = "floating supply is dissolving into vaults" if snapshot.drivers.get("custody", 0) > 0.5 else "supply is sealed and cannot return to markets without price violence"
    desk_verdict_options = [
        "BITCOIN ASCENDANT",
        "BITCOIN COILED — IGNITION IMMINENT",
        "MARKET DELAYED — INEVITABILITY UNSCROLLED",
        "SUPPLY TRAP SET — EXIT PRICE UNKNOWN"
    ]
    desk_verdict = desk_verdict_options[int(snapshot.chain_tension_index) % len(desk_verdict_options)]  # map CTI to verdict
    assert_conviction(desk_verdict)

    cti_line = "forces compression" if snapshot.chain_tension_index > 5 else "accelerates collapse"
    macro_thesis = "Miners seal the rails while Wall Street waits for permission. That gap births the next parabola."
    regime_trigger = "entropy gradient compresses float"
    inevitable_endstate = "scarcity regime locks in"
    block_height = bod.get('height', 0)
    block_thesis = "This block participated in the supply starvation cycle."
    if bod.get('entropy_h', 0) < 3:  # low entropy
        block_thesis = "The silence itself is a weapon — whales accumulate in boredom."
    block_signal_bullet_1 = "Entropy forces miner adaptation."
    block_signal_bullet_2 = "Custody starves sellers."
    block_signal_bullet_3 = "Fees lock in dominance."

    # Miner futures with conviction
    antpool_future = "industrial capacity starves float"
    foundry_future = "institutional hash protects floor"
    viabtc_future = "rotation compresses volatility"

    custody_clock_line = custody_direction

    # Enforce conviction on key lines
    assert_conviction(viral_quote)
    assert_conviction(f"AntPool → {antpool_future}")
    assert_conviction(f"FoundryUSA → {foundry_future}")
    assert_conviction(f"ViaBTC → {viabtc_future}")
    assert_conviction(f"{regime_trigger} → {inevitable_endstate}")
    assert_conviction(custody_clock_line)

    # Build markdown per APEX V4 template
    lines = []
    lines.append("# 📡 CHAINWALK APEX — THE BITCOIN CONVICTION DESK")
    lines.append("")
    lines.append(f"CTI: {snapshot.chain_tension_index:.1f} — {cti_line}")
    lines.append(f"Custody Vector: {custody_direction}")
    lines.append(f"Desk Verdict: {desk_verdict}")
    lines.append("")
    lines.append("## Macro Inflection")
    lines.append(macro_thesis)
    lines.append("")
    lines.append("## Regime Flip Forecast")
    lines.append(f"{regime_trigger} → {inevitable_endstate}")
    lines.append("")
    lines.append(f"## Block of the Day — {block_height}")
    lines.append(block_thesis)
    lines.append(f"- {block_signal_bullet_1}")
    lines.append(f"- {block_signal_bullet_2}")
    lines.append(f"- {block_signal_bullet_3}")
    lines.append("")
    lines.append("## Miner Power Map")
    lines.append(f"AntPool → {antpool_future}")
    lines.append(f"FoundryUSA → {foundry_future}")
    lines.append(f"ViaBTC → {viabtc_future}")
    lines.append("")
    lines.append("## Custody Clock")
    lines.append(custody_clock_line)
    lines.append("")

    # MEMORY OF PRICE section
    if memory_snapshot:
        # Trajectory classification
        if memory_snapshot.cti_trend_7d == "rising" and memory_snapshot.custody_direction == "vaultward" and memory_snapshot.custody_streak >= 3:
            trajectory = "COILED ASCENT"
            trajectory_line = "CTI has risen and custody keeps draining into vaults; the chain is compressing future upside into a single unavoidable breakout."
        elif memory_snapshot.cti_trend_7d == "flat" and memory_snapshot.custody_streak < 3:
            trajectory = "STALLED FLOAT"
            trajectory_line = "CTI is treading water while custody drifts sideways; the chain is stalling, not resetting, and every extra day deepens the eventual move."
        else:
            trajectory = "EXHAUSTED CEILING"
            trajectory_line = "CTI is bleeding down as coins drift back toward markets; the chain is offloading weak hands before it can enforce a new regime."

        # CTI path
        prev_cti = memory_snapshot.cti_prev_7d if memory_snapshot.cti_prev_7d else memory_snapshot.cti_last
        cti_path_line = f"CTI marched from {prev_cti:.1f} → {memory_snapshot.cti_last:.1f} over 7 days; tension is {'building' if memory_snapshot.cti_trend_7d == 'rising' else 'bleeding' if memory_snapshot.cti_trend_7d == 'falling' else 'paused under strain'}."

        # Custody line
        if memory_snapshot.custody_direction == "vaultward":
            custody_line = f"Custody has flowed into vaults for {memory_snapshot.custody_streak} straight sessions; sellers are being deleted, not rotated."
        else:
            custody_line = f"Custody has leaked back toward markets for {memory_snapshot.custody_streak} days; any pop is feeding liquidity, not starving it yet."

        # Entropy line
        entropy_line = f"Entropy trend: {memory_snapshot.entropy_trend_7d} — miners are {'increasing structural complexity' if memory_snapshot.entropy_trend_7d == 'rising' else 'running minimal scripts' if memory_snapshot.entropy_trend_7d == 'falling' else 'holding pattern'}."

        # Fee line
        fee_line = f"Fee gravity: {memory_snapshot.miner_fee_trend} — fee share is {'pulling the network toward fee dominance' if memory_snapshot.miner_fee_trend == 'rising' else 'still subsidy-led'}."

        # Inevitable path
        if trajectory == "COILED ASCENT":
            inevitable_path_line = "With CTI climbing, custody locked in vaults, and entropy thickening, price cannot stay in this corridor; it will be forced higher as the float disappears."
        elif trajectory == "STALLED FLOAT":
            inevitable_path_line = "A flat CTI with vaultward custody is a loaded spring; every quiet day now lifts the eventual clearing price and removes soft exits."
        else:
            inevitable_path_line = "When CTI decays while coins leak back to market, the chain is exterminating tourists so it can later move in one direction without resistance."

        # Enforce conviction
        for line in [trajectory_line, cti_path_line, custody_line, entropy_line, fee_line, inevitable_path_line]:
            assert_conviction(line)

        lines.append("## MEMORY OF PRICE")
        lines.append("")
        lines.append(f"**Trajectory:** {trajectory_line}")
        lines.append("")
        lines.append(f"- CTI path: {cti_path_line}")
        lines.append(f"- Custody drift: {custody_line}")
        lines.append(f"- Entropy field: {entropy_line}")
        lines.append(f"- Miner fee gravity: {fee_line}")
        lines.append("")
        lines.append(f"**Inevitable path:** {inevitable_path_line}")
        lines.append("")

    lines.append("## Viral Quote")
    lines.append(f"**{viral_quote}**")

    return "\n".join(lines)