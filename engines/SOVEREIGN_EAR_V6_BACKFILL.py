from __future__ import annotations

"""
SOVEREIGN_EAR_V6_BACKFILL

Prune-aware historical "museum" builder for SovereignSignals V6.

- Uses ONLY your own Bitcoin Core node over JSON-RPC via LocalRPCProvider.
- No third-party explorers.
- Fills / extends block_catalog.jsonl for all blocks that are
  (a) still available on disk (respecting pruneheight) and
  (b) safely below the live engine's rolling window.

Safe to run repeatedly: it tracks progress in backfill_state.json.
"""

import sys
import json
import time
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sovereign_core.providers import LocalRPCProvider, RPC_URL  # type: ignore
from sovereign_core.detectors import detect_signals  # type: ignore
from sovereign_core.catalog import update_block_catalog  # type: ignore

try:
    # Only used here to read blockchaininfo / pruneheight.
    from bitcoinrpc.authproxy import AuthServiceProxy  # type: ignore
except Exception:  # pragma: no cover
    AuthServiceProxy = None  # type: ignore


def load_config(root: Path) -> Dict[str, Any]:
    cfg_path = root / "config.json"
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def load_backfill_state(root: Path) -> Dict[str, Any]:
    state_path = root / "backfill_state.json"
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_backfill_state(root: Path, state: Dict[str, Any]) -> None:
    state_path = root / "backfill_state.json"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_blockchain_info() -> Dict[str, Any]:
    """
    Lightweight helper to query getblockchaininfo from the same RPC URL
    that LocalRPCProvider uses. If RPC is unavailable, we raise a clear error.
    """
    if AuthServiceProxy is None:
        raise RuntimeError("bitcoinrpc.authproxy.AuthServiceProxy not available")

    rpc = AuthServiceProxy(RPC_URL)  # type: ignore
    return rpc.getblockchaininfo()


def main() -> None:
    project_root = ROOT
    cfg = load_config(project_root)

    # Config knobs (with conservative defaults)
    cfg_backfill_start = int(cfg.get("backfill_start_height", 1))
    backfill_chunk_size = int(cfg.get("backfill_chunk_size", 500))
    backfill_sleep_seconds = int(cfg.get("backfill_sleep_seconds", 5))
    window_size = int(cfg.get("window_size", 500))
    catalog_path = project_root / cfg.get("block_catalog_path", "block_catalog.jsonl")

    provider = LocalRPCProvider()

    # --- Introspect node state ------------------------------------------------
    info = get_blockchain_info()
    tip_height = int(info.get("blocks", 0))
    pruned = bool(info.get("pruned", False))
    pruneheight = int(info.get("pruneheight", 0)) if pruned else 1

    # Live engine scans the *last* `window_size` blocks continuously.
    live_window_start = max(1, tip_height - window_size + 1)
    max_backfill_height = max(1, live_window_start - 1)

    # Effective backfill start cannot be below pruneheight on a pruned node.
    effective_backfill_start = max(
        cfg_backfill_start,
        pruneheight if pruned else cfg_backfill_start,
    )

    state = load_backfill_state(project_root)
    last_processed = int(
        state.get("last_processed_height", effective_backfill_start - 1)
    )

    print("SOVEREIGN_EAR_V6_BACKFILL (local node, prune-aware)")
    print(f"   Node tip height         : {tip_height:,}")
    print(f"   Window size (live)      : {window_size}")
    print(f"   Live window start       : {live_window_start:,}")
    print(f"   Node pruned?            : {pruned}")
    if pruned:
        print(f"   Node pruneheight        : {pruneheight:,}")
    else:
        print("   Node pruneheight        : (not pruned)")
    print(f"   Config backfill_start   : {cfg_backfill_start:,}")
    print(f"   Effective backfill_start: {effective_backfill_start:,}")
    print(f"   Backfill target (max)   : {max_backfill_height:,}")
    print(f"   Last processed height   : {last_processed:,}")
    print(f"   Catalog path            : {catalog_path}")
    print(f"   Chunk size              : {backfill_chunk_size}")
    print(f"   Sleep between chunks    : {backfill_sleep_seconds}s")
    print()

    if effective_backfill_start > max_backfill_height:
        print("   Nothing to backfill: effective_backfill_start is above live window region.")
        print("   You can safely stop this script; the museum is up to date for the available chain.")
        return

    while True:
        if last_processed >= max_backfill_height:
            print("   Backfill complete — no more historical blocks below live region.")
            break

        # Next chunk boundaries, clamped to [effective_backfill_start, max_backfill_height]
        chunk_start = max(effective_backfill_start, last_processed + 1)
        chunk_end = min(chunk_start + backfill_chunk_size - 1, max_backfill_height)

        if chunk_start > chunk_end:
            print("   Backfill complete (chunk_start > chunk_end).")
            break

        print(f"   Processing chunk: {chunk_start:,} → {chunk_end:,}")

        try:
            blocks = list(provider.get_range(chunk_start, chunk_end))
        except Exception as e:
            print(f"   [error] provider failure in range {chunk_start}–{chunk_end}: {e}")
            print(f"   Sleeping {backfill_sleep_seconds} seconds and retrying...")
            time.sleep(backfill_sleep_seconds)
            continue

        if not blocks:
            print("   [warn] provider returned no blocks; skipping this chunk.")
            last_processed = chunk_end  # Mark as processed to move on
            state["last_processed_height"] = last_processed
            save_backfill_state(project_root, state)
            continue

        print(f"   Retrieved {len(blocks)} blocks; running detectors...")
        signals, _detector_state = detect_signals(blocks)

        polyphonic_count = sum(1 for s in signals if getattr(s, "polyphonic", False))
        print(
            f"   Signals in this chunk: {len(signals)} "
            f"(polyphonic: {polyphonic_count})"
        )

        # Append directly to the main catalog (museum)
        entries = [s.to_dict() for s in signals]
        if entries:
            update_block_catalog(catalog_path, entries)
            print(f"   Appended {len(entries)} records to catalog")

        last_processed = chunk_end
        state["last_processed_height"] = last_processed
        save_backfill_state(project_root, state)
        print(
            f"   Updated backfill_state.json (last_processed_height = "
            f"{last_processed:,})"
        )

        # Friendly pause to avoid hammering the node
        print(f"   Sleeping {backfill_sleep_seconds} seconds before next chunk...")
        time.sleep(backfill_sleep_seconds)
        print()

    print("SOVEREIGN_EAR_V6_BACKFILL complete.")


if __name__ == "__main__":
    main()
