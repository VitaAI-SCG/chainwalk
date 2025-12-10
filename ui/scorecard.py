def render_scorecard(state):
    # Enforce language
    outcome = state.get("outcome", "").lower()
    prohibited = ["maybe", "looks like", "i think", "i feel", "probably", "guess"]
    if any(word in outcome for word in prohibited):
        raise ValueError("Prohibited language in outcome")

    # Regime badge
    regime = state.get("regime_label", "UNKNOWN")
    badge = state.get("regime_symbol", "[UNKNOWN]")

    # CTI bar
    cti = state.get("cti", 0)
    filled_blocks = int(cti / 2)  # 0.5 per block
    bar = "#" * filled_blocks + "|" if cti % 2 >= 1 else "#" * filled_blocks
    bar += "-" * (10 - len(bar))

    # Streak and flips
    streak = state.get("streak", 0)
    flips = state.get("flips", 0)

    # Build the compact card
    card = f"""[CHAINWALK SCORECARD — TODAY · {state.get('date', 'UNKNOWN')}]
REGIME: {regime} {badge} (streak {streak}, flips {flips})
CTI: {bar} {cti:.1f}/10 — {state.get('cti_label', 'tension stored')}
CUSTODY: -> {state.get('custody_direction', 'UNKNOWN')} (streak {state.get('custody_streak', 0)})
ENTROPY: {state.get('entropy_trend', 'UNKNOWN')}
PRICE CORRIDOR: {state.get('price_corridor', 'UNKNOWN')}
OUTCOME: {state.get('outcome', 'UNKNOWN')}
RULE: Price does not lead the chain. The chain leads price.
"""

    print(card)

    # Save to file for reference
    import os
    reports_dir = os.path.join(os.path.dirname(__file__), '..', 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    scorecard_path = os.path.join(reports_dir, 'scorecard_latest.md')
    with open(scorecard_path, 'w', encoding='utf-8') as f:
        f.write(card)

