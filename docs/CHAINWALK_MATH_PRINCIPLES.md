# ChainWalk Mathematical Principles

## Normalization Formulas

ChainWalk operates on normalized constraint spaces to enable fusion across disparate domains.

### CTI Normalization
```
CTI_norm = CTI / 10 ∈ [0,1]
```
Maps Chain Tension Index to unit interval for weighted fusion.

### Custody Normalization
```
custody_norm = min(custody_streak / 10, 1) ∈ [0,1]
```
Caps custody streak influence at 10 blocks to prevent unbounded scaling.

### MTI Direct
MTI ∈ [0,1] by construction, requiring no additional normalization.

### ETI Direct
ETI ∈ [0,1] by construction.

## Regime Hamiltonian Overview

The Regime Hamiltonian models Bitcoin's incentive landscape as a quantum-like system with probabilistic state evolution.

### Basis States
```
|COMPRESSION⟩, |ASCENT⟩, |DISTRIBUTION⟩, |STARVATION⟩
```

### Expectation Operator
```
E[regime] = Σ p_i × index_i
```
Where index mapping: COMPRESSION=-2, ASCENT=-1, DISTRIBUTION=1, STARVATION=2.

### Hamiltonian Components
- **H_chain_tension**: CTI-driven compression bias
- **H_custody_vector**: Supply flow directionality
- **H_entropy_flux**: Network complexity gradients
- **H_price_corridor**: Legality floor constraints

### Evolution Equation
```
∂|ψ⟩/∂t = -iH|ψ⟩
```
Where H is the time-dependent Hamiltonian incorporating daily constraint updates.

## Entropy Flux Mapping

Entropy flux quantifies information flow through Bitcoin's transaction graph.

### Block Entropy (H)
```
H = -Σ p_i log p_i
```
Shannon entropy of transaction size distribution per block.

### Complexity (K)
```
K = H × log₂(N)
```
Where N is transaction count, capturing structure density.

### Flux Gradient
```
∇H = (H_today - H_7d_avg) / H_7d_std
```
Normalized entropy trend over 7-day window.

### Polyphony Detection
Blocks with H > μ_H + σ_H and K > μ_K + σ_K are classified polyphonic, indicating multi-modal activity.

## Threshold Equations

### Irreversibility Thresholds

#### Reversible Band
```
IRQ < 0.45
```
Tension can dissipate without systemic liquidation.

#### Primed Band
```
0.45 ≤ IRQ < 0.78
```
Unwind possible but requires external energy input.

#### Irreversible Band
```
IRQ ≥ 0.78 ∧ regime ∈ {COMPRESSION, STARVATION}
```
Structural lock-in; optionality eliminated.

#### Protocol Floor
```
IRQ ≥ 0.90 ∧ MTI ≥ 0.85 ∧ CTI ≥ 6.5
```
Price becomes epiphenomenal to protocol enforcement.

### Miner Threshold Bands

#### Critical
```
regime ∈ {COMPRESSION, STARVATION} ∧ stress_score ≥ 0.7 ∧ CTI ≥ 6.5
```
Liquidity cliff activated.

#### Strained
```
regime ∈ {COMPRESSION, STARVATION} ∧ stress_score ≥ 0.4 ∧ CTI ≥ 4.5
```
Threshold zone entry.

#### Amber
```
regime ∈ {COMPRESSION, STARVATION} ∧ (stress_score ≥ 0.2 ∨ CTI ≥ 3.0)
```
Approaching danger zone.

### Epoch Tension Bands

#### Overclocked
```
ETI ≥ 0.7
```
Difficulty adjustment under extreme pressure.

#### Balanced
```
0.3 ≤ ETI < 0.7
```
Nominal adjustment stress.

#### Relaxed
```
ETI < 0.3
```
Minimal epoch pressure.

## Hard Gating Rules

### Irreversibility Gating
Irreversibility (🟥, ⬛) can only occur within protocol pressure regimes:
```
regime ∈ {COMPRESSION, STARVATION}
```
Outside these states, maximum band is 🟧 Primed.

### Floor Conditions
Protocol floor (⬛) requires simultaneous extreme conditions:
```
MTI ≥ 0.85 ∧ CTI ≥ 6.5 ∧ IRQ ≥ 0.90
```
Ensures floor is rare and unambiguous.

### Regime Coherence
Regime labels are deterministic functions of CTI:
```
regime = f(CTI) where f is piecewise constant
```
No hysteresis; state transitions are immediate.

### Index Bounds
All indices are clamped to [0,1]:
```
∀ index ∈ {CTI_norm, MTI, ETI, IRQ, custody_norm}: index ∈ [0,1]
```
Prevents numerical instability in fusion operations.

## Fusion Invariants

### Weighted Sum Conservation
Fusion weights sum to unity:
```
Σ w_i = 1 for all fusion operations
```

### Monotonicity
Higher constraint values cannot decrease fused indices:
```
∂(fused_index)/∂component ≥ 0 ∀ components
```

### Regime Conditioning
Fusion weights adapt to regime state:
```
w_i = w_i(regime) where regime modulates emphasis
```

## Conclusion

ChainWalk's mathematics transform Bitcoin's incentive structure into a deterministic system. Normalization enables cross-domain fusion, Hamiltonian modeling captures state evolution, entropy flux maps information dynamics, and threshold equations define phase transitions. Hard gating rules ensure physical consistency, making ChainWalk a rigorous framework for protocol analysis.