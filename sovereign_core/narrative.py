# sovereign_core/narrative.py
"""
Narrative + tagging engine for Sovereign Signals V8.

This module is the heart of your "AI Docent":

- classify_tags(block)            -> TagSet with .as_list()
- classify_cluster(block)         -> future hook (currently light stub)
- channels_human_labels(block)    -> human labels for channel keys
- make_block_story(block, premium=False)
      -> generates a block story
         * first via deterministic rules
         * then optionally enriched by your local LLM

If the LLM is not available for any reason, everything still works.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional

from core.llm_client import get_client


# ---------------------------------------------------------------------------
# Tagging helpers
# ---------------------------------------------------------------------------


@dataclass
class TagSet:
    tags: List[str]

    def as_list(self) -> List[str]:
        return list(self.tags)


def _fmt_approx(x: Optional[float]) -> Optional[str]:
    if x is None:
        return None
    try:
        if abs(x) >= 1000:
            return f"{x:,.1f}"
        return f"{x:,.3f}"
    except Exception:
        return None


def _coerce_float(val, default: Optional[float] = None) -> Optional[float]:
    try:
        if val is None:
            return default
        if isinstance(val, (int, float)):
            return float(val)
        return float(str(val))
    except Exception:
        return default


def _coerce_int(val, default: Optional[int] = None) -> Optional[int]:
    try:
        if val is None:
            return default
        if isinstance(val, (int, float)):
            return int(val)
        return int(str(val))
    except Exception:
        return default


def classify_tags(block: Mapping) -> TagSet:
    """
    Turn raw block fields into a thin layer of curator-style tags
    that the UI can render as turquoise pills.

    We keep it simple and robust: if a field is missing, we just
    skip that tag instead of raising.
    """
    tags: List[str] = []

    # Era / pool anchors
    era = (block.get("era_label") or block.get("era") or "unknown").lower()
    tags.append(f"era:{era}")

    pool = (block.get("pool") or block.get("pool_name") or "unknown").strip()
    if pool:
        tags.append(f"pool:{pool}")

    # Volume / entropy / complexity
    txs = _coerce_int(
        block.get("txs") or block.get("tx_count") or block.get("num_txs")
    )
    volume = _coerce_float(
        block.get("total_out_btc")
        or block.get("onchain_volume_btc")
        or block.get("volume_btc")
    )
    entropy = _coerce_float(block.get("entropy_h") or block.get("entropy"))
    complexity = _coerce_float(block.get("complexity_k") or block.get("complexity"))

    if txs is not None and txs > 2500:
        tags.append("volume:notable")
    if volume is not None and volume > 5000:
        tags.append("whale:block")

    if entropy is not None:
        if entropy >= 5.2:
            tags.append("entropy:elevated")
        elif entropy <= 4.4:
            tags.append("entropy:low")
        else:
            tags.append("entropy:normal")

    if complexity is not None:
        if complexity >= 1.06:
            tags.append("complexity:rich")
        else:
            tags.append("complexity:normal")

    # Channels: treat them as curated channel:* tags as-is
    chans: Iterable[str] = block.get("channels") or block.get("channel_keys") or []
    for ch in chans:
        ch_key = str(ch).strip()
        if not ch_key:
            continue
        tags.append(f"channels:{ch_key}")

    # Polyphonic marker
    if block.get("polyphonic"):
        tags.append("polyphonic")

    return TagSet(tags=tags)


def classify_cluster(block: Mapping) -> Dict[str, str]:
    """
    Placeholder for future 'cluster' semantics.

    Right now we just surface a couple of high-level flags the UI
    may want later. mirror_builder.py only calls this for side effects.
    """
    out: Dict[str, str] = {}

    era = (block.get("era_label") or block.get("era") or "unknown").lower()
    out["era_cluster"] = era

    txs = _coerce_int(
        block.get("txs") or block.get("tx_count") or block.get("num_txs")
    )
    if txs is not None:
        if txs > 4000:
            out["flow_cluster"] = "high_throughput"
        elif txs < 1000:
            out["flow_cluster"] = "quiet"
        else:
            out["flow_cluster"] = "normal"

    return out


def channels_human_labels(block: Mapping) -> Dict[str, str]:
    """
    Map internal channel keys (e.g. 'finance_whale_tx') to short
    human labels. Again, mirror_builder currently ignores the return
    value but we keep this tidy for future HUD usage.
    """
    mapping = {
        "header_tail_anomaly": "header tail anomaly",
        "script_pattern": "script pattern",
        "time_delta_weird": "time delta weird",
        "finance_whale_tx": "finance whale tx",
        "utxo_pressure": "utxo pressure",
    }

    chans: Iterable[str] = block.get("channels") or block.get("channel_keys") or []
    out: Dict[str, str] = {}
    for ch in chans:
        key = str(ch).strip()
        if not key:
            continue
        out[key] = mapping.get(key, key.replace("_", " "))
    return out


# ---------------------------------------------------------------------------
# Deterministic block story
# ---------------------------------------------------------------------------


def _deterministic_block_story(block: Mapping) -> str:
    """
    Old-school curated story: no LLM required.

    We keep this fairly close to what you've been seeing in V7:
    concise, structured, and numerically grounded.
    """
    height = _coerce_int(block.get("height"))
    era = (block.get("era_label") or block.get("era") or "unknown").lower()
    pool = (block.get("pool") or block.get("pool_name") or "unknown").strip()
    ts_iso = block.get("time_utc") or block.get("time_iso") or block.get("time")

    txs = _coerce_int(
        block.get("txs") or block.get("tx_count") or block.get("num_txs")
    )
    volume = _coerce_float(
        block.get("total_out_btc")
        or block.get("onchain_volume_btc")
        or block.get("volume_btc")
    )
    largest = _coerce_float(
        block.get("largest_tx_btc")
        or block.get("whale_tx_btc")
        or block.get("largest_btc")
    )

    entropy = _coerce_float(block.get("entropy_h") or block.get("entropy"))
    complexity = _coerce_float(block.get("complexity_k") or block.get("complexity"))

    chans: List[str] = list(
        block.get("channels") or block.get("channel_keys") or []
    )

    parts: List[str] = []

    # Opening sentence
    head = "This block"
    if height is not None:
        head = f"Block {height}"
    head += f" sits in the {era} regime"
    if pool and pool.lower() != "unknown":
        head += f", carved by {pool}"
    head += "."
    parts.append(head)

    # Timing
    if ts_iso:
        parts.append(f"It landed around {ts_iso} on-chain.")

    # Flow + whale structure
    seg_flow: List[str] = []
    if txs is not None:
        seg_flow.append(f"{txs:,} transactions")
    if volume is not None:
        v = _fmt_approx(volume)
        if v:
            seg_flow.append(f"~{v} BTC of on-chain volume")
    if largest is not None:
        l = _fmt_approx(largest)
        if l:
            seg_flow.append(f"a standout transfer near ~{l} BTC")

    if seg_flow:
        if len(seg_flow) == 1:
            parts.append(f"It carried {seg_flow[0]}.")
        else:
            parts.append(
                "It carried "
                + ", ".join(seg_flow[:-1])
                + f", and {seg_flow[-1]}."
            )

    # Entropy / complexity
    if entropy is not None or complexity is not None:
        desc_bits: List[str] = []
        if entropy is not None:
            if entropy >= 5.2:
                desc_bits.append("elevated entropy")
            elif entropy <= 4.4:
                desc_bits.append("low entropy")
            else:
                desc_bits.append("normal entropy")
        if complexity is not None:
            if complexity >= 1.06:
                desc_bits.append("rich complexity")
            else:
                desc_bits.append("normal complexity")

        if desc_bits:
            eh = f"H≈{entropy:.3f}" if entropy is not None else ""
            ck = f"K≈{complexity:.3f}" if complexity is not None else ""
            hk = " ".join([eh, ck]).strip()
            parts.append(
                f"Coinbase structure shows {', '.join(desc_bits)}"
                + (f" ({hk})." if hk else ".")
            )

    # Channels summary
    if chans:
        labels = [channels_human_labels(block).get(c, c.replace("_", " ")) for c in chans]
        parts.append(
            "From a curator's lens, it lights up channels such as "
            + ", ".join(labels)
            + "."
        )

    return " ".join(p.strip() for p in parts if p).strip()


# ---------------------------------------------------------------------------
# LLM-enriched story
# ---------------------------------------------------------------------------


_DOCENT_SYSTEM_PROMPT = (
    "You are a Bitcoin block desk analyst. "
    "Your job is to explain an individual block in the Bitcoin blockchain "
    "to a curious but non-technical visitor. "
    "Use clear, vivid language, but stay grounded in the factual inputs. "
    "Highlight what makes this block unusual in the chain "
    "(volume, whales, timing, entropy/complexity, channels). "
    "Keep it to 2–4 short paragraphs. "
    "Avoid repeating exact numbers more than once; interpret them instead."
)


def _build_llm_facts(block: Mapping, base_story: str) -> str:
    """
    Serialize the block into a compact fact sheet that the LLM can reason over.
    """
    height = _coerce_int(block.get("height"))
    era = block.get("era_label") or block.get("era") or "unknown"
    pool = block.get("pool") or block.get("pool_name") or "unknown"
    ts_iso = block.get("time_utc") or block.get("time_iso") or block.get("time")

    txs = _coerce_int(
        block.get("txs") or block.get("tx_count") or block.get("num_txs")
    )
    volume = _coerce_float(
        block.get("total_out_btc")
        or block.get("onchain_volume_btc")
        or block.get("volume_btc")
    )
    largest = _coerce_float(
        block.get("largest_tx_btc")
        or block.get("whale_tx_btc")
        or block.get("largest_btc")
    )

    entropy = _coerce_float(block.get("entropy_h") or block.get("entropy"))
    complexity = _coerce_float(block.get("complexity_k") or block.get("complexity"))

    chans: List[str] = list(
        block.get("channels") or block.get("channel_keys") or []
    )
    tagset = classify_tags(block).as_list()

    lines = [
        f"height: {height}" if height is not None else "height: unknown",
        f"era: {era}",
        f"pool: {pool}",
        f"time_utc: {ts_iso}",
        f"txs: {txs}",
        f"onchain_volume_btc: {volume}",
        f"largest_tx_btc: {largest}",
        f"entropy_h: {entropy}",
        f"complexity_k: {complexity}",
        f"channels: {', '.join(chans) if chans else 'none'}",
        f"tags: {', '.join(tagset) if tagset else 'none'}",
        "",
        "baseline_story:",
        base_story,
    ]

    return "\n".join(str(x) for x in lines)


def _detect_narrative_tone(block: Mapping) -> str:
    """
    Detect the narrative tone based on block signals.
    """
    channels = block.get("channels", {})
    pool = (block.get("pool") or "").lower()

    if channels.get("finance_whale_tx"):
        return "whale_transfer_pivot"
    if channels.get("finance_high_fees"):
        return "fee_compression_anomaly"
    if channels.get("header_tail_anomaly") or channels.get("time_delta_weird"):
        return "difficulty_echo_phase"
    if channels.get("utxo_pressure") or channels.get("finance_whale_tx"):
        return "custody_rotation"
    if pool in ["antpool", "foundry usa", "binance pool", "f2pool"]:
        return "syndicate_miner_block"
    return "neutral_throughput"


def _llm_enriched_story(block: Mapping, base_story: str) -> Optional[str]:
    """
    Try to get a richer narrative from the local LLM. Returns None on failure.
    """
    client = get_client()
    if not client.available():
        return None

    tone = _detect_narrative_tone(block)
    facts = _build_llm_facts(block, base_story)
    user_prompt = (
        "Here are structured facts about a single Bitcoin block.\n\n"
        f"{facts}\n\n"
        f"Interpret this block in the '{tone}' tone. "
        "What story does this block tell about Bitcoin’s enemies, incentives, and future? "
        "Write a short, vivid desk analyst interpretation. "
        "Do not invent specific numbers that aren't present, "
        "but you may interpret and characterize them (e.g. 'whale-sized', 'heavy throughput'). "
        "Focus on diagnosis, not description."
    )

    try:
        text = client.generate_text(
            prompt=user_prompt,
            system_prompt=_DOCENT_SYSTEM_PROMPT,
        )
        text = text.strip()
        if not text:
            return None
        return text
    except Exception:
        # Never let the UI break because of the LLM.
        return None


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def make_block_story(block: Mapping, premium: bool = False) -> str:
    """
    Main API used by mirror_builder.py.

    - Always computes a deterministic base_story.
    - If the LLM is available, tries to return an enriched story.
    - If anything fails, falls back to base_story.
    """
    base_story = _deterministic_block_story(block)

    # Only bother with LLM for "premium" or when we explicitly want
    # the full analyst treatment; you can flip this behaviour if you
    # want everything to be LLM-driven all the time.
    use_llm = True  # always try; we still gracefully fallback

    if use_llm:
        enriched = _llm_enriched_story(block, base_story)
        if enriched:
            return enriched

    return base_story
