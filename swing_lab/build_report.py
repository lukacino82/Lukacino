"""Render results/report_data.json + family / exit tables into results/ES_SWING_LAB_REPORT.html"""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
LABELS = {
    "LMT_Down#_#ATR": "Limit nákup 0,25–0,5 ATR pod close po 3 down dnech",
    "DeltaZ<#": "Den s extrémně negativní deltou (z-score < −1…−2)",
    "TurnaroundMon": "Down pondělí → long",
    "C<prev_qvwap": "Close pod VWAP minulého kvartálu",
    "IBS<#": "IBS < 0,1–0,3 (close u low dne)",
    "DownDays>=#": "2–5 down closes za sebou",
    "C<prev_wvwap": "Close pod VWAP minulého týdne",
    "SweepPrevWeekVAL": "Low pod VAL minulého týdne, close zpět nad",
    "TurtleSoup#": "Turtle Soup (falešné proražení 20d low)",
    "LMT@prevWeekVAL": "Limit nákup na VAL minulého týdne",
    "Breakout#dHigh": "Close na 10/20/50denním high",
    "C<wvwap#sd": "Close pod týdenním VWAP − k·σ",
    "LowerLows>=#": "2–5 nižších low za sebou",
    "CumRSI#x#<#": "Kumulativní RSI(2)",
    "C<dvwap#sd": "Close pod denním VWAP − k·σ",
}
d = json.load(open(RES / "report_data.json"))
f = pd.read_csv(RES / "families_full.csv")
f = f[f.family.isin(LABELS)].head(15)
d["families"] = [dict(label=LABELS[r.family] + (" · trend MA200" if r.rclass == "LT_bull" else ""), n=int(r.n),
                      pos_disc=r.pos_disc, pos_val=r.pos_val, pos_oos=r.pos_oos, med_pf=r.med_pf, med_expo=r.med_expo)
                 for r in f.itertuples()]
e = pd.read_csv(RES / "exit_league.csv").sort_values("cons", ascending=False)
d["exits"] = e.to_dict("records")
for k in ("canon_curves",):
    d.pop(k, None)
html = (HERE / "report_template.html").read_text().replace("/*DATA*/", json.dumps(d, ensure_ascii=False))
(RES / "ES_SWING_LAB_REPORT.html").write_text(html)
print("ok", len(html))
