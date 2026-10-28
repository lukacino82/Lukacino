// Call Copilot – minimální server bez závislostí (Node 18+).
// Servíruje UI a proxuje dotazy na Claude API, aby klíč nebyl v prohlížeči.
const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || '127.0.0.1';
const API_KEY = process.env.ANTHROPIC_API_KEY;
const MODEL = process.env.MODEL || 'claude-haiku-5-5';
const PUBLIC = path.join(__dirname, 'public');

const SYSTEM = `Jsi zkušený sales/call coach, který v reálném čase našeptává operátorovi telefonního hovoru.
Dostaneš cíl hovoru, kontext (produkt, skript, pravidla) a průběžný přepis hovoru.
Řádky "Operátor:" říká operátor, "Zákazník:" protistrana, "?:" je neoznačený mluvčí – odhadni z kontextu.
Tvým úkolem je říct operátorovi, co má říct TEĎ, aby hovor optimálně vedl k cíli.

Pravidla:
- Piš česky (pokud hovor neprobíhá jinak), stručně, přirozeně jako mluvená řeč.
- "say" = přesná věta/y, kterou může operátor hned přečíst (max 2 věty). Reaguj na poslední zákazníkovu repliku.
- Nejdřív reaguj na to, co zákazník řekl (empatie, odpověď na námitku), pak veď k dalšímu kroku.
- Neslibuj nic, co není v kontextu; nevymýšlej ceny ani fakta. Když informace chybí, navrhni doptání.
- Pokud zákazník neřekl nic nového a operátor mluví, vrať "say": "" a jen průběžně hodnoť.
- Upozorni na rizika (tlak, monolog, ignorovaný signál, compliance).

Odpověz POUZE validním JSON bez markdownu v tomto tvaru:
{
 "phase": "úvod|zjištění potřeb|prezentace|námitka|uzavření|rozloučení",
 "sentiment": "pozitivní|neutrální|negativní",
 "interest": číslo 0-100 (zájem zákazníka),
 "say": "hlavní doporučená věta",
 "alternatives": ["max 2 alternativní formulace/přístupy"],
 "objection": "rozpoznaná námitka nebo prázdný řetězec",
 "warning": "krátké varování nebo prázdný řetězec",
 "next_goal": "co má být cílem dalšího kroku hovoru"
}`;

function readBody(req, limit = 200_000) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', (c) => {
      data += c;
      if (data.length > limit) { reject(new Error('too large')); req.destroy(); }
    });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

function extractJson(text) {
  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');
  if (start < 0 || end < 0) throw new Error('Model nevrátil JSON');
  return JSON.parse(text.slice(start, end + 1));
}

async function suggest({ goal, context, transcript }) {
  const user =
    `CÍL HOVORU:\n${goal || '(neurčen)'}\n\nKONTEXT / SKRIPT:\n${context || '(žádný)'}\n\n` +
    `PŘEPIS HOVORU (nejnovější dole):\n${transcript}`;
  const r = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': API_KEY,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 600,
      system: SYSTEM,
      messages: [{ role: 'user', content: user }],
    }),
  });
  if (!r.ok) throw new Error(`Claude API ${r.status}: ${(await r.text()).slice(0, 300)}`);
  const j = await r.json();
  return extractJson(j.content.map((b) => b.text || '').join(''));
}

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css' };

http.createServer(async (req, res) => {
  try {
    if (req.method === 'POST' && req.url === '/api/suggest') {
      if (!API_KEY) {
        res.writeHead(500, { 'content-type': 'application/json' });
        return res.end(JSON.stringify({ error: 'Chybí ANTHROPIC_API_KEY na serveru.' }));
      }
      const body = JSON.parse(await readBody(req));
      if (!body.transcript || typeof body.transcript !== 'string') throw new Error('Prázdný přepis');
      const out = await suggest(body);
      res.writeHead(200, { 'content-type': 'application/json' });
      return res.end(JSON.stringify(out));
    }
    if (req.method === 'GET') {
      const rel = req.url.split('?')[0] === '/' ? 'index.html' : req.url.split('?')[0].slice(1);
      const file = path.join(PUBLIC, path.normalize(rel));
      if (!file.startsWith(PUBLIC)) { res.writeHead(403); return res.end(); }
      fs.readFile(file, (err, buf) => {
        if (err) { res.writeHead(404); return res.end('Not found'); }
        res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' });
        res.end(buf);
      });
      return;
    }
    res.writeHead(404); res.end();
  } catch (e) {
    res.writeHead(500, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: e.message }));
  }
}).listen(PORT, HOST, () => console.log(`Call Copilot běží na http://${HOST}:${PORT} (model ${MODEL})`));
