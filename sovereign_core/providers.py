from __future__ import annotations

"""
sovereign_core.providers

Local Bitcoin Core-backed block provider for SovereignSignals V6.

- Uses ONLY your own Bitcoin Core node over JSON-RPC.
- No third-party explorers.
- Decimal-safe math for BTC amounts (no float + Decimal mixing).
"""

import os
from dataclasses import dataclass
from typing import Iterable
from decimal import Decimal
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException  # type: ignore

# --- RPC configuration -------------------------------------------------------

RPC_USER = os.getenv("SOVEREIGN_RPC_USER", "sovereign")
RPC_PASSWORD = os.getenv("SOVEREIGN_RPC_PASSWORD", "bitcoin")
RPC_HOST = os.getenv("SOVEREIGN_RPC_HOST", "127.0.0.1")
RPC_PORT = int(os.getenv("SOVEREIGN_RPC_PORT", "8332"))

RPC_URL = f"http://{RPC_USER}:{RPC_PASSWORD}@{RPC_HOST}:{RPC_PORT}"


@dataclass
class SimpleBlock:
    height: int
    timestamp: int
    block_hash: str
    coinbase_script: bytes
    pool_hint: str
    tx_count: int
    total_output_btc: float
    largest_tx_btc: float
    total_fee_btc: float


class BlockProviderError(Exception):
    """Raised when RPC is unavailable or all attempts fail."""
    pass


class BlockProvider:
    """Abstract provider interface."""

    def get_tip_height(self) -> int:
        raise NotImplementedError

    def get_range(self, start_height: int, end_height: int) -> Iterable[SimpleBlock]:
        raise NotImplementedError


class LocalRPCProvider(BlockProvider):
    """
    Thin wrapper over Bitcoin Core JSON-RPC.

    bitcoin.conf should contain something like:

        server=1
        txindex=0            # ok for our current use
        rpcuser=sovereign
        rpcpassword=bitcoin
        rpcallowip=127.0.0.1
        rpcbind=127.0.0.1
        rpcport=8332

    If you use different credentials, either:

        - change RPC_USER / RPC_PASSWORD above, or
        - set SOVEREIGN_RPC_USER / SOVEREIGN_RPC_PASSWORD env vars.
    """

    def __init__(self) -> None:
        self._rpc = AuthServiceProxy(RPC_URL)

    # --- Core RPC helpers ----------------------------------------------------

    def get_tip_height(self) -> int:
        try:
            return int(self._rpc.getblockcount())
        except Exception as e:  # JSONRPCException or connection error
            raise BlockProviderError(f"RPC getblockcount failed: {e}") from e

    def _decode_pool_hint(self, coinbase_script: bytes) -> str:
        text = coinbase_script.decode("utf-8", "ignore").lower()
        if "foundry" in text:
            return "Foundry USA"
        if "viabtc" in text:
            return "ViaBTC"
        if "antpool" in text:
            return "AntPool"
        if "f2pool" in text:
            return "F2Pool"
        if "binance" in text:
            return "Binance Pool"
        return "unknown"

    def get_range(self, start_height: int, end_height: int):
        """
        Yield SimpleBlock objects for the inclusive height range.

        Uses Decimal internally for all BTC math and converts to float only
        when populating SimpleBlock.
        """
        start = max(1, int(start_height))
        end = int(end_height)
        if end < start:
            return []

        for h in range(start, end + 1):
            try:
                hsh = self._rpc.getblockhash(h)
                blk = self._rpc.getblock(hsh, 2)  # verbosity=2 => decoded txs

                cb_hex = blk["tx"][0]["vin"][0].get("coinbase", "") or ""
                coinbase_bytes = bytes.fromhex(cb_hex) if cb_hex else b""

                pool_hint = self._decode_pool_hint(coinbase_bytes)

                txs = blk["tx"]
                tx_count = len(txs)

                total_out_dec: Decimal = Decimal("0")
                largest_dec: Decimal = Decimal("0")

                # Sum vout values as Decimal
                for i, tx in enumerate(txs):
                    vout_sum_dec = sum(
                        Decimal(str(v["value"]))
                        for v in tx.get("vout", [])
                    )
                    total_out_dec += vout_sum_dec
                    if i > 0 and vout_sum_dec > largest_dec:
                        largest_dec = vout_sum_dec

                # Very rough fee estimate (all Decimal)
                try:
                    cb_out_dec = sum(
                        Decimal(str(v["value"]))
                        for v in txs[0].get("vout", [])
                    )
                    total_non_cb_dec = total_out_dec - cb_out_dec
                    fee_est_dec = cb_out_dec - total_non_cb_dec
                    if fee_est_dec < Decimal("0"):
                        fee_est_dec = Decimal("0")
                except Exception:
                    fee_est_dec = Decimal("0")

                # Convert to float for the dataclass
                total_out = float(total_out_dec)
                largest = float(largest_dec)
                fee_est = float(fee_est_dec)

                yield SimpleBlock(
                    height=h,
                    timestamp=int(blk["time"]),
                    block_hash=str(hsh),
                    coinbase_script=coinbase_bytes,
                    pool_hint=pool_hint,
                    tx_count=tx_count,
                    total_output_btc=total_out,
                    largest_tx_btc=largest,
                    total_fee_btc=fee_est,
                )
            except JSONRPCException as e:
                print(f"[LocalRPC] RPC error at height {h}: {e}")
                continue
            except Exception as e:
                print(f"[LocalRPC] Unexpected error at height {h}: {e}")
                continue
