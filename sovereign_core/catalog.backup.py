from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

try:
    # Docent / narrative helpers we already wired for the block plaques.
    from sovereign_core.narrative import make_block_story, make_curator_tags
except Exception:  # pragma: no cover
    # Fallback so tools can still import this module in isolation.
    def make_block_story(sig: Dict[str, Any]) -> str:
        return "Block story not available (narrative module missing)."

    def make_curator_tags(sig: Dict[str, Any]) -> List[str]:
        return []


@dataclass
class CatalogEntry:
    height: int
    time: Optional[str]
    pool: str
    era: str
    channels: List[str]
    curator_tags: List[str]
    story: str
    financial_hook: Optional[str]
    history_hook: Optional[str]
    nerd_hook: Optional[str]
    score: float
    polyphonic: bool
    entropy: Optional[float]
    complexity: Optional[float]
    total_btc: Optional[float]
    largest_tx_btc: Optional[float]
    fees_btc: Optional[float]
    coinbase_text: Optional[str]
    sample_hex: Optional[str]


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_polyphonic(sig: Dict[str, Any]) -> bool:
    # Prefer explicit flag if present, fall back to channel count.
    if "polyphonic" in sig:
        return bool(sig.get("polyphonic"))
    if "poly" in sig:
        return bool(sig.get("poly"))
    ch = sig.get("ch") or sig.get("channels_count")
    try:
        return int(ch) > 1
    except (TypeError, ValueError):
        return False


def _extract_finance_fields(
    sig: Dict[str, Any],
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Try multiple shapes so upstream field names can evolve without
    breaking the catalog.
    """
    total = sig.get("total_btc") or sig.get("volume_btc") or sig.get("total_btc_volume")
    largest = sig.get("largest_tx_btc") or sig.get("largest_btc") or sig.get("largest_tx")
    fees = sig.get("fees_btc") or sig.get("fee_btc") or sig.get("fees")
    return _float_or_none(total), _float_or_none(largest), _float_or_none(fees)


def _build_hooks(sig: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Build the three short 'exhibit labels' for each block:

        financial_hook
        history_hook
        nerd_hook
    """
    total_btc, largest_btc, fees_btc = _extract_finance_fields(sig)
    channels: List[str] = list(sig.get("channels") or [])
    era = str(sig.get("era") or sig.get("regime") or "unknown")
    pool = str(sig.get("pool") or "unknown")
    time_str = str(sig.get("time") or "")

    # 1) Financial hook
    financial: Optional[str] = None
    if total_btc is not None and largest_btc is not None:
        whale_ratio = largest_btc / total_btc if total_btc > 0 else 0.0
        if whale_ratio >= 0.3:
            # Strong single-actor footprint.
            cb = (sig.get("coinbase_text") or sig.get("message") or "").lower()
            if "f2pool" in cb:
                financial = (
                    f"This block looks like a heavy F2Pool-style payout sweep: "
                    f"~{total_btc:,.1f} BTC moved on-chain with a whale transfer near "
                    f"{largest_btc:,.1f} BTC dominating the flow."
                )
            else:
                financial = (
                    f"On-chain flow is dominated by a single whale-scale movement: "
                    f"{largest_btc:,.1f} BTC out of ~{total_btc:,.1f} BTC total volume."
                )
        else:
            financial = (
                f"Flow is more distributed here: ~{total_btc:,.1f} BTC over many smaller "
                f"transfers; the largest single move clocks in near {largest_btc:,.1f} BTC."
            )
    elif total_btc is not None:
        financial = f"Roughly ~{total_btc:,.1f} BTC of value changed hands in this block."
    else:
        financial = None

    # 2) History hook — consciously cycle/era oriented; we don't guess exact price.
    history: Optional[str] = None
    if time_str:
        history = (
            f"Mined in the {era} era, this block sits in the late-{time_str[:4]} portion "
            f"of the cycle—one tile in the wider market-regime mosaic."
        )
    else:
        history = f"Part of the {era} era; another datapoint in the post-halving regime map."

    # 3) Nerd / anomaly hook
    nerd: Optional[str] = None
    lowered_channels = ",".join(channels).lower()
    coinbase_text = str(sig.get("coinbase_text") or sig.get("message") or "")
    if "header tail anomaly" in lowered_channels:
        nerd = (
            "Header tail anomaly plus low-entropy text hints at a custom payout template or "
            "bespoke pool script rather than a stock mining stack."
        )
    elif "time delta weird" in lowered_channels:
        nerd = (
            "Non-standard inter-block timing flags this as an out-of-rhythm arrival in the chain—"
            "exactly the sort of cadence break hidden-structure hunters watch for."
        )
    elif "coinbase low entropy" in lowered_channels:
        nerd = (
            "Coinbase entropy sits unusually low here, suggesting a tightly scripted or templated "
            "operator message rather than organic variation."
        )
    elif coinbase_text:
        nerd = (
            "Coinbase message carries the operator's fingerprint; tiny stylistic quirks here become "
            "breadcrumbs once you scan thousands of neighbouring blocks."
        )
    else:
        nerd = None

    return financial, history, nerd


def build_catalog_entry(sig: Dict[str, Any]) -> CatalogEntry:
    """
    Turn one Sovereign Signals block dict into a persistent catalog entry.
    """
    height = int(sig.get("height"))
    time_str = sig.get("time")
    pool = str(sig.get("pool") or "unknown")
    era = str(sig.get("era") or sig.get("regime") or "unknown")
    channels = list(sig.get("channels") or [])

    # Curator tags + base story from the docent engine.
    curator_tags: List[str] = []
    try:
        curator_tags = list(make_curator_tags(sig))
    except Exception:
        curator_tags = []

    try:
        story = make_block_story(sig)
    except Exception:
        story = "Narrative unavailable; curator engine offline."

    financial_hook, history_hook, nerd_hook = _build_hooks(sig)

    score = _float_or_none(sig.get("score")) or 0.0
    polyphonic = _bool_polyphonic(sig)

    entropy = _float_or_none(sig.get("entropy") or sig.get("H") or sig.get("h"))
    complexity = _float_or_none(sig.get("complexity") or sig.get("K") or sig.get("k"))

    total_btc, largest_btc, fees_btc = _extract_finance_fields(sig)

    coinbase_text = sig.get("coinbase_text") or sig.get("message") or None
    sample_hex = sig.get("sample_hex") or sig.get("sample") or None

    return CatalogEntry(
        height=height,
        time=time_str,
        pool=pool,
        era=era,
        channels=channels,
        curator_tags=curator_tags,
        story=story,
        financial_hook=financial_hook,
        history_hook=history_hook,
        nerd_hook=nerd_hook,
        score=score,
        polyphonic=polyphonic,
        entropy=entropy,
        complexity=complexity,
        total_btc=total_btc,
        largest_tx_btc=largest_btc,
        fees_btc=fees_btc,
        coinbase_text=coinbase_text,
        sample_hex=sample_hex,
    )


def _load_existing_heights(catalog_path: Path) -> Set[int]:
    heights: Set[int] = set()
    if not catalog_path.exists():
        return heights
    try:
        with catalog_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                h = obj.get("height")
                try:
                    if h is not None:
                        heights.add(int(h))
                except (TypeError, ValueError):
                    continue
    except OSError:
        # If anything goes wrong, we just start fresh; the on-disk file is a cache.
        return set()
    return heights


def append_block_catalog_entries(
    signals: Iterable[Dict[str, Any]],
    catalog_path: Path,
    source: str = "sovereign_ear_v6",
) -> int:
    """
    Append new catalog entries for any blocks we haven't seen before.

    Returns the number of *new* entries appended.
    """
    catalog_path = catalog_path.expanduser().resolve()
    catalog_path.parent.mkdir(parents=True, exist_ok=True)

    existing_heights = _load_existing_heights(catalog_path)

    new_entries: List[CatalogEntry] = []
    for sig in signals:
        try:
            height = int(sig.get("height"))
        except Exception:
            continue
        if height in existing_heights:
            continue
        entry = build_catalog_entry(sig)
        new_entries.append(entry)
        existing_heights.add(height)

    if not new_entries:
        return 0

    with catalog_path.open("a", encoding="utf-8") as fh:
        for entry in new_entries:
            obj = asdict(entry)
            # Tiny bit of provenance never hurts.
            obj["_source"] = source
            fh.write(json.dumps(obj, sort_keys=True) + "\n")

    return len(new_entries)
