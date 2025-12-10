from typing import Dict, Any

def build_spine_line(
    date_utc: str,
    regime_state: Dict[str, Any],
    regime_clock: Dict[str, Any],
    memory_state: Dict[str, Any],
    daily_state: Dict[str, Any],
    intent_clock: Dict[str, Any],
) -> str:
    regime_label = daily_state.get("regime_label", regime_state.get("dominant_vector", "UNKNOWN"))
    regime_phase = regime_clock.get("phase", "UNKNOWN")

    cti = float(daily_state.get("chain_tension_index", 0.0))
    cti_str = f"{cti:.1f}"

    custody_dir = memory_state.get("custody_direction", "neutral")
    custody_streak = int(memory_state.get("custody_streak", 0))

    entropy_trend = memory_state.get("entropy_trend_7d", "flat")
    price_corridor = daily_state.get("price_corridor", "UNKNOWN")

    incentive_delta = float(daily_state.get("incentive_delta", 0.0))
    id_str = f"{incentive_delta:.2f}"

    intent_days = intent_clock.get("max_days_remaining", None)
    if intent_days is not None:
        ic_str = f"{int(intent_days)}d"
    else:
        ic_str = "nd"  # no data

    window = regime_clock.get("window_days", {})
    rc_min = window.get("min_remaining", None)
    rc_max = window.get("max_remaining", None)
    if rc_min is not None and rc_max is not None:
        rc_str = f"{int(rc_min)}-{int(rc_max)}d"
    else:
        rc_str = "nd"

    hr_state = daily_state.get("hashrate", {})
    hr_trend = hr_state.get("trend", "nd")
    hr_band = hr_state.get("stress_band", "nd")
    hr_score = hr_state.get("stress_score", 0.0)

    miner_threshold = daily_state.get("miner_threshold", {})
    th_band = miner_threshold.get("band", "below")
    th_index = miner_threshold.get("index", 0.0)

    epoch = daily_state.get("difficulty_epoch", {})
    eti = float(epoch.get("tension_index", 0.0))
    eband = epoch.get("tension_band", "relaxed")

    cohort = daily_state.get("miner_cohort", {})
    tilt = cohort.get("tilt_label", "none")
    dom = cohort.get("dominant_pool", "na")

    irq = daily_state.get("irreversibility", {})
    irq_band = irq.get("band", "reversible")
    irq_index = irq.get("index", 0.0)

    rei = daily_state.get("resolution", {})
    rei_band = rei.get("band", "dormant")
    rei_index = rei.get("index", 0.0)

    oracle_hash = daily_state.get("oracle_input_hash")
    if oracle_hash:
        short_oih = oracle_hash[-8:]
        oih_part = f"OIH={short_oih}"
    else:
        oih_part = None

    parts = [
        "CWSPINE v0.1",
        date_utc,
        f"R={regime_label},{regime_phase}",
        f"CTI={cti_str}",
        f"CUST={custody_dir}({custody_streak})",
        f"ENT={entropy_trend}",
        f"PC={price_corridor}",
        f"ID={id_str}",
        f"IC={ic_str}",
        f"RC={rc_str}",
        f"HR={hr_trend},{hr_band},{hr_score:.1f}",
        f"TH={th_band},{th_index:.2f}",
        f"EP={eband},{eti:.2f}",
        f"MC={tilt},{dom}",
        f"IRQ={irq_band},{irq_index:.2f}",
        f"REI={rei_band},{rei_index:.2f}",
    ]

    if oih_part:
        parts.append(oih_part)

    return " | ".join(parts)