"""A/B day classification and hypothesis generation, consuming live_state.csv.

See ARCHITECTURE.md ("Not built yet") for what this package is for: this is
the Python side that reads the VWAP tiers and cumulative delta ACSIL writes
to `live_state.csv` and turns them into the same style of read the
`trading-vwap-hypotezy` skill produces from screenshots (structural bias
across tiers, absorption/divergence, A-day/B-day regime).
"""
