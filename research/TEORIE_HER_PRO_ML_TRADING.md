# Teorie her prakticky pro ML algo trading (23. 10. 2026)

## Krátká odpověď
Ano, ale ne klasická teorie her z učebnic (Nashovy rovnováhy, maticové hry). Trh není hra se známými pravidly a výplatami, takže rovnováhu nejde spočítat jako v pokeru. Prakticky použitelná je větev **„učení ve hrách“** (online learning, minimalizace lítosti, bandity). Na ní stojí pokerové boty i přístup Equilibre a dá se naprogramovat na našich datech. Druhá použitelná větev jsou **herní modely mikrostruktury trhu**: z nich vycházejí vstupní proměnné pro ML a simulátory trhu.

## 1. Přímo použitelné hned (naše data stačí)
| Zdroj | Co dává | Jak to použít u nás | Odkaz |
|---|---|---|---|
| Elad Hazan: Introduction to Online Convex Optimization (2. vyd. 2022) | Algoritmy s garancí lítosti (Hedge, online gradient), zdarma na arXiv | Adaptivní alokátor mezi našimi vrstvami (vol target, crisis allocator, medvědí momentum, signály A/B): váhy se každý den upravují podle výsledků bez znalosti budoucnosti | https://arxiv.org/abs/1909.05207 |
| Cesa-Bianchi & Lugosi: Prediction, Learning, and Games (2006) | Teorie „učení s radou expertů“ = přesně model „více strategií, jedna peněženka“ | Garance: alokátor bude dlouhodobě skoro tak dobrý jako nejlepší strategie zpětně, aniž by ji znal předem | kniha (Cambridge UP) |
| Lattimore & Szepesvári: Bandit Algorithms (2020) | Bandity (EXP3, UCB, Thompson) – rozhodování „kterou strategii teď hrát“ | Výběr režimu/strategie, když vidíme jen výsledek té, kterou hrajeme | koncept zdarma (draft): https://ece.iisc.ac.in/~aditya/E1245_Online_Prediction_Learning_F2018/lattimore-szepesvari18bandit-algorithms.pdf |
| Li & Hoi: Online Portfolio Selection: A Survey + OLPS toolbox | Hotové algoritmy (universal portfolio, EG, mean reversion OLMAR…), kód | Kombinace více trhů nebo strategií; benchmark pro náš alokátor | https://arxiv.org/abs/1212.2129 , https://www.jmlr.org/beta/papers/v17/15-317.html |

## 2. Použitelné s lepšími daty (tick / order book)
| Zdroj | Co dává | Co potřebujeme | Odkaz |
|---|---|---|---|
| Kyle (1985), Glosten–Milgrom (1985); O'Hara: Market Microstructure Theory | Herní model informovaného obchodníka, market makera a šumových obchodníků | Inspirace pro proměnné do ML: tlak toku příkazů (delta, imbalance), cenový dopad (Kyle lambda). Delta už máme od 2010. | učebnice O'Hara |
| Avellaneda & Stoikov (2008): High-frequency trading in a limit order book | Optimální kotování market makera (řízení inventáře) | Tick/MBO data a nízké náklady; pro nás spíš pro pochopení, kdo stojí na druhé straně | https://math.nyu.edu/~avellane/HighFrequencyTrading.pdf |
| Cardaliaguet & Lehalle (2018): Mean field game … trade crowding | Hra mnoha obchodníků, kteří se navzájem ovlivňují (crowding) | Akademické; vysvětluje, proč známé edge mizí (náš nález po 2021) | https://arxiv.org/abs/1610.09904 |
| Cartea, Jaimungal, Penalva: Algorithmic and High-Frequency Trading (2015) | Optimální exekuce a market making | Tick data | kniha (Cambridge UP) |

## 3. „Aréna“ – multiagentní simulace trhu
| Zdroj | Co dává | Odkaz |
|---|---|---|
| ABIDES (J.P. Morgan AI Research) | Open-source simulátor burzy s tisíci agentů (market makeři, momentum, value, šum) + ABIDES-Gym pro reinforcement learning | https://arxiv.org/abs/1904.12066 , https://github.com/abides-sim/abides |

Použití: trénovat RL agenta proti „nuceným hráčům“ v simulaci a historii ES nechat jen jako závěrečnou zkoušku (náš nápad Aréna). Riziko: agent se naučí chyby simulátoru, ne trh.

## Co z toho NEFUNGUJE přímo
- **CFR a pokerové solvery:** potřebují hru s pevnými pravidly a výplatami, kterou trh nemá. Přenositelný je jen princip minimalizace lítosti (sekce 1).
- **Výpočet Nashovy rovnováhy trhu:** neznáme hráče ani jejich výplaty.
- **Žádný z těchto zdrojů edge nevytvoří.** Online learning jen rychleji přesouvá kapitál mezi strategiemi, které edge mají, a odstavuje ty, které ji ztratily. To je přesně problém, který jsme viděli (edge mizí po 2018 a 2021).

## Doporučený praktický krok
Postavit **regret-minimizing alokátor** (Hedge/EXP3) nad vrstvami, které už máme denní řady:
1. **Vstupy:** buy & hold, vol target, crisis allocator, jádro fade, medvědí momentum, signály A/B a short po propadu.
2. **Walk-forward od 2009:** váhy se mění jen podle minulých výsledků.
3. **Srovnání:**
   - stejné váhy;
   - nejlepší strategie zpětně;
   - B&H.
4. **Kill kritérium:** automaticky z výpočtu lítosti.
