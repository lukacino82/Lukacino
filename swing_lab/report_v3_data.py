"""Assemble every number for report v3 (correction alpha) into results/report_v3_data.json."""
import json

import numpy as np
import pandas as pd

from correction_model import labels
from lab import Lab
from sieve import RES

NAMES = {
    "LMT_RSI#<#_#ATR": "Limitní nákup k·ATR pod close po oversold RSI",
    "C<dvwap#sd": "Close pod denním VWAP − k σ",
    "C<wvwap#sd": "Close pod týdenním VWAP − k σ",
    "C06": "Reclaim krátké MA (3/5/10) po drawdownu",
    "P_Hi#DD>#&RSI#<#": "Drawdown od 20/50d high + RSI(2) potvrzení",
    "IBS<#": "IBS (close u denního low)",
    "WR#<#": "Williams %R extrém",
    "D01": "Close pod týdenním/měsíčním VWAP pásmem",
    "CloseAt#dLow": "Close na N-denním minimu",
    "RSI#<#": "RSI(2–5) oversold",
    "P_Hi#DD>#&IBS<#": "Drawdown od high + IBS potvrzení",
    "ConnorsRSI<#": "Connors RSI extrém",
    "A01": "A01 série nižších close", "A02": "A02 vážená série ztrát", "A03": "A03 kumulativní pokles v percentilu",
    "A04": "A04 ATR shock", "A05": "A05 akcelerující výprodej", "A06": "A06 decelerující korekce",
    "A07": "A07 failed breakdown", "A08": "A08 outside reversal", "A10": "A10 higher-low potvrzení",
    "A11": "A11 gap down recovery", "A12": "A12 retest korekčního low",
    "B01": "B01 drawdown ladder", "B02": "B02 rychlost drawdownu", "B03": "B03 time-under-water",
    "B04": "B04 recovery fraction", "B05": "B05 archetyp V/W",
    "C01": "C01 RSI2 v bull režimu", "C04": "C04 vzdálenost od MA v ATR", "C05": "C05 MA stack pullback",
    "C07": "C07 Double 7/10", "C08": "C08 momentum failure",
    "D03": "D03 multi-anchor VWAP", "D04": "D04 VWAP undercut + reclaim", "D05": "D05 AVWAP od shock baru",
    "E01": "E01 sweep + reclaim VAL", "E02": "E02 návrat do value", "E04": "E04 POC roste při slabé ceně",
    "E05": "E05 překryv value areas", "E07": "E07 naked POC",
    "F01": "F01 delta z-score exhaustion", "F02": "F02 price/delta divergence",
    "F03": "F03 effort without result", "F05": "F05 delta climax + flip",
    "F06": "F06 CVD vs cena", "F09": "F09 failed negative continuation",
    "G01": "G01 weakness + location + trigger", "G02": "G02 drawdown + delta + VAL", "G03": "G03 dvoustupňový vstup",
    "P_NewLow#&NoCDLow": "Nové low bez nového low kumulativní delty",
    "P_Down#&BelowW#ATR": "N down dnů pod týdenním VWAP (ATR)",
    "P_Down#&BelowM#ATR": "N down dnů pod měsíčním VWAP (ATR)",
}


def main():
    lab = Lab()
    s0 = lab.start_i
    d = lab.d
    fam = pd.read_csv(RES / "final_families.csv")
    fam["label"] = fam.family.map(lambda f: NAMES.get(f, f))
    books = pd.read_csv(RES / "final_books.csv", index_col=0)
    wf = json.load(open(RES / "wf_families.json"))
    cm = json.load(open(RES / "correction_model.json"))

    # conditional hit rates: does the correction state actually shift the odds?
    y, mfe, mae = labels(d, 1.0, 1.0, 20)
    ok = np.isfinite(y)
    ok[:s0] = False
    buckets = []
    for lo, hi, nm in [(-1, -0.20, "20 %+"), (-0.20, -0.15, "15–20 %"), (-0.15, -0.10, "10–15 %"),
                       (-0.10, -0.075, "7,5–10 %"), (-0.075, -0.05, "5–7,5 %"), (-0.05, -0.03, "3–5 %"),
                       (-0.03, -0.02, "2–3 %"), (-0.02, -0.01, "1–2 %"), (-0.01, 0.001, "0–1 %")]:
        m = ok & (d.dd.values > lo) & (d.dd.values <= hi)
        buckets.append(dict(bucket=nm, n=int(m.sum()), hit=round(float(y[m].mean()), 3),
                            mfe=round(float(mfe[m].mean()), 2), mae=round(float(mae[m].mean()), 2)))
    conds = []
    for nm, col in [("Všechny dny", None), ("2 nižší close", "downdays>=2"), ("3 nižší close", "downdays>=3"),
                    ("4 nižší close", "downdays>=4"), ("5 nižších close", "downdays>=5"),
                    ("Decelerující korekce", "decel_down"), ("Akcelerující výprodej", "accel_down"),
                    ("Nové low bez low delty", "cvd_higher_low"), ("Effort without result", "effort_no_result"),
                    ("Delta climax + flip", "climax_flip"), ("Failed breakdown 10d", "sweep10"),
                    ("Outside reversal", "outside_rev"), ("Retest korekčního low", "retest_low"),
                    ("Gap down + recovery", "gap_down_recover")]:
        if col is None:
            m = ok
        elif ">=" in col:
            c_, v = col.split(">=")
            m = ok & (d[c_].values >= float(v))
        else:
            m = ok & d[col].fillna(False).values.astype(bool)
        if m.sum() < 30:
            continue
        conds.append(dict(name=nm, n=int(m.sum()), hit=round(float(y[m].mean()), 3),
                          mfe=round(float(mfe[m].mean()), 2), mae=round(float(mae[m].mean()), 2)))

    out = dict(
        families=fam.sort_values("alpha_t", ascending=False).to_dict("records"),
        books=books.reset_index().rename(columns={"index": "book"}).to_dict("records"),
        curves=json.load(open(RES / "final_curves.json")),
        wf=wf, wf_curves=json.load(open(RES / "wf_families_curves.json")),
        years=pd.read_csv(RES / "final_years.csv", index_col=0).reset_index().to_dict("records"),
        buckets=buckets, conds=conds, model=cm,
        n_setups=int(len(pd.read_parquet(RES / "grid.parquet").setup.unique())),
        n_tested=int(len(pd.read_parquet(RES / "grid.parquet"))),
    )
    json.dump(out, open(RES / "report_v3_data.json", "w"), default=float)
    print("families", len(fam), "beat", int(fam.beats_bh.sum()), "tested", out["n_tested"])


if __name__ == "__main__":
    main()
