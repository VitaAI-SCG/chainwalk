import math
import zlib
from typing import Iterable


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    length = len(data)
    counts = {}
    for b in data:
        counts[b] = counts.get(b, 0) + 1
    ent = 0.0
    for c in counts.values():
        p = c / length
        ent -= p * math.log2(p)
    return ent


def compression_ratio(data: bytes, level: int = 6) -> float:
    if not data:
        return 1.0
    try:
        comp = zlib.compress(data, level)
        return round(len(comp) / len(data), 3)
    except Exception:
        return 1.0


def mean(values: Iterable[float]) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def stddev(values: Iterable[float]) -> float:
    vals = list(values)
    n = len(vals)
    if n < 2:
        return 0.0
    m = mean(vals)
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    return math.sqrt(var)
