from __future__ import annotations

"""
SovereignSignals V8 — Tour script builder

Takes a combined list of block "signal" dicts and emits a simple JSON
structure describing tour playlists. mirror_builder embeds this JSON
directly into MESSAGE_MIRROR.html for the JS tour runtime.

We keep this deliberately small:
- Latest high-score blocks
- Whale gallery
- Entropy extremes
"""

from typing import Any, Dict, List


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default


def _compute_score(sig: Dict[str, Any]) -> float:
    """
    Re-usable scoring function. A slightly spicy but bounded 0–10-ish
    score based on entropy, complexity, channels, polyphony & whales.
    """
    h = _safe_float(sig.get("entropy"))
    k = _safe_float(sig.get("complexity"))
    ch = sig.get("channels") or {}
    ch_active = sum(1 for v in ch.values() if v)
    poly = 1.0 if sig.get("polyphonic") else 0.0
    largest = _safe_float(sig.get("largest_tx_btc"))

    score = 0.0
    if h > 0:
        score += min(max(h - 3.5, 0.0), 3.0)  # up to ~3
    if k > 0:
        score += min(max(k - 0.9, 0.0) * 5.0, 3.0)  # richness
    score += min(ch_active, 5) * 0.5  # up to 2.5
    score += poly * 1.5
    score += min(largest / 2000.0, 2.0)  # big whales => + up to 2

    return round(score, 1)


def attach_score(sig: Dict[str, Any]) -> None:
    if "master_score" not in sig or not sig.get("master_score"):
        sig["master_score"] = _compute_score(sig)


def build_tours(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a small set of tour playlists from the combined signals list.
    """
    if not signals:
        return {"playlists": []}

    # Ensure each signal has a score
    for s in signals:
        attach_score(s)

    # Helpers
    def height(sig: Dict[str, Any]) -> int:
        return _safe_int(sig.get("height"))

    def largest(sig: Dict[str, Any]) -> float:
        return _safe_float(sig.get("largest_tx_btc"))

    def entropy(sig: Dict[str, Any]) -> float:
        return _safe_float(sig.get("entropy"))

    def playlist_from_candidates(name: str, title: str, candidates: List[Dict[str, Any]], limit: int = 64) -> Dict[str, Any]:
        stops = []
        for s in candidates[:limit]:
            stops.append(
                {
                    "height": height(s),
                    "score": _safe_float(s.get("master_score")),
                    "era": s.get("era_label") or "unknown",
                    "pool": s.get("pool") or "unknown",
                    "reason": s.get("tour_reason", []),
                }
            )
        return {"id": name, "title": title, "stops": stops}

    # 1) Latest high-score blocks (recent tip window)
    recent = sorted(signals, key=height, reverse=True)[:512]
    recent_sorted = sorted(
        recent, key=lambda s: (_safe_float(s.get("master_score")), height(s)), reverse=True
    )
    for s in recent_sorted:
        s.setdefault("tour_reason", []).append("high_score_recent")

    # 2) Whale gallery
    whales = [s for s in signals if largest(s) >= 1500.0]
    whales_sorted = sorted(whales, key=lambda s: largest(s), reverse=True)
    for s in whales_sorted:
        s.setdefault("tour_reason", []).append("whale_transfer")

    # 3) Entropy extremes
    mid_h = 4.5
    extremes = sorted(
        signals,
        key=lambda s: abs(entropy(s) - mid_h),
        reverse=True,
    )[:256]
    for s in extremes:
        s.setdefault("tour_reason", []).append("entropy_extreme")

    playlists = [
        playlist_from_candidates("latest_high_score", "Latest High-Score Blocks", recent_sorted),
        playlist_from_candidates("whale_gallery", "Whale Transfer Gallery", whales_sorted),
        playlist_from_candidates("entropy_extremes", "Entropy Extremes Walk", extremes),
    ]

    # Filter out empty playlists
    playlists = [p for p in playlists if p["stops"]]

    return {"playlists": playlists}
