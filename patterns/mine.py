"""Hledání vzorců s oddělenou validací: výběr jen na 2016–2021 (IS), ověření na 2022–2026 (OOS).
Metrika = přínos filtru nad stejnou šablonou obchodovanou každý den (= long bez podmínky)."""
import numpy as np, pandas as pd
OUT = "reports/patterns"
R = pd.read_pickle(f"{OUT}/sablony_R.pkl"); F = pd.read_pickle(f"{OUT}/vlastnosti.pkl")
SPLIT = pd.Timestamp("2022-01-01"); IS = R.index < SPLIT; OOS = ~IS
rows = []
for t in R.columns:
    r = R[t]
    base_is, base_oos = r[IS].mean(), r[OOS].mean()
    for f in F.columns:
        if f == "VŠECHNY DNY": continue
        m = F[f].values
        a, b = r[m & IS].dropna(), r[m & OOS].dropna()
        if len(a) < 80 or len(b) < 40: continue
        rows.append(dict(sablona=t, filtr=f, n_IS=len(a), R_IS=a.mean(), prinos_IS=a.mean() - base_is,
                         t_IS=(a.mean() - base_is) / (a.std() / np.sqrt(len(a))),
                         n_OOS=len(b), R_OOS=b.mean(), prinos_OOS=b.mean() - base_oos,
                         t_OOS=(b.mean() - base_oos) / (b.std() / np.sqrt(len(b))),
                         t_abs_OOS=b.mean() / b.std() * np.sqrt(len(b))))
M = pd.DataFrame(rows); M.to_csv(f"{OUT}/vsechny_testy.csv", index=False)
print("testů:", len(M))
top = M.sort_values("t_IS", ascending=False).head(30)
pd.set_option("display.width", 260); pd.set_option("display.max_colwidth", 60)
print("\n=== TOP 30 podle IS (2016–2021) a jejich OOS (2022–2026) ===")
print(top[["sablona", "filtr", "n_IS", "R_IS", "prinos_IS", "t_IS", "n_OOS", "R_OOS", "prinos_OOS", "t_OOS"]].round(3).to_string(index=False))
k = (top.prinos_OOS > 0).mean()
print(f"\nZ top 30 IS má kladný přínos i v OOS: {k*100:.0f} % (čistá náhoda ≈ 50 %)")
# robustnost filtru: v kolika šablonách je přínos kladný v IS i OOS
g = M.groupby("filtr").agg(sablon=("sablona", "size"), IS_kladne=("prinos_IS", lambda s: (s > 0).mean()),
                           OOS_kladne=("prinos_OOS", lambda s: (s > 0).mean()), prinos_IS=("prinos_IS", "mean"),
                           prinos_OOS=("prinos_OOS", "mean"), t_IS=("t_IS", "median"), t_OOS=("t_OOS", "median"))
g["oba_kladne"] = M.assign(ok=(M.prinos_IS > 0) & (M.prinos_OOS > 0)).groupby("filtr").ok.mean()
print("\n=== Filtr napříč všemi šablonami (průměrný přínos v R) ===")
print(g.sort_values("prinos_IS", ascending=False).round(3).to_string())
g.to_csv(f"{OUT}/filtry_souhrn.csv")
# základ: šablony na všech dnech
base = pd.DataFrame({"R_IS": R[IS].mean(), "t_IS": R[IS].mean() / R[IS].std() * np.sqrt(R[IS].count()),
                     "R_OOS": R[OOS].mean(), "t_OOS": R[OOS].mean() / R[OOS].std() * np.sqrt(R[OOS].count()), "n": R.count()})
base.to_csv(f"{OUT}/sablony_vsechny_dny.csv")
print("\n=== Šablony bez filtru (long každý den), nejlepší podle IS ===")
print(base.sort_values("t_IS", ascending=False).head(12).round(3).to_string())
