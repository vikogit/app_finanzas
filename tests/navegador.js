// Pruebas en navegador real (Playwright) sobre la app viva.
//   1) python tests/servidor_pruebas.py
//   2) node tests/navegador.js
// Cubre: errores JS, flujos de usuario, XSS, accesibilidad, móvil y modo claro.
const { chromium } = require('playwright');

const BASE = 'http://127.0.0.1:5055';
const fallos = [], avisos = [];
const ok = l => console.log(`  OK   ${l}`);
const bad = (l, d = '') => { console.log(`  FAIL ${l} :: ${d}`); fallos.push([l, d]); };
const aviso = (l, d = '') => { console.log(`  WARN ${l} :: ${d}`); avisos.push([l, d]); };
const check = (l, c, d = '') => c ? ok(l) : bad(l, d);

const PAGINAS = [
  ['resumen', '/dashboard'], ['colchon', '/dashboard/colchon'], ['necesidades', '/dashboard/necesidades'],
  ['diversion', '/dashboard/diversion'], ['inversion', '/dashboard/inversion'], ['vortex', '/dashboard/vortex'],
  ['earnings', '/dashboard/earnings'], ['tarjeta', '/dashboard/tarjeta'], ['rd', '/dashboard/rd'],
  ['presupuesto', '/dashboard/presupuesto'], ['movimientos', '/movimientos'],
  ['nuevo', '/nuevo'], ['transferencia', '/transferencia'],
];

async function entrar(page) {
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await page.fill('input[name="usuario"]', 'tester');
  await page.fill('input[name="password"]', 'tester');
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type="submit"]')]);
}

(async () => {
  const browser = await chromium.launch({ channel: 'chromium' });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const problemas = [];
  let actual = '';
  page.on('pageerror', e => problemas.push([actual, 'EXCEPCIÓN JS', String(e).slice(0, 150)]));
  page.on('console', m => { if (m.type() === 'error') problemas.push([actual, 'console.error', m.text().slice(0, 150)]); });
  page.on('response', r => { if (r.status() >= 400) problemas.push([actual, `HTTP ${r.status()}`, r.url().replace(BASE, '').slice(0, 70)]); });
  page.on('dialog', d => d.accept());

  actual = 'login';
  await entrar(page);

  console.log('=== 1. Carga de cada pantalla ===');
  for (const [nombre, url] of PAGINAS) {
    actual = nombre;
    await page.goto(BASE + url, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1100);
    const v = await page.evaluate(() => ({
      canvasVacios: [...document.querySelectorAll('canvas')]
        .filter(c => c.getBoundingClientRect().width < 20).length,
      kpisPendientes: [...document.querySelectorAll('.kpi-value, .resultado-val')]
        .map(e => e.textContent.trim()).filter(t => /^(S\/\s*)?—/.test(t) || t === '— %').length,
    }));
    check(`${nombre}: sin canvas vacíos ni KPIs sin resolver`,
          v.canvasVacios === 0 && v.kpisPendientes === 0,
          `canvas vacíos=${v.canvasVacios}, KPIs sin dato=${v.kpisPendientes}`);
  }

  console.log('\n=== 2. Flujo: crear → editar → eliminar ===');
  actual = 'flujo';
  await page.goto(`${BASE}/nuevo`, { waitUntil: 'networkidle' });
  await page.fill('#fecha', '2026-09-15');
  await page.click('label[for="gasto"]');
  await page.click('label[for="necesidades"]');
  await page.fill('#descripcion', 'Prueba automatica');
  await page.fill('#importe', '123.45');
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type="submit"]')]);
  check('crear movimiento', (await page.content()).includes('Prueba automatica'));

  await page.goto(`${BASE}/movimientos?descripcion=Prueba automatica`, { waitUntil: 'networkidle' });
  await page.click('a:has-text("Editar")');
  await page.waitForLoadState('networkidle');
  await page.fill('#descripcion', 'Prueba editada');
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type="submit"]')]);
  check('editar movimiento', (await page.content()).includes('Prueba editada'));

  await page.goto(`${BASE}/movimientos?descripcion=Prueba editada`, { waitUntil: 'networkidle' });
  const antes = await page.locator('tbody tr').count();
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button:has-text("Eliminar")')]);
  await page.goto(`${BASE}/movimientos?descripcion=Prueba editada`, { waitUntil: 'networkidle' });
  check('eliminar movimiento (POST)', (await page.locator('tbody tr').count()) < antes);

  console.log('\n=== 3. Inversión: asistente de activo + conversión USD ===');
  actual = 'inversion-form';
  await page.goto(`${BASE}/nuevo`, { waitUntil: 'networkidle' });
  await page.click('label[for="inversion"]');
  await page.waitForTimeout(250);
  check('"Ingreso" oculto en Inversión', !(await page.locator('#ingreso-wrap').isVisible()),
        'permitiría romper el Neto invertido');
  await page.click('button:has-text("Cripto")');
  await page.waitForTimeout(250);
  await page.click('button:has-text("Bitcoin")');
  await page.fill('#monto-usd', '25');
  await page.waitForTimeout(400);
  check('convierte USD a soles', parseFloat(await page.inputValue('#importe')) > 25);

  console.log('\n=== 4. Metas: crear rango y eliminar ===');
  actual = 'metas';
  await page.goto(`${BASE}/dashboard/diversion`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  const mAntes = await page.locator('#metas-body tr').count();
  await page.click('button:has-text("Nueva meta")');
  await page.waitForTimeout(300);
  await page.fill('#meta-desde', '2027-01');
  await page.fill('#meta-hasta', '2027-03');
  await page.fill('#meta-monto', '333');
  await page.click('button:has-text("Guardar meta")');
  await page.waitForTimeout(1200);
  const mDespues = await page.locator('#metas-body tr').count();
  check('crear meta por rango (3 meses)', mDespues === mAntes + 3, `${mAntes} -> ${mDespues}`);
  await page.locator('#metas-body button[title="Eliminar"]').first().click();
  await page.waitForTimeout(1100);
  check('eliminar meta', (await page.locator('#metas-body tr').count()) === mDespues - 1);

  console.log('\n=== 5. Seguridad: XSS en descripciones ===');
  actual = 'xss';
  await page.goto(`${BASE}/nuevo`, { waitUntil: 'networkidle' });
  await page.fill('#fecha', '2026-09-18');
  await page.click('label[for="gasto"]');
  await page.click('label[for="colchon"]');
  await page.fill('#descripcion', `<img src=x onerror="window.__xss=1">`);
  await page.fill('#importe', '9');
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type="submit"]')]);
  for (const [n, u] of [['movimientos', '/movimientos'], ['Colchón', '/dashboard/colchon'],
                        ['Tarjeta', '/dashboard/tarjeta'], ['VORTEX', '/dashboard/vortex']]) {
    await page.goto(BASE + u, { waitUntil: 'networkidle' });
    await page.evaluate(() => { window.__xss = 0; });
    await page.waitForTimeout(1200);
    check(`${n} no ejecuta HTML de la descripción`, !(await page.evaluate(() => window.__xss === 1)), 'XSS');
  }

  console.log('\n=== 6. Accesibilidad ===');
  for (const [n, u] of [['necesidades', '/dashboard/necesidades'], ['nuevo', '/nuevo'],
                        ['movimientos', '/movimientos'], ['presupuesto', '/dashboard/presupuesto']]) {
    actual = n;
    await page.goto(BASE + u, { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);
    const a = await page.evaluate(() => ({
      sinLabel: [...document.querySelectorAll('input:not([type=hidden])')]
        .filter(i => !i.labels?.length && !i.getAttribute('aria-label')).map(i => i.id || i.type),
      sinNombre: [...document.querySelectorAll('button, a')]
        .filter(e => !e.textContent.trim() && !e.getAttribute('aria-label') && !e.getAttribute('title')).length,
    }));
    check(`${n}: todo input tiene etiqueta`, a.sinLabel.length === 0, a.sinLabel.join(', '));
    check(`${n}: todo botón/enlace tiene nombre`, a.sinNombre === 0, `${a.sinNombre} sin nombre`);
  }
  await ctx.close();

  console.log('\n=== 7. Móvil (390x844) ===');
  const mob = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const mp = await mob.newPage();
  mp.on('pageerror', e => problemas.push(['móvil', 'EXCEPCIÓN JS', String(e).slice(0, 150)]));
  await entrar(mp);
  for (const [n, u] of PAGINAS) {
    await mp.goto(BASE + u, { waitUntil: 'networkidle' });
    await mp.waitForTimeout(900);
    const d = await mp.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(`${n}: sin scroll horizontal`, d <= 2, `desborda ${d}px`);
  }
  await mob.close();

  console.log('\n=== 8. Modo claro ===');
  const luz = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const lp = await luz.newPage();
  lp.on('pageerror', e => problemas.push(['claro', 'EXCEPCIÓN JS', String(e).slice(0, 150)]));
  await entrar(lp);
  await lp.evaluate(() => localStorage.setItem('theme', 'light'));
  for (const [n, u] of [['resumen', '/dashboard'], ['earnings', '/dashboard/earnings'],
                        ['necesidades', '/dashboard/necesidades'], ['presupuesto', '/dashboard/presupuesto']]) {
    await lp.goto(BASE + u, { waitUntil: 'networkidle' });
    await lp.waitForTimeout(900);
    const r = await lp.evaluate(() => ({ claro: !document.documentElement.classList.contains('dark') }));
    check(`${n}: renderiza en modo claro`, r.claro);
  }
  await luz.close();

  console.log('\n=== Problemas de consola / red ===');
  const vistos = new Set();
  for (const [pg, tipo, msg] of problemas) {
    const k = `${pg}|${tipo}|${msg}`;
    if (vistos.has(k)) continue;
    vistos.add(k);
    bad(`[${pg}] ${tipo}`, msg);
  }
  if (!vistos.size) ok('ninguno');

  console.log('\n' + '='.repeat(62));
  console.log(`RESULTADO: ${fallos.length} fallos, ${avisos.length} avisos`);
  await browser.close();
  process.exit(fallos.length ? 1 : 0);
})();
