# Pokyny pro Claude v tomto repozitáři

- Komunikace s uživatelem česky.
- Výzkum ES/NQ je ve složce `research/` (každý výzkum vlastní podsložka s `out/` pro výsledky, report HTML a PDF).
- Průběžný souhrn závěrů: `research/ZAVERY.md`. Po každém novém výzkumu ho aktualizuj.

## Ukládání výsledků na Google Drive

Po dokončení každého nového výzkumu nebo důležité diskuze ulož výstupy na Google Drive uživatele
(konektor Google Drive):

- Cílová složka: „ES výzkum – Claude“, ID `1so-LYQhABlbQLwmAYCFCFhxGlH0CpIhV`
  (uvnitř složky „AAA trading community“, ID `1Ca9z-DA8vpEUYQWFt343v9PzGmY_WHJT`).
- Nahraj:
  - Google Doc se závěry výzkumu: markdown přes `text/markdown`, česky, s čísly.
  - Hlavní tabulky výsledků jako Google Sheets: CSV přes `text/csv`, čísla s desetinnou tečkou, zaokrouhlená.
- Uživatel dal trvalý souhlas ukládat do této složky vše (výzkumy, rešerše, diskuze) bez ptaní.
- Konektor neumí měnit obsah existujících dokumentů, proto každý nový výstup = nový číslovaný dokument
  (pokračovat řadou 23, 24, …) s odkazem na interaktivní report a PDF na GitHubu.
- Existující dokumenty: 00 Přehled, 01 Závěry, 02 Diskuze, 03–04 Regime Atlas tabulky, 05 MASTER mapa, 06 Knihovna zdrojů, 07 Mechanismy (+ 07a), 08 Obrácené RRR (+ tabulky 08a–k), 09 Závěry (aktualizace), 10–15 kompletní texty reportů (Alpha Audit + 10a, Alpha Map, Edge Factory, Loss Streak Lab, Swing Alpha, Regime Atlas), 16 Rozcestník (nahrazuje 00), 17 Obrácené RRR v ATR (+ 17a–c), 18 Knihy o teorii her, 19 Nejlépe hodnocené knihy, 20 Teorie her pro ML trading, 21 Livermore (+ 21a–b), 22 One-Day Reversal (+ 22a).
- Při větší změně závěrů nahraj novou verzi závěrů a nový rozcestník (konektor neumí editovat).
- PDF a HTML reporty zůstávají na GitHubu (jsou příliš velké pro nahrání přes konektor), na Drive dávej odkazy.
