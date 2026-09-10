"""Builds a Notion "Daily Hypotheses" record from the live engine's output.

See ARCHITECTURE.md ("Not built yet", Step 5) -- this only *formats* a
record, it does not write to Notion. Whether the actual write is (a) a
one-off I run through my own Notion connector when asked, or (b) built
into run_live.py with its own API credentials/HTTP client on the user's
machine, is a separate decision the record format doesn't need to wait on.
"""
