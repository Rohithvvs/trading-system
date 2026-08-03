# Platform regime → RE-001 Bull / Sideways / Bear / UNKNOWN

| Platform signals (examples) | RE-001 bucket |
| --------------------------- | ------------- |
| FAVORABLE / FAV + new_entry_allowed | Bull |
| CAUTIOUS / NEU / MIXED | Sideways |
| DEFENSIVE / DEF / HIGHRISK / new_entry_allowed=False / BEARISH trend | Bear |
| Missing / UNKNOWN / failed classification | UNKNOWN → REJECT |

Exact enum matching is implemented in `regime.py`.
