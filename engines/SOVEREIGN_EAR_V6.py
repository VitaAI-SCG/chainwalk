from __future__ import annotations

import math
import requests  # for BTC/USD + hashrate snapshot
"""
SOVEREIGN_EAR_V6
----------------
Live Bitcoin block listener for Sovereign Signals V6, backed ONLY by your
local Bitcoin Core node.

Responsibilities
* Ask the local node for the current tip height.
* Pull a rolling window of recent blocks via LocalRPCProvider.
* Run the detector pipeline to produce per-block "signals".
* Emit a live JSON feed (sovereign_signals_latest.json) for the UI.
* Append block snapshots into block_catalog.jsonl for the long-horizon museum.
* Regenerate MESSAGE_MIRROR.html via readers/mirror_builder.py.
"""

import sys
import json
from pathlib import Path
from typing import Optional, Any, Dict

# ---------------------------------------------------------------------------
# Make sure project root and readers/ are on sys.path
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent  # project root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

READERS_DIR = ROOT / "readers"
if READERS_DIR.is_dir() and str(READERS_DIR) not in sys.path:
    sys.path.insert(0, str(READERS_DIR))

# Core pipeline pieces (these live under sovereign_core on disk)
from sovereign_core.providers import LocalRPCProvider  # type: ignore
from sovereign_core.detectors import detect_signals  # type: ignore
from sovereign_core.schema import build_payload  # type: ignore
from sovereign_core.catalog import update_block_catalog  # type: ignore

# MESSAGE_MIRROR builder (readers/mirror_builder.py)
import mirror_builder  # type: ignore

from core.config import get_config

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Main live engine
# ---------------------------------------------------------------------------


def build_network_snapshot(provider) -> dict:
    """Best-effort snapshot of network state for the live window.

    - Tries local node RPC first (difficulty, blocks, chain).
    - Then tries a public API for BTC/USD and hash rate.
    - Never raises; on failure returns {}.
    """
    snap: dict = {}

    # 1) Try local node for difficulty / chain info
    try:
        info = provider.call("getblockchaininfo", []) if hasattr(provider, "call") else provider.rpc_call("getblockchaininfo")  # type: ignore[attr-defined]
        if isinstance(info, dict):
            snap["difficulty"] = info.get("difficulty")
            snap["blocks"] = info.get("blocks")
            snap["chain"] = info.get("chain")
    except Exception as e:
        print(f"[warn] getblockchaininfo failed for network snapshot: {e}")

    # 2) Try local node for network hash rate (if supported)
    try:
        hps = provider.call("getnetworkhashps", []) if hasattr(provider, "call") else provider.rpc_call("getnetworkhashps")  # type: ignore[attr-defined]
        if isinstance(hps, (int, float)):
            snap["network_hashps"] = hps
    except Exception as e:
        print(f"[warn] getnetworkhashps failed for network snapshot: {e}")

    # 3) Public API for BTC/USD & hash rate (blockchain.info)
    try:
        resp = requests.get("https://api.blockchain.info/stats?cors=true", timeout=5)
        if resp.ok:
            data = resp.json()
            # API gives hash_rate in GH/s; convert to H/s if we want
            if "hash_rate" in data and "network_hashps" not in snap:
                try:
                    ghps = float(data["hash_rate"])
                    snap["network_hashps"] = ghps * 1e9
                except Exception:
                    pass
            if "difficulty" in data and "difficulty" not in snap:
                snap["difficulty"] = data["difficulty"]
            if "market_price_usd" in data:
                snap["btc_usd"] = data["market_price_usd"]
    except Exception as e:
        print(f"[warn] public network stats fetch failed: {e}")

    return snap


def main() -> None:
    project_root = ROOT
    cfg = get_config()

    # How many blocks to scan each live cycle
    window_size = int(cfg.get("window_size", 500))
    min_height = int(cfg.get("min_height", 1))

    # Paths for outputs
    output_json_path = project_root / cfg.get(
        "output_json", "sovereign_signals_latest.json"
    )
    mirror_html_path = project_root / cfg.get(
        "message_mirror_html", "MESSAGE_MIRROR.html"
    )
    catalog_path = project_root / cfg.get(
        "block_catalog_path", "block_catalog.jsonl"
    )

    provider = LocalRPCProvider()

    # Ask local node for current tip
    try:
        tip_height = int(provider.get_tip_height())
    except Exception as e:
        print(f"[fatal] get_tip_height failed: {e}")
        sys.exit(1)

    start_height = max(min_height, tip_height - window_size + 1)
    end_height = tip_height

    print("SOVEREIGN_EAR_V6 (local node) - Initializing Bitcoin signal observatory...")
    print("   Using local Bitcoin Core via JSON-RPC.")
    print(f"   Tip height (local node): {tip_height:,}")
    print(
        f"   Scanning window: {start_height:,} to {end_height:,} "
        f"({end_height - start_height + 1} blocks)"
    )

    # Fetch blocks
    try:
        blocks = list(provider.get_range(start_height, end_height))
    except Exception as e:
        print(f"[fatal] provider.get_range({start_height}, {end_height}) failed: {e}")
        sys.exit(1)

    if not blocks:
        print("[warn] No blocks returned in live window; aborting this cycle.")
        return

    print(f"[info] Retrieved {len(blocks)} blocks; running detectors...")

    # Run detectors -> signals (each Signal already contains the block stats you care about)
    signals, detector_state = detect_signals(blocks)

    polyphonic_count = sum(1 for s in signals if getattr(s, "polyphonic", False))
    print(
        f"[info] Detected {len(signals)} signals "
        f"(polyphonic: {polyphonic_count}) in live window."
    )

    # IMPORTANT: call build_payload with the correct signature:
    #   build_payload(signals, tip_height, window_size)
    payload = build_payload(signals, tip_height, window_size)

    # Persist live JSON feed
    try:
        output_json_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        print(f"[ok] Wrote latest signals to {output_json_path}")
    except Exception as e:
        print(f"[error] Failed to write {output_json_path}: {e}")

    # Append signals to the long-horizon catalog
    entries = payload.get("signals", [])
    if entries:
        try:
            update_block_catalog(catalog_path, entries)
            print(
                f"[ok] Updated block catalog at {catalog_path} "
                f"with {len(entries)} entries"
            )
        except Exception as e:
            print(f"[error] Failed to update block catalog: {e}")
    else:
        print("[info] No signals in this window; catalog not updated.")

    # Rebuild MESSAGE_MIRROR.html via readers/mirror_builder.py
    try:
        mirror_builder.build_mirror(output_json_path, mirror_html_path)
        print(f"[ok] Rebuilt MESSAGE_MIRROR at {mirror_html_path}")
    except Exception as e:
        print(f"[warn] Could not rebuild MESSAGE_MIRROR.html: {e}")

    print("SOVEREIGN_EAR_V6 cycle complete.")





def _maybe_run_message_mirror() -> None:
    """
    Refresh MESSAGE_MIRROR.html after each SOVEREIGN_EAR_V6 cycle.
    Best-effort only; will never raise if mirror builder is missing.
    """
    try:
        import subprocess
        import sys as _sys
        from pathlib import Path as _Path

        project_root = _Path(__file__).resolve().parent.parent
        candidates = [
            project_root / "readers" / "mirror_builder.py",
            project_root / "mirror_builder.py",
            project_root / "tools" / "mirror_builder.py",
            project_root / "museum" / "mirror_builder.py",
        ]
        target = None
        for c in candidates:
            if c.exists():
                target = c
                break

        if target is None:
            print("[ear] MESSAGE_MIRROR builder not found; skipping.")
            return

        print(f"[ear] Refreshing MESSAGE_MIRROR via {target} ...")
        subprocess.run([_sys.executable, str(target)], check=False)
    except Exception as e:
        print(f"[ear] MESSAGE_MIRROR refresh failed: {e}")


if __name__ == "__main__":
    main()
