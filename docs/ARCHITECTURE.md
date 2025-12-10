# ARCHITECTURE • CHAINWALK



graph TD
A[Block Catalog] --> B[Signal Extractor]
B --> C[Constraint Stack]
C --> D[Irreversibility Engine]
D --> E[Resolution Field]
E --> F[Uncertainty Physics Engine]
F --> G[APEX Deck]
G --> H[Oracle Calibration]
H --> I[Alert Rail]


ChainWalk is a **one-directional pipeline**:

Inputs:  
- block structure  
- miner incentives  
- custody dynamics  
- mempool desire  

Never price.

Outputs:  
- constraint geometry  
- inevitability index  
- sovereign oracle surface