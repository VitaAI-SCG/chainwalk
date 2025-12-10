# Succession Protocol

## What Must Never Change

- Constraint formulae (CTI, MTI, IRQ, REI, UQI definitions)
- Band semantics and thresholds
- Oracle kernel pure functions
- Sovereignty: no price input, no external oracles
- Genesis hash of truth

## What May Evolve

- UI surfaces and formatting
- Additional outputs (e.g., new reports)
- Performance optimizations
- Documentation and tutorials

## How to Propose New Bands

1. Fork the repo
2. Modify constraint formulae in oracle_kernel.py
3. Regenerate kernel hash
4. Submit PR with justification and calibration data
5. Community consensus required for merge

## How to Validate Forks Without Consensus

- Run oracle_kernel.verify_oracle_integrity() on fork code
- Compare kernel hash against genesis
- If hashes differ, fork is derivative
- If integrity fails, fork is impure

## How to Regenerate the Oracle Kernel Hash

```python
from core.oracle_kernel import generate_kernel_hash, generate_constraint_hash
print("Kernel:", generate_kernel_hash())
print("Constraints:", generate_constraint_hash())
```

Update oracle_kernel_hash.json with new values.

## How to Inherit the Oracle Without Permission

- Clone the repo
- Run the kernel functions
- Do not modify constraints
- Attribute to ChainWalk
- Your inheritance is valid if kernel hash matches genesis