from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from bitcoinrpc.authproxy import AuthServiceProxy  # type: ignore

from sovereign_core.detectors import detect_signals
from sovereign_core.narrative import make_block_story, classify_tags
from sovereign_core.catalog import update_block_catalog
from sovereign_core.providers import SimpleBlock, RPC_URL

CATALOG = ROOT.parent / "block_catalog.jsonl"


def main(block_hash: str) -> None:
    log_path = ROOT.parent / "extract_log.txt"
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"Starting extraction for {block_hash}\n")
        try:
            rpc = AuthServiceProxy(RPC_URL)
            blk = rpc.getblock(block_hash, 2)
            h = blk["height"]
            log.write(f"Fetched block {h}\n")

            cb_hex = blk["tx"][0]["vin"][0].get("coinbase", "") or ""
            cb = bytes.fromhex(cb_hex) if cb_hex else b""

            total_out = 0.0
            largest = 0.0
            for i, tx in enumerate(blk["tx"]):
                vout_sum = sum(v["value"] for v in tx.get("vout", []))
                total_out += vout_sum
                if i > 0 and vout_sum > largest:
                    largest = vout_sum

            try:
                cb_out = sum(v["value"] for v in blk["tx"][0].get("vout", []))
                total_non_cb = total_out - cb_out
                fee_est = max(0.0, cb_out - total_non_cb)
            except Exception:
                fee_est = 0.0

            sblock = SimpleBlock(
                height=h,
                timestamp=blk["time"],
                block_hash=block_hash,
                coinbase_script=cb,
                pool_hint="unknown",
                tx_count=len(blk["tx"]),
                total_output_btc=total_out,
                largest_tx_btc=largest,
                total_fee_btc=fee_est,
            )

            signals, _ = detect_signals([sblock])
            if signals:
                sig = signals[0].to_dict()
                sig["story"] = make_block_story(sig)
                sig["tags"] = classify_tags(sig).as_list()
                update_block_catalog(CATALOG, [sig])
                log.write(f"[Extract] Block {h} → museum\n")
                print(f"[Extract] Block {h} → museum")
            else:
                log.write(f"No signals for block {h}\n")
                print(f"No signals for block {h}")
        except Exception as e:
            log.write(f"[Extract Error] {e}\n")
            print(f"[Extract Error] {e}")


if __name__ == "__main__" and len(sys.argv) > 1:
    main(sys.argv[1])
