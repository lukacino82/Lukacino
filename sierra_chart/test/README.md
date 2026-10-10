# Testovaci harness

Simulator ACSIL rozhrani, aby se dala logika study ověřit bez Sierra Chart.
`sierrachart.h` tady je **mock**, ne skutečná hlavička — simuluje ordery,
attached OCO brackety, fily podle ceny, netto pozici a `MaximumPositionAllowed`.

```
g++ -std=c++14 -I. -o test test_main.cpp ../LukacinoAutoTrader.cpp && ./test
```

Pokrývá: otevření vstupu, blokaci v režimu Both a odpal po přepnutí Mode,
manuální trigger, zásah TP i SL, full auto re-entry, trailing per position,
kill switch a odmítnutí vstupu kvůli cizí pozici v DOM.
