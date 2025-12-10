from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional


SURGE_HARD = 0.15
SURGE_SOFT = 0.02
BLEED_SOFT = -0.02
BLEED_HARD = -0.15


@dataclass
class MempoolIntentState:
    date_utc: str
    mpi: Optional[float]
    state: str          # SURGING/ELEVATING/NEUTRAL/BLEEDING/PURGE/UNKNOWN
    line: str           # human string for posts
    confidence: float   # 0.0–1.0


def classify_mpi(mpi: Optional[float]) -> tuple[str, float]:
    """
    Classify MPI into a coarse bucket and assign a naive confidence.
    """
    if mpi is None:
        return "UNKNOWN", 0.0

    if mpi >= SURGE_HARD:
        return "SURGING", 0.9
    if mpi >= SURGE_SOFT:
        return "ELEVATING", 0.7
    if mpi <= BLEED_HARD:
        return "PURGE", 0.9
    if mpi <= BLEED_SOFT:
        return "BLEEDING", 0.7
    return "NEUTRAL", 0.6


def build_mpi_line(state: str) -> str:
    """
    Map state → human-readable line in ChainWalk tone (Option B, toned down).
    """
    if state == "SURGING":
        return "Mempool intent is surging — demand is lining up before the chain commits."
    if state == "ELEVATING":
        return "Mempool intent is rising — demand is entering before commitment."
    if state == "BLEEDING":
        return "Mempool intent is bleeding — desire is leaving the queue before it can settle to chain."
    if state == "PURGE":
        return "Mempool is purging — the queue is clearing faster than it can refill."
    if state == "NEUTRAL":
        return "Mempool intent is balanced — no clear pressure bias in the queue."
    return "Mempool intent unavailable — chain permission cannot be inferred today."


def compute_mempool_intent(
    *,
    date_utc: str,
    tx_count_now: Optional[int],
    tx_count_then: Optional[int],
) -> MempoolIntentState:
    """
    Pure builder: no IO, no logging, no side effects.
    """

    mpi: Optional[float] = None
    if (
        tx_count_now is not None
        and tx_count_then is not None
        and tx_count_then > 0
    ):
        mpi = (tx_count_now - tx_count_then) / float(tx_count_then)

    state, confidence = classify_mpi(mpi)
    line = build_mpi_line(state)

    return MempoolIntentState(
        date_utc=date_utc,
        mpi=mpi,
        state=state,
        line=line,
        confidence=confidence,
    )


def mempool_intent_to_json(intent: MempoolIntentState) -> Dict[str, Any]:
    return asdict(intent)