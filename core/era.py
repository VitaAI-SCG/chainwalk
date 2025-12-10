from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class EraInfo:
    slug: str        # "post_etf"
    label: str       # "Post-ETF"
    min_height: int  # inclusive
    max_height: int  # inclusive

# Updated boundaries per DEVREPORT.md
ETF_TIMESTAMP = 1727740800  # Oct 1, 2024
ERA_BANDS = [
    EraInfo("satoshi",       "Satoshi",        0,        199999),
    EraInfo("early_gpu",     "Early GPU",      200000,  349999),
    EraInfo("asic_wars",     "ASIC Wars",      350000,  549999),
    EraInfo("segwit",        "SegWit",         550000,  699999),
    EraInfo("institutional", "Institutional",  700000,  1000000000),  # adjusted for ETF
    EraInfo("post_etf",      "Post-ETF",       700000,  1000000000),  # special case
]

def get_era(height: Optional[int], timestamp: Optional[int] = None) -> str:
    if height is None:
        return "unknown"
    if height < 200000:
        return "satoshi"
    elif height < 350000:
        return "early_gpu"
    elif height < 550000:
        return "asic_wars"
    elif height < 700000:
        return "segwit"
    elif height >= 700000:
        if timestamp and timestamp >= ETF_TIMESTAMP:
            return "post_etf"
        else:
            return "institutional"
    return "unknown"

def label_for_slug(slug: str) -> str:
    for band in ERA_BANDS:
        if band.slug == slug:
            return band.label
    # fallback (should be rare)
    return "Unknown"

def infer_era(block: dict) -> tuple[str, str]:
    """
    Returns (slug, label) for a block, using:
    1) block['era_slug'] if present,
    2) mapped from block['era'] if that's a slug-ish string,
    3) height/timestamp-based otherwise.
    """
    # 1) direct slug field
    slug = (block.get("era_slug") or "").lower().strip()
    if slug:
        return slug, label_for_slug(slug)

    # 2) try "era" field as slug
    era_field = (block.get("era") or "").lower().strip()
    if era_field.startswith("era:"):
        era_field = era_field.split(":", 1)[1]
    if era_field in {e.slug for e in ERA_BANDS}:
        return era_field, label_for_slug(era_field)

    # 3) height/timestamp-based
    height = block.get("height")
    timestamp = block.get("timestamp")
    slug = get_era(height, timestamp)
    return slug, label_for_slug(slug)