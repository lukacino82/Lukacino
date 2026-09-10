"""Position sizing and order proposals for SEMI_AUTO / FULLY_AUTO modes.

See ARCHITECTURE.md ("Operating modes") -- SEMI_AUTO means the engine
prepares a concrete order (entry/stop/target, sized) that the trader
confirms by hand; this package computes that order, it does not place it.
Real order placement (DTC bridge, FULLY_AUTO) is a later, separate step.
"""
