// Capturas puntuales para revisar visualmente un cambio.
const { chromium } = require('playwright');
const path = require('path');
const BASE = 'http://127.0.0.1:5055';
const DIR = path.join(__dirname, 'capturas');

(async () => {
  const b = await chromium.launch({ channel: 'chromium' });
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  await p.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await p.fill('input[name="usuario"]', 'tester');
  await p.fill('input[name="password"]', 'tester');
  await Promise.all([p.waitForNavigation({ waitUntil: 'networkidle' }), p.click('button[type="submit"]')]);

  for (const [n, u] of [['necesidades', '/dashboard/necesidades'], ['diversion', '/dashboard/diversion'],
                        ['inversion', '/dashboard/inversion'], ['rd', '/dashboard/rd']]) {
    await p.goto(BASE + u, { waitUntil: 'networkidle' });
    await p.waitForTimeout(1200);
    const color = await p.evaluate(() => {
      const b = document.querySelector('.btn-add-meta');
      return b ? getComputedStyle(b).backgroundImage.slice(0, 60) : 'sin botón';
    });
    console.log(`  ${n.padEnd(12)} botón "Nueva meta": ${color}`);
    await p.locator('.metas-hdr').locator('xpath=following-sibling::div[1]')
      .screenshot({ path: path.join(DIR, `metas_${n}.png`) }).catch(() => {});
  }

  // Modal abierto, para revisar que mantiene su estilo
  await p.goto(`${BASE}/dashboard/inversion`, { waitUntil: 'networkidle' });
  await p.waitForTimeout(900);
  await p.click('button:has-text("Nueva meta")');
  await p.waitForTimeout(400);
  await p.screenshot({ path: path.join(DIR, 'modal_meta.png') });
  console.log('  modal capturado');

  await b.close();
  process.exit(0);
})();
