// Znalostní báze: dokumenty v ./knowledge, vyhledávání BM25 po kouscích textu.
const fs = require('fs');
const path = require('path');

const KB_DIR = path.join(__dirname, 'knowledge');
fs.mkdirSync(KB_DIR, { recursive: true });

let chunks = [];      // {doc, text, tf:Map, len}
let df = new Map();   // term -> počet chunků s termem
let avgLen = 1;

// Hrubý "stemmer" pro češtinu: bez diakritiky, prefix 5 znaků – zvládne skloňování.
function tokenize(t) {
  return t.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .split(/[^a-z0-9]+/).filter((w) => w.length > 2).map((w) => w.slice(0, 5));
}

function chunkText(text) {
  const out = [];
  let heading = '', buf = '';
  const flush = () => {
    if (buf.trim().length > 20) out.push((heading ? heading + '\n' : '') + buf.trim());
    buf = '';
  };
  for (const para of text.split(/\n\s*\n/)) {
    for (const line of para.split('\n')) {
      const h = line.match(/^#{1,4}\s+(.+)/);
      if (h) { flush(); heading = h[1]; }
      else buf += line + '\n';
    }
    buf += '\n';
    if (buf.length > 700) flush();
  }
  flush();
  return out;
}

const listDocs = () => fs.readdirSync(KB_DIR).filter((f) => /\.(md|txt|csv|json)$/i.test(f));

function rebuild() {
  chunks = []; df = new Map();
  for (const doc of listDocs()) {
    for (const text of chunkText(fs.readFileSync(path.join(KB_DIR, doc), 'utf8'))) {
      const toks = tokenize(doc + ' ' + text), tf = new Map();
      for (const w of toks) tf.set(w, (tf.get(w) || 0) + 1);
      for (const w of tf.keys()) df.set(w, (df.get(w) || 0) + 1);
      chunks.push({ doc, text, tf, len: toks.length });
    }
  }
  avgLen = chunks.reduce((a, c) => a + c.len, 0) / (chunks.length || 1);
}

// Soubory můžeš přidávat/upravovat i ručně ve složce – index se při změně sám obnoví.
let sig = '';
function refresh() {
  const now = listDocs().map((f) => f + fs.statSync(path.join(KB_DIR, f)).mtimeMs).join('|');
  if (now !== sig) { sig = now; rebuild(); }
}

function retrieve(query, k = 5) {
  refresh();
  if (!chunks.length) return [];
  const q = [...new Set(tokenize(query))], N = chunks.length;
  return chunks.map((c) => {
    let score = 0;
    for (const w of q) {
      const f = c.tf.get(w);
      if (!f) continue;
      const idf = Math.log(1 + (N - df.get(w) + 0.5) / (df.get(w) + 0.5));
      score += idf * (f * 2.2) / (f + 1.2 * (0.25 + 0.75 * c.len / avgLen));
    }
    return { c, score };
  }).filter((x) => x.score > 0).sort((a, b) => b.score - a.score).slice(0, k).map((x) => x.c);
}

function safeName(n) {
  n = path.basename(String(n || 'dokument')).replace(/[^\p{L}\p{N}_.\- ]/gu, '_');
  return /\.(md|txt|csv|json)$/i.test(n) ? n : n + '.txt';
}

function save(name, text) { fs.writeFileSync(path.join(KB_DIR, safeName(name)), text); rebuild(); sig = ''; }
function remove(name) { fs.rmSync(path.join(KB_DIR, safeName(name)), { force: true }); rebuild(); sig = ''; }
function docs() { refresh(); return docsNow(); }
function docsNow() { return listDocs().map((d) => ({ name: d, chunks: chunks.filter((c) => c.doc === d).length })); }

function read(name) { return fs.readFileSync(path.join(KB_DIR, safeName(name)), 'utf8'); }
function append(name, text) {
  const f = path.join(KB_DIR, safeName(name));
  fs.appendFileSync(f, (fs.existsSync(f) ? '\n\n' : '') + text.trim() + '\n');
  rebuild();
}

rebuild();
module.exports = { retrieve, save, remove, docs, read, append };
