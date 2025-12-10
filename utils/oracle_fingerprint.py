from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
import hashlib
import json

MEASUREMENT_FIELDS = [
    "date_utc",
    "regime",
    "regime_phase",           # e.g. MID, LATE
    "cti",                    # Chain Tension Index
    "custody_streak",
    "custody_direction",      # marketward / sideline / neutral
    "entropy_band",           # flat / fractured / shocked
    "price_corridor",         # permitted / constrained / forbidden
    "mempool_intent_band",    # bleeding / neutral / surging
    "mempool_intent_score",   # 0–1
    "hashrate_band",          # rising / falling / calm
    "hashrate_stress",        # 0–1
    "mti_index",
    "mti_band",
    "eti_index",
    "eti_band",
    "irq_index",
    "irq_band",
    "rei_index",
    "rei_band",
    "regime_integrity",       # e.g. COILED / FRACTURING / BROKEN
]

def build_measurement_vector(daily_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts the measurement-only vector used to construct the oracle fingerprint.
    IMPORTANT: This MUST NOT include price, realized vol, or any market-derived variable.
    """
    v: Dict[str, Any] = {}
    for key in MEASUREMENT_FIELDS:
        if key in daily_state:
            v[key] = daily_state[key]
    return v

def compute_oracle_input_hash(daily_state: Dict[str, Any]) -> str:
    """
    Deterministic hash over the measurement vector.
    - Canonical JSON serialization (sorted keys, no whitespace)
    - SHA-256 hex digest
    """
    vec = build_measurement_vector(daily_state)
    payload = json.dumps(vec, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return h