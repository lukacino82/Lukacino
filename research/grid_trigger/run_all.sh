#!/bin/sh
# resumable: every finished chunk is kept in out/parts
cd "$(dirname "$0")"
for w in points atr_d atr_h atr_w; do python3 grid_run.py $w || exit 1; done
[ -f out/D_vwap_filtr.csv ] || python3 vwap_run.py
echo ALL_DONE
