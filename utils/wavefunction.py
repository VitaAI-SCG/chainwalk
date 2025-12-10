import math
from typing import Dict, Tuple

BASIS_ORDER = ["S", "C", "D", "A"]

def softmax(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    max_s = max(scores.values())
    exps = {k: math.exp(v - max_s) for k, v in scores.items()}
    Z = sum(exps.values())
    return {k: exps[k] / Z for k in scores}

def scores_to_wavefunction(scores: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
    # Add epsilon if all scores are zero
    if all(v == 0.0 for v in scores.values()):
        scores = {k: 1e-6 for k in scores}

    probs = softmax(scores)
    amps = {k: math.sqrt(p) for k, p in probs.items()}

    # Sanity check
    prob_sum = sum(probs.values())
    amp_norm_sq = sum(a * a for a in amps.values())
    assert abs(prob_sum - 1.0) < 1e-6, f"Probabilities do not sum to 1: {prob_sum}"
    assert abs(amp_norm_sq - 1.0) < 1e-6, f"Amplitudes do not normalize: {amp_norm_sq}"

    return probs, amps