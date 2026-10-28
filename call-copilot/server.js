// Call Copilot – minimální server bez závislostí (Node 18+).
// Servíruje UI a proxuje dotazy na Claude API, aby klíč nebyl v prohlížeči.
const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || '127.0.0.1';
const API_KEY = process.env.ANTHROPIC_API_KEY;
const MODEL = process.env.MODEL || 'claude-haiku-5-5';
const kb = require('./kb');
const PUBLIC = path.join(__dirname, 'public');

const SYSTEM = fs.readFileSync(path.join(__dirname, 'prompt.txt'), 'utf8');
const NOTES_SYSTEM = fs.readFileSync(path.join(__dirname, 'notes-prompt.txt'), 'utf8');
const NOTES_MODEL = process.env.NOTES_MODEL || 'claude-sonnet-5-5';
const CALLS_DIR = path.join(__dirname, 'calls');
fs.mkdirSync(CALLS_DIR, { recursive: true });

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

async function claude(model, system, user, maxTokens, signal) {
  const r = await fetch((process.env.ANTHROPIC_BASE_URL || 'https://api.anthropic.com') + '/v1/messages', {
    method: 'POST', signal,
    headers: { 'content-type': 'application/json', 'x-api-key': API_KEY, 'anthropic-version': '2023-06-01' },
    body: JSON.stringify({ model, max_tokens: maxTokens, system, messages: [{ role: 'user', content: user }] }),
  });
  if (!r.ok) throw new Error(`Claude API ${r.status}: ${(await r.text()).slice(0, 300)}`);
  const j = await r.json();
  return extractJson(j.content.map((b) => b.text || '').join(''));
}

const leadText = (l = {}) =>
  [l.name && `Jméno: ${l.name}`, l.company && `Firma: ${l.company}`, l.notes && `Poznámky k leadu: ${l.notes}`]
    .filter(Boolean).join('\n') || '(žádné údaje)';

function suggest({ goal, context, transcript, lead }) {
  // dotaz do báze = poslední repliky; poslední věty klienta mají dvojnásobnou váhu
  const lines = transcript.split('\n');
  const recent = lines.slice(-4);
  const lastClient = lines.filter((l) => !l.startsWith('Operátor:')).slice(-2);
  const hits = kb.retrieve([...recent, ...lastClient].join(' '));
  const kbText = hits.length
    ? hits.map((h, i) => `[${i + 1}] (${h.doc})\n${h.text}`).join('\n\n')
    : '(žádný relevantní úryvek)';
  const user =
    `ZNALOSTNÍ BÁZE – nalezené úryvky:\n${kbText}\n\n` +
    `LEAD:\n${leadText(lead)}\n\n` +
    `CÍL HOVORU:\n${goal || '(neurčen)'}\n\nKONTEXT / SKRIPT:\n${context || '(žádný)'}\n\n` +
    `PŘEPIS HOVORU (nejnovější dole):\n${transcript}`;
  return claude(MODEL, SYSTEM, user, 600);
}

async function makeNotes({ goal, context, transcript, lead }) {
  const user = `LEAD:\n${leadText(lead)}\n\nCÍL HOVORU:\n${goal || '(neurčen)'}\n\nKONTEXT:\n${context || '(žádný)'}\n\nPŘEPIS HOVORU:\n${transcript}`;
  return claude(NOTES_MODEL, NOTES_SYSTEM, user, 2000);
}

const safeId = (id) => (/^[\w-]+$/.test(id || '') ? id : null);
const callFile = (id) => path.join(CALLS_DIR, id + '.json');

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css' };

const json = (res, code, obj) => {
  res.writeHead(code, { 'content-type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(obj));
};

http.createServer(async (req, res) => {
  try {
    // ochrana proti DNS-rebindingu: jen localhost
    if (!/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(req.headers.host || '')) { res.writeHead(403); return res.end(); }
    const u = new URL(req.url, 'http://x');
    // UI volá stejné adresy jako na PHP hostingu: api.php?a=<akce>
    const route = u.pathname === '/api.php' ? u.searchParams.get('a')
      : u.pathname.startsWith('/api/') ? u.pathname.slice(5) : null;

    if (route) {
      const q = u.searchParams;
      if (req.method === 'POST' && !(req.headers['content-type'] || '').startsWith('application/json')) {
        return json(res, 415, { error: 'Očekávám application/json' });
      }
      if (route === 'me') return json(res, 200, { auth: true });   // lokálně bez přihlášení

      if (route === 'kb') {
        if (req.method === 'GET' && q.has('name')) return json(res, 200, { name: q.get('name'), text: kb.read(q.get('name')) });
        if (req.method === 'GET') return json(res, 200, { docs: kb.docs() });
        if (req.method === 'DELETE') { kb.remove(q.get('name')); return json(res, 200, { docs: kb.docs() }); }
        if (req.method === 'POST') {
          const { name, text, append } = JSON.parse(await readBody(req, 5_000_000));
          if (!text || !String(text).trim()) throw new Error('Prázdný dokument');
          append ? kb.append(name, String(text)) : kb.save(name, String(text));
          return json(res, 200, { docs: kb.docs() });
        }
      }

      if (route === 'calls' && req.method === 'GET') {
        const id = safeId(q.get('id'));
        if (q.has('id')) {
          if (!id || !fs.existsSync(callFile(id))) return json(res, 404, { error: 'Hovor nenalezen' });
          return json(res, 200, JSON.parse(fs.readFileSync(callFile(id), 'utf8')));
        }
        const list = fs.readdirSync(CALLS_DIR).filter((f) => f.endsWith('.json')).sort().reverse().map((f) => {
          const c = JSON.parse(fs.readFileSync(path.join(CALLS_DIR, f), 'utf8'));
          return { id: c.id, date: c.date, lead: c.lead, outcome: c.notes?.outcome, score: c.notes?.lead_score, summary: c.notes?.summary };
        });
        return json(res, 200, { calls: list });
      }

      if ((route === 'suggest' || route === 'notes') && req.method === 'POST') {
        if (!API_KEY) return json(res, 500, { error: 'Chybí ANTHROPIC_API_KEY (viz README).' });
        const body = JSON.parse(await readBody(req, 1_000_000));
        if (!body.transcript || typeof body.transcript !== 'string') throw new Error('Prázdný přepis');
        if (route === 'suggest') return json(res, 200, await suggest(body));
        const notes = await makeNotes(body);
        const d = new Date();
        const id = d.toISOString().replace(/[-:T]/g, '').slice(0, 14) + '-' + Math.random().toString(36).slice(2, 6);
        const call = { id, date: d.toISOString(), lead: body.lead || {}, goal: body.goal || '', transcript: body.transcript, notes };
        fs.writeFileSync(callFile(id), JSON.stringify(call, null, 2));
        return json(res, 200, call);
      }
      return json(res, 404, { error: 'Neznámá akce' });
    }

    if (req.method === 'GET') {
      const rel = u.pathname === '/' ? 'index.html' : u.pathname.slice(1);
      const file = path.join(PUBLIC, path.normalize(rel));
      if (!file.startsWith(PUBLIC)) { res.writeHead(403); return res.end(); }
      return fs.readFile(file, (err, buf) => {
        if (err) { res.writeHead(404); return res.end('Not found'); }
        res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' });
        res.end(buf);
      });
    }
    res.writeHead(404); res.end();
  } catch (e) {
    json(res, 500, { error: e.message });
  }
}).listen(PORT, HOST, () => console.log(`Call Copilot běží na http://localhost:${PORT} (návrhy: ${MODEL}, zápisy: ${NOTES_MODEL})`));
