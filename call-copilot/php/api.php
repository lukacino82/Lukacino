<?php
// Call Copilot – PHP backend pro sdílený hosting (Active24 apod.). Ekvivalent server.js + kb.js.
declare(strict_types=1);
mb_internal_encoding('UTF-8');
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

$cfgFile = __DIR__ . '/config.php';
if (!is_file($cfgFile)) fail(500, 'Chybí config.php (zkopíruj config.sample.php).');
$cfg = require $cfgFile;

session_name('copilot');
session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'httponly' => true,
    'secure' => !empty($_SERVER['HTTPS']), 'samesite' => 'Strict']);
session_start();

const KB_DIR = __DIR__ . '/knowledge';
if (!is_dir(KB_DIR)) { mkdir(KB_DIR, 0755, true); file_put_contents(KB_DIR . '/.htaccess', "Require all denied\n"); }

function fail(int $code, string $msg): never {
    http_response_code($code);
    echo json_encode(['error' => $msg], JSON_UNESCAPED_UNICODE);
    exit;
}
function out($data): never { echo json_encode($data, JSON_UNESCAPED_UNICODE); exit; }
function body(): array {
    // vyžadujeme JSON content-type => cizí web nemůže volat API bez CORS preflightu (ochrana před CSRF)
    if (stripos($_SERVER['CONTENT_TYPE'] ?? '', 'application/json') !== 0) fail(415, 'Očekávám application/json');
    $raw = file_get_contents('php://input');
    if (strlen($raw) > 5_000_000) fail(413, 'Příliš velké');
    $j = json_decode($raw, true);
    if (!is_array($j)) fail(400, 'Neplatný JSON');
    return $j;
}
function requireAuth(): void { if (empty($_SESSION['ok'])) fail(401, 'Nepřihlášen'); }

// ---------- Znalostní báze (BM25) ----------
function tokenize(string $t): array {
    $t = strtr(mb_strtolower($t), [
        'á'=>'a','č'=>'c','ď'=>'d','é'=>'e','ě'=>'e','í'=>'i','ň'=>'n','ó'=>'o','ř'=>'r','š'=>'s',
        'ť'=>'t','ú'=>'u','ů'=>'u','ý'=>'y','ž'=>'z','ä'=>'a','ö'=>'o','ü'=>'u','ß'=>'s',
    ]);
    $out = [];
    foreach (preg_split('/[^a-z0-9]+/', $t, -1, PREG_SPLIT_NO_EMPTY) as $w) {
        if (strlen($w) > 2) $out[] = substr($w, 0, 5);      // hrubý stemmer pro češtinu
    }
    return $out;
}
function chunkText(string $text): array {
    $out = []; $heading = ''; $buf = '';
    $flush = function () use (&$out, &$heading, &$buf) {
        if (mb_strlen(trim($buf)) > 20) $out[] = ($heading !== '' ? $heading . "\n" : '') . trim($buf);
        $buf = '';
    };
    foreach (preg_split('/\R\s*\R/', $text) as $para) {
        foreach (preg_split('/\R/', $para) as $line) {
            if (preg_match('/^#{1,4}\s+(.+)/u', $line, $m)) { $flush(); $heading = $m[1]; }
            else $buf .= $line . "\n";
        }
        $buf .= "\n";
        if (mb_strlen($buf) > 700) $flush();
    }
    $flush();
    return $out;
}
function listDocs(): array {
    return array_values(array_map('basename', array_filter(glob(KB_DIR . '/*') ?: [],
        fn($f) => preg_match('/\.(md|txt|csv|json)$/i', $f))));
}
function loadChunks(): array {
    $chunks = [];
    foreach (listDocs() as $doc) {
        foreach (chunkText((string)file_get_contents(KB_DIR . '/' . $doc)) as $text) {
            $toks = tokenize($doc . ' ' . $text);
            $chunks[] = ['doc' => $doc, 'text' => $text, 'tf' => array_count_values($toks), 'len' => count($toks)];
        }
    }
    return $chunks;
}
function retrieve(array $chunks, string $query, int $k = 5): array {
    if (!$chunks) return [];
    $N = count($chunks); $df = []; $sum = 0;
    foreach ($chunks as $c) { $sum += $c['len']; foreach ($c['tf'] as $w => $_) $df[$w] = ($df[$w] ?? 0) + 1; }
    $avg = max($sum / $N, 1);
    $q = array_unique(tokenize($query));
    $scored = [];
    foreach ($chunks as $c) {
        $s = 0.0;
        foreach ($q as $w) {
            $f = $c['tf'][$w] ?? 0;
            if (!$f) continue;
            $idf = log(1 + ($N - $df[$w] + 0.5) / ($df[$w] + 0.5));
            $s += $idf * ($f * 2.2) / ($f + 1.2 * (0.25 + 0.75 * $c['len'] / $avg));
        }
        if ($s > 0) $scored[] = [$s, $c];
    }
    usort($scored, fn($a, $b) => $b[0] <=> $a[0]);
    return array_map(fn($x) => $x[1], array_slice($scored, 0, $k));
}
function safeName(string $n): string {
    $n = preg_replace('/[^\p{L}\p{N}_.\- ]/u', '_', basename($n)) ?: 'dokument';
    $n = ltrim($n, '.');
    return preg_match('/\.(md|txt|csv|json)$/i', $n) ? $n : $n . '.txt';
}
function docsInfo(): array {
    $cnt = [];
    foreach (loadChunks() as $c) $cnt[$c['doc']] = ($cnt[$c['doc']] ?? 0) + 1;
    return array_map(fn($d) => ['name' => $d, 'chunks' => $cnt[$d] ?? 0], listDocs());
}

// ---------- Claude ----------
function suggest(array $cfg, array $b): array {
    $transcript = (string)($b['transcript'] ?? '');
    if (trim($transcript) === '') fail(400, 'Prázdný přepis');
    $transcript = mb_substr($transcript, -12000);
    $recent = array_slice(explode("\n", $transcript), -4);
    $hits = retrieve(loadChunks(), implode(' ', $recent) . ' ' . implode(' ', array_slice($recent, -2)));
    $kbText = $hits ? implode("\n\n", array_map(fn($h, $i) => '[' . ($i + 1) . "] ({$h['doc']})\n{$h['text']}", $hits, array_keys($hits)))
                    : '(žádný relevantní úryvek)';
    $user = "ZNALOSTNÍ BÁZE – nalezené úryvky:\n$kbText\n\n" .
            "CÍL HOVORU:\n" . mb_substr((string)($b['goal'] ?? '') ?: '(neurčen)', 0, 1000) .
            "\n\nKONTEXT / SKRIPT:\n" . mb_substr((string)($b['context'] ?? '') ?: '(žádný)', 0, 20000) .
            "\n\nPŘEPIS HOVORU (nejnovější dole):\n$transcript";

    $ch = curl_init('https://api.anthropic.com/v1/messages');
    curl_setopt_array($ch, [
        CURLOPT_POST => true, CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 25,
        CURLOPT_HTTPHEADER => ['content-type: application/json', 'x-api-key: ' . $cfg['anthropic_api_key'],
                               'anthropic-version: 2023-06-01'],
        CURLOPT_POSTFIELDS => json_encode([
            'model' => $cfg['model'] ?? 'claude-haiku-5-5', 'max_tokens' => 600,
            'system' => file_get_contents(__DIR__ . '/prompt.txt'),
            'messages' => [['role' => 'user', 'content' => $user]],
        ], JSON_UNESCAPED_UNICODE),
    ]);
    $res = curl_exec($ch); $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    if ($res === false) fail(502, 'Spojení s Claude API selhalo: ' . curl_error($ch));
    if ($code >= 400) fail(502, "Claude API $code: " . mb_substr((string)$res, 0, 300));
    $j = json_decode((string)$res, true);
    $text = implode('', array_map(fn($x) => $x['text'] ?? '', $j['content'] ?? []));
    $s = strpos($text, '{'); $e = strrpos($text, '}');
    $parsed = ($s === false || $e === false) ? null : json_decode(substr($text, $s, $e - $s + 1), true);
    if (!is_array($parsed)) fail(502, 'Model nevrátil JSON');
    return $parsed;
}

// ---------- Routování ----------
$a = $_GET['a'] ?? '';
$method = $_SERVER['REQUEST_METHOD'];

if ($a === 'me') out(['auth' => !empty($_SESSION['ok'])]);

if ($a === 'login' && $method === 'POST') {
    $b = body();
    if (!empty($cfg['password_hash']) && password_verify((string)($b['password'] ?? ''), $cfg['password_hash'])) {
        session_regenerate_id(true);
        $_SESSION['ok'] = true;
        out(['ok' => true]);
    }
    sleep(1);   // zpomalení hádání hesla
    fail(401, 'Špatné heslo');
}
if ($a === 'logout') { $_SESSION = []; session_destroy(); out(['ok' => true]); }

requireAuth();

if ($a === 'suggest' && $method === 'POST') out(suggest($cfg, body()));

if ($a === 'kb') {
    if ($method === 'GET') out(['docs' => docsInfo()]);
    if ($method === 'POST') {
        $b = body();
        $text = trim((string)($b['text'] ?? ''));
        if ($text === '') fail(400, 'Prázdný dokument');
        file_put_contents(KB_DIR . '/' . safeName((string)($b['name'] ?? 'dokument')), $text);
        out(['docs' => docsInfo()]);
    }
    if ($method === 'DELETE') {
        $f = KB_DIR . '/' . safeName((string)($_GET['name'] ?? ''));
        if (is_file($f)) unlink($f);
        out(['docs' => docsInfo()]);
    }
}
fail(404, 'Neznámá akce');
