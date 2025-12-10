import hashlib
import json
import os
import time
from typing import Any, Dict, Optional

from .config import get_config
from .llm_client import generate_text

_cfg = get_config()
CACHE_PATH = os.environ.get("SOV_DOCENT_CACHE", "cache/docent_cache.jsonl")
MAX_AGE_SECS = int(os.environ.get("SOV_DOCENT_MAX_AGE_SECS", "31536000"))  # 1 year


def _key_for_block(block: Dict[str, Any]) -> str:
    h = block.get("height")
    pool = block.get("pool")
    txs = block.get("txs")
    total = block.get("total_out_btc") or block.get("total_out")
    largest = block.get("largest_btc") or block.get("largest")
    channels = ",".join(block.get("channels", []))
    basis = f"{h}|{pool}|{txs}|{total}|{largest}|{channels}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _read_cached(key: str) -> Optional[Dict[str, Any]]:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row.get("k") == key:
                    if time.time() - row.get("ts", 0) <= MAX_AGE_SECS:
                        return row
    except FileNotFoundError:
        pass
    return None


def _write_cached(key: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    row = {"ts": int(time.time()), "k": key, **payload}
    with open(CACHE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _fmt(v, unit="BTC"):
    if v is None:
        return "—"
    try:
        return f"{float(v):,.3f} {unit}"
    except Exception:
        return str(v)


def _finance_line(b: Dict[str, Any]) -> str:
    txs = b.get("txs")
    total = b.get("total_out_btc") or b.get("total_out")
    fees = b.get("fees_btc") or b.get("fees")
    largest = b.get("largest_btc") or b.get("largest")
    pct = b.get("fees_pct")
    if pct is not None:
        try:
            pct_val = float(pct)
            pct_str = f"{pct_val:0.000%}"
        except Exception:
            pct_str = str(pct)
    else:
        pct_str = "—"
    return (
        f"txs: {txs} · total out: {_fmt(total)} · "
        f"fees: {_fmt(fees)} ({pct_str}) · largest: {_fmt(largest)}"
    )


def _fallback_story(block: Dict[str, Any]) -> Dict[str, str]:
    """
    Cheap deterministic summary when LLM is disabled or call cap reached.
    No network calls, no cache writes.
    """
    height = block.get("height")
    pool = block.get("pool")
    era = block.get("era")
    time_utc = block.get("time")
    finance = _finance_line(block)
    channels = ", ".join(block.get("channels", [])) or "no special channels"
    h_val = block.get("entropy_h")
    k_val = block.get("complexity_k")

    headline = "Typical throughput block"
    text = (
        f"Block {height} in the {era} regime was mined by {pool} and looks like a "
        f"normal throughput block. It settled {finance.split('·')[1].strip()} with "
        f"entropy H≈{h_val} and complexity K≈{k_val}. Channels show "
        f"{channels}; nothing unusually extreme stands out for this block."
    )
    return {"headline": headline, "text": text}


def describe_block(block: Dict[str, Any]) -> Dict[str, str]:
    """
    Returns {'headline': str, 'text': str} for a block.

    Uses cache first; prompts the LLM only on a cache miss, and respects
    config/env for docent_enabled + max_calls.
    """
    key = _key_for_block(block)

    # 1) cache hit?
    cached = _read_cached(key)
    if cached and "headline" in cached and "text" in cached:
        return {"headline": cached["headline"], "text": cached["text"]}

    # 2) consult config for whether LLM is allowed
    cfg = get_config()
    docent_enabled = bool(cfg.get("docent_enabled", True))
    max_calls = int(cfg.get("docent_max_calls", 32))

    # global call counter (per-process)
    if not hasattr(describe_block, "_calls"):
        setattr(describe_block, "_calls", 0)

    calls = getattr(describe_block, "_calls")  # type: ignore[assignment]

    if (not docent_enabled) or (calls >= max_calls):
        return _fallback_story(block)

    # 3) Build prompt & call LLM
    height = block.get("height")
    era = block.get("era")
    pool = block.get("pool")
    time_utc = block.get("time")
    h_val = block.get("entropy_h")
    k_val = block.get("complexity_k")
    channels = ", ".join(block.get("channels", [])) or "—"
    tags = ", ".join(block.get("curator_tags", [])) or "—"
    finance = _finance_line(block)

    prompt = f"""You are a Bitcoin macro analyst for the ChainWalk Desk. Write ONE decisive desk-grade insight paragraph (3–5 sentences) diagnosing what this block reveals about Bitcoin's enemies, incentives, and future.

Block facts:
- Height: {height}
- Era: {era}
- Time (UTC): {time_utc}
- Pool: {pool}
- Entropy H: {h_val} · Complexity K: {k_val}
- Finance: {finance}
- Channels: {channels}
- Curator tags: {tags}

Rules:
- No speculation, no commands, no lists.
- Diagnose: This block means X. This miner wants Y. This tension pushes risk to Z.
- Eliminate: “Typical throughput block”, “Nothing unusually extreme…”, neutral/factual tone.
- Confident, decisive desk analyst voice.
"""

    try:
        text = generate_text(prompt, max_tokens=260)
        headline = "Desk analyst insight"
        payload = {"headline": headline, "text": text.strip()}
    except Exception as e:
        payload = {
            "headline": "Docent unavailable",
            "text": f"(docent error: {e})",
        }

    # bump call counter
    setattr(describe_block, "_calls", calls + 1)  # type: ignore[arg-type]

    # 4) persist
    try:
        _write_cached(key, payload)
    except Exception:
        pass

    return payload


def build_story(block: Dict[str, Any], use_llm: bool = True, **kwargs) -> str:
    """
    Backwards-compatible wrapper used by mirror_builder.

    - If use_llm is False, we skip any new LLM calls and rely on cache
      or fallback summary.
    - If use_llm is True, we still respect config.json/env call limits.
    """
    if not use_llm:
        # temporarily pretend docent is disabled so describe_block
        # goes straight to fallback or cache
        cfg = get_config()
        original = cfg.get("docent_enabled", True)
        cfg["docent_enabled"] = False
        try:
            res = describe_block(block)
        finally:
            cfg["docent_enabled"] = original
    else:
        res = describe_block(block)

    # mirror_builder expects plain text today; we put headline on first line
    headline = res.get("headline", "AI docent note")
    text = res.get("text", "")
    return f"{headline}\n\n{text}"
