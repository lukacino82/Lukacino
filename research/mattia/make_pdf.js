// Render out/report.html to out/ES_Alpha_Map.pdf: node make_pdf.js out/report.html out/ES_Alpha_Map.pdf
// Needs fonts_inline.css (IBM Plex latin subsets as base64 @font-face) next to the script path below.
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  let h = fs.readFileSync(process.argv[2], 'utf8');
  h = h.replace(/<link[^>]*fonts\.g[^>]*>/g, '');
  const fonts = fs.readFileSync('/tmp/claude-0/fonts_inline.css', 'utf8');
  const print = `
  @page { size: A4 landscape; margin: 12mm 12mm 14mm; }
  body { background:#fff !important; padding:0 !important; font-size:12.5px; }
  .wrap { max-width:none; padding-block:0; }
  section { padding-block:22px 4px; break-inside:auto; }
  h2 { break-after:avoid; } .eyebrow { break-after:avoid; }
  .panel, .card, .callout, .kpis, .chart, tr { break-inside:avoid; }
  .tablewrap { overflow:visible !important; border:1px solid var(--rule); }
  table { font-size:10.5px; } th, td { padding:5px 6px; white-space:normal !important; }
  td.name small { min-width:0 !important; max-width:none !important; }
  .filters { display:none; } .tip { display:none !important; }
  .lede { font-size:15px; }
  #tMap td, #tMap th { text-align:left !important; }
  section:has(.steps), section:has(#recCards) { break-inside:avoid; }`;
  const doc = `<!doctype html><html data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=1100">
  <style>${fonts}</style></head><body>${h}<style>${print}</style></body></html>`;
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const p = await b.newPage({ viewport: { width: 1100, height: 900 } });
  p.on('pageerror', e => console.log('ERR', e.message));
  await p.setContent(doc, { waitUntil: 'load' });
  await p.emulateMedia({ media: 'print', colorScheme: 'light' });
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(500);
  await p.pdf({ path: process.argv[3], format: 'A4', landscape: true, printBackground: true,
    displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#7a8286;font-family:sans-serif">ES Alpha Map · strana <span class="pageNumber"></span> / <span class="totalPages"></span></div>',
    margin: { top: '12mm', bottom: '14mm', left: '12mm', right: '12mm' } });
  await b.close();
})();
