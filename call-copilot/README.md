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
