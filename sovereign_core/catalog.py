from __future__ import annotations
import json, hashlib
from pathlib import Path
from typing import Any, Dict, List
from core.era import get_era

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "block_catalog.jsonl"

def _entry_key(sig: Dict[str, Any]) -> str:
    sample = (sig.get("sample_hex") or "")[:32]
    key = f'{sig["height"]}:{sample}'
    return hashlib.sha256(key.encode()).hexdigest()[:12]

def update_block_catalog(catalog_path: Path, signals: List[Dict[str, Any]]) -> int:
    if not signals: return 0
    catalog_path = catalog_path.expanduser().resolve()
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if catalog_path.exists():
        with catalog_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        obj = json.loads(line)
                        existing.add(_entry_key(obj))
                    except: pass
    new_sigs = [s for s in signals if _entry_key(s) not in existing]
    if new_sigs:
        for s in new_sigs:
            if "era_slug" not in s:
                s["era_slug"] = get_era(s.get("height"), s.get("timestamp"))
        with catalog_path.open("a", encoding="utf-8") as f:
            for s in new_sigs:
                f.write(json.dumps(s, sort_keys=False) + "\n")
        print(f"[Catalog] +{len(new_sigs)} new blocks → ~{len(existing)+len(new_sigs):,} total")
    return len(new_sigs)
