# Call Copilot – AI našeptávač pro telefonní hovory

Webová appka: mikrofon → přepis řeči (Web Speech API, `cs-CZ`) → Claude v reálném čase
navrhuje, co má operátor říct dál.

## Spuštění
```bash
export ANTHROPIC_API_KEY=sk-ant-...
node server.js            # http://127.0.0.1:3000
```
Volitelně: `PORT`, `HOST`, `MODEL` (výchozí `claude-haiku-5-5` – nejnižší latence).

Otevři v **Chrome/Edge** (Web Speech API; Firefox nepodporuje). Mikrofon funguje jen na
`localhost` nebo přes HTTPS.

## Jak zachytit oba konce hovoru
Prohlížeč slyší jen mikrofon. Možnosti:
- hovor na hlasitý odposlech (mikrofon zachytí obě strany),
- nebo virtuální kabel (VB-Cable / BlackHole / Loopback), který smíchá hlas operátora
  a zákazníka do jednoho vstupu a nastavíš ho jako výchozí mikrofon.

Web Speech API nerozlišuje mluvčí. Tlačítkem (nebo klávesou **Mezerník** mimo textová pole)
přepínáš označení mluvčího Auto / Operátor / Zákazník; v režimu Auto ho odhadne model z kontextu.

## Poznámky
- Bez mikrofonu můžeš flow vyzkoušet přes textové pole „Simulovat repliku“.
- Přepis se posílá na tvůj server a odtud do Claude API – ošetři souhlas s nahráváním/GDPR.
- Web Speech API v Chrome posílá audio Googlu; pro produkci zvaž vlastní STT (Deepgram, Whisper…).

## Znalostní báze
Dokumenty (`.md`, `.txt`, `.csv`, `.json`) nahraješ v UI (Nastavení hovoru → Znalostní báze)
nebo je dáš do složky `knowledge/`. Server je rozdělí na úryvky podle nadpisů a odstavců
a při každém návrhu vyhledá (BM25, bez diakritiky a s hrubým stemmingem pro češtinu)
úryvky nejpodobnější posledním replikám hovoru. Claude je dostane jako podklad, čerpá
z nich fakta/ceny/odpovědi na námitky a v UI zobrazí zdroj (`📚 Zdroj: …`).
Pro nejlepší výsledky piš dokumenty jako sekce s nadpisem (`# Námitka: je to drahé`)
a konkrétní odpovědí. Ukázka: `knowledge/ukazka-faq.md`.
Pro velké báze (stovky stran) lze BM25 nahradit embeddingy.

## Osobní použití na PC (doporučeno)
```bash
export ANTHROPIC_API_KEY=sk-ant-...      # Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
node server.js                            # http://localhost:3000  (potřebuje Node 18+)
```
Server poslouchá jen na `localhost`. Otevři v Chrome/Edge. Volitelně `MODEL` (návrhy, výchozí
`claude-haiku-5-5`) a `NOTES_MODEL` (zápisy, výchozí `claude-sonnet-5-5`).

### Zdarma / bez Claude API
Appka umí i jiné modely přes OpenAI-kompatibilní API (`LLM_BASE_URL`, `MODEL`, volitelně `LLM_API_KEY`):
```bash
# a) Ollama – běží lokálně na tvém PC, zdarma (stáhni z ollama.com, pak: ollama pull qwen2.5:7b)
LLM_BASE_URL=http://localhost:11434/v1 MODEL=qwen2.5:7b node server.js
# b) Groq – bezplatný limit (klíč z console.groq.com)
LLM_BASE_URL=https://api.groq.com/openai/v1 LLM_API_KEY=gsk_... MODEL=llama-3.3-70b-versatile node server.js
# c) Google Gemini – bezplatný limit (klíč z aistudio.google.com)
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai LLM_API_KEY=... MODEL=gemini-2.0-flash node server.js
```
Pro „přemýšlející“ modely (např. `openai/gpt-oss-120b` na Groq) nastav pro rychlejší odpovědi `LLM_REASONING_EFFORT=low`.
Bezplatné limity a názvy modelů se mění – ověř je u poskytovatele. Menší/bezplatné modely bývají
v češtině slabší než Claude a hůř drží JSON formát.

### Průběh cold callu
1. Vyplň **lead** (jméno, firma, poznámky) a jednou **cíl** + **skript** v Nastavení hovoru.
2. Zavolej z telefonu na **hlasitý odposlech** a polož ho k mikrofonu PC (nebo použij virtuální kabel).
   Klikni **Začít hovor**.
3. Vpravo v **Našeptávači** vidíš větu k řečení, fázi, náladu, zájem, námitku a zdroj ze znalostní báze.
4. **Ukončit hovor** → automaticky vznikne **Zápis** (shrnutí, výsledek, skóre leadu, potřeby, námitky,
   další kroky, hotový follow-up e-mail/SMS, koučink) a uloží se do `calls/`. Najdeš ho v **Historii**,
   jde zkopírovat nebo stáhnout jako `.md`.
5. V zápisu jsou **poučení pro znalostní bázi** – jedním klikem je přidáš (`knowledge/z-hovoru.md`).
   Báze tak roste s každým hovorem. Můžeš ji také ručně doplňovat (rychlé přidání, nahrání souboru,
   úprava dokumentů, nebo prostě soubory do složky `knowledge/` – index se obnoví sám).

Rozdělaný hovor se po obnovení stránky obnoví. `calls/` a tvá znalostní báze jsou v `.gitignore`
(neposílají se na GitHub).

### Právní poznámka
Přepis hovoru je záznam hovoru a obsahuje osobní údaje. Informuj volaného, že hovor zaznamenáváš/přepisuješ,
a přepis posílá Google (rozpoznávání řeči v Chrome) a Anthropic (návrhy a zápisy).

## Nasazení na sdílený hosting (starší, základní verze – bez zápisů a historie hovorů)
Active24 sdílený hosting nespouští Node, proto je tu ekvivalentní PHP backend (`php/api.php`).
```bash
./build-php.sh        # vytvoří dist/copilot/
```
1. Nahraj obsah `dist/copilot/` přes FTP do `rentez.eu/copilot/` (včetně skrytých `.htaccess`).
2. Na hostingu zkopíruj `config.sample.php` → `config.php`, doplň `anthropic_api_key` a `password_hash`
   (`php -r "echo password_hash('heslo', PASSWORD_DEFAULT);"`).
3. V administraci Active24 zapni HTTPS (Let's Encrypt) – mikrofon funguje jen přes HTTPS.
4. Otevři `https://rentez.eu/copilot/`, přihlas se heslem.

Backend je za přihlášením (session cookie), takže cizí návštěvníci nemohou čerpat tvůj API klíč.
`config.php`, `prompt.txt` a složka `knowledge/` jsou přes `.htaccess` nedostupné z webu.
Vyžaduje PHP ≥ 8.1 s rozšířeními curl a mbstring.
