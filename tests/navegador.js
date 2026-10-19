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

  console.log('\n=== 4. Metas: crear rango y eliminar (los 4 dashboards) ===');
  // Año irrepetible por ejecución: la BD de pruebas persiste y, si se
  // reutilizara el mismo rango, el alta sería un upsert y no sumaría filas.
  const anio = 2050 + Math.floor(Math.random() * 40);
  for (const [nombre, url] of [['necesidades', '/dashboard/necesidades'], ['diversion', '/dashboard/diversion'],
                               ['inversion', '/dashboard/inversion'], ['rd', '/dashboard/rd']]) {
    actual = `metas-${nombre}`;
    await page.goto(BASE + url, { waitUntil: 'networkidle' });
    await page.waitForTimeout(900);
    const mAntes = await page.locator('#metas-body tr').count();

    await page.click('button:has-text("Nueva meta")');
    await page.waitForTimeout(300);
    await page.fill('#meta-desde', `${anio}-01`);
    await page.fill('#meta-hasta', `${anio}-03`);
    await page.fill('#meta-monto', '333');
    await page.click('button:has-text("Guardar meta")');
    await page.waitForTimeout(1200);
    const mDespues = await page.locator('#metas-body tr').count();
    check(`${nombre}: crear rango de 3 meses`, mDespues === mAntes + 3, `${mAntes} -> ${mDespues}`);

    // Borrar las 3 recién creadas deja la tabla como estaba (prueba repetible).
    for (let k = 0; k < 3; k++) {
      await page.locator('#metas-body button[title="Eliminar"]').first().click();
      await page.waitForTimeout(700);
    }
    check(`${nombre}: eliminar deja la tabla como estaba`,
          (await page.locator('#metas-body tr').count()) === mAntes,
          `quedaron ${await page.locator('#metas-body tr').count()}, esperaba ${mAntes}`);
  }

  console.log('\n=== 4b. Tarjeta: marcar "ya tengo el dinero" ===');
  actual = 'tarjeta-consumos';
  await page.goto(`${BASE}/dashboard/tarjeta`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1600);
  const rojosIni = await page.locator('.consumo-pend').count();
  check('hay consumos sin dinero apartado (en rojo)', rojosIni > 0, 'no hay con qué probar');

  // El check no debe cambiar nada hasta confirmar.
  await page.locator('.consumo-pend .consumo-check').first().click();
  await page.waitForTimeout(450);
  check('el check pide confirmación', (await page.locator('#modal-consumo.open').count()) > 0);
  const detalle = await page.locator('.mc-detalle').innerText();
  check('la confirmación muestra la compra', /Fecha[\s\S]*Compra[\s\S]*Monto/.test(detalle), detalle.slice(0, 60));
  await page.click('#mc-cancelar');
  await page.waitForTimeout(400);
  check('cancelar no cambia nada', (await page.locator('.consumo-pend').count()) === rojosIni);

  await page.locator('.consumo-pend .consumo-check').first().click();
  await page.waitForTimeout(400);
  await page.click('#mc-confirmar');
  await page.waitForTimeout(1600);
  check('confirmar pasa el consumo de rojo a verde',
        (await page.locator('.consumo-pend').count()) === rojosIni - 1,
        `quedaron ${await page.locator('.consumo-pend').count()}, esperaba ${rojosIni - 1}`);

  const per1 = await page.locator('#ciclo-txt').innerText();
  await page.click('#ciclo-prev');
  await page.waitForTimeout(1500);
  check('el filtro cambia de período', (await page.locator('#ciclo-txt').innerText()) !== per1, per1);

  check('el panel muestra la deuda en soles y dólares',
        /S\//.test(await page.locator('#pagar-monto').innerText()) &&
        /\$/.test(await page.locator('#pagar-usd').innerText()), 'falta una de las dos monedas');
  check('el panel muestra lo que se va acumulando',
        /S\//.test(await page.locator('#acum-monto').innerText()));

  actual = 'nuevo-consumos';
  await page.goto(`${BASE}/nuevo`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  check('la lista de consumos está oculta al inicio',
        !(await page.locator('#bloque-consumos').isVisible()));
  await page.click('label[for="tarjeta"]');
  await page.waitForTimeout(1600);
  check('al elegir Tarjeta aparece la lista del período',
        (await page.locator('#bc-body tr').count()) > 0);

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

  console.log('\n=== 6. Texto: sin entidades HTML a la vista ===');
  // Un "&amp;" escrito a mano dentro de una expresión Jinja se escapa dos
  // veces y el usuario termina leyendo "R &amp; D" en pantalla.
  for (const [n, u] of [['transferencia', '/transferencia'], ['movimientos', '/movimientos'],
                        ['nuevo', '/nuevo'], ['resumen', '/dashboard']]) {
    actual = n;
    await page.goto(BASE + u, { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    const crudas = await page.evaluate(() =>
      (document.body.innerText.match(/&(amp|lt|gt|quot|#\d+);/g) || []).slice(0, 3));
    check(`${n}: sin entidades HTML visibles`, crudas.length === 0, crudas.join(', '));
  }

  console.log('\n=== 7. Accesibilidad ===');
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

  console.log('\n=== 8. Móvil (390x844) ===');
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

  console.log('\n=== 9. Modo claro ===');
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
