# VORTEX Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated financial dashboard page for the "VORTEX" movement category (the user's education business), showing income/expense KPIs, a per-student ("alumno") income breakdown, and a monthly income-vs-expense trend, styled identically to the app's existing category dashboards.

**Architecture:** Follows the exact pattern already used by `colchon.html`/`diversion.html`/`inversion.html`: a Flask route renders a template shell, the template fetches its data from a dedicated `/api/<categoria>` JSON endpoint on page load and on filter changes, and renders Chart.js charts using the shared `renderEtoroChart`/`renderDonutChart` helpers already defined in `base.html`. No new libraries, no DB schema changes — everything is derived from the existing `Movimiento` columns (`categoria`, `tipo`, `descripcion`, `importe`, `fecha`).

**Tech Stack:** Flask, Flask-SQLAlchemy, Jinja2 templates, Chart.js 4 (already loaded via CDN in `base.html`), vanilla JS (no build step, no frontend framework).

## Global Constraints

- Category string is exactly `"VORTEX"` (matches `templates/nuevo_movimiento.html:77`, already deployed).
- Accent color: `#06b6d4` (light mode) / `#22d3ee` (dark mode) — cyan family, per approved design.
- No changes to the `Movimiento` model or database schema.
- No new Python or JS dependencies — reuse what's already in `requirements.txt` and already loaded in `base.html`.
- Repo has **no automated test suite** (no `pytest` in `requirements.txt`, no `tests/` directory, no other route/template in the codebase has tests). Do not introduce a test framework as part of this feature — verification steps below use throwaway scripts (never committed) and manual browser checks, consistent with how the rest of the app is verified.
- Follow existing code conventions exactly: 2-space indent in HTML/CSS/JS, function names in Spanish where the codebase already uses Spanish (`agrupar_mensual`, `query_movs`), JSON keys in Spanish (`kpis`, `por_mes`, `evolucion`), money formatting via `toLocaleString('es-PE', {minimumFractionDigits:2, maximumFractionDigits:2})`.
- Ingreso vs Gasto is always colored green (`#22c55e`/`rgba(34,197,94,...)`) vs red (`#f87171`/`rgba(248,113,113,...)`) app-wide (see `dashboard.html` bar chart, `movimientos.html` badges) — do not use the category's cyan accent for that distinction; cyan is reserved for category-level chrome (KPI values, area chart, donut border/badges).

---

### Task 1: Backend — `/api/vortex` endpoint and `/dashboard/vortex` route

**Files:**
- Modify: `app.py:82` (insert new helper after `top_items`)
- Modify: `app.py:132` (insert new route after `dashboard_inversion`)
- Modify: `app.py:304` (insert new API endpoint after `api_inversion`)

**Interfaces:**
- Produces: `ranking_por_descripcion(movs) -> list[dict]`, each dict shaped `{"alumno": str, "total": float, "num_pagos": int, "pct": float}`, sorted descending by `total`.
- Produces: `GET /api/vortex?desde=YYYY-MM-DD&hasta=YYYY-MM-DD` returning JSON:
  ```json
  {
    "kpis": {"total_ingresos": 0.0, "total_gastos": 0.0, "utilidad_neta": 0.0, "margen_pct": 0.0, "num_alumnos": 0},
    "evolucion": [{"mes": "Jul 2026", "acumulado": 0.0}],
    "por_mes": [{"mes": "Jul 2026", "ingresos": 0.0, "gastos": 0.0}],
    "ingresos_por_alumno": [{"label": "Ana", "value": 150.0}],
    "ranking_alumnos": [{"alumno": "Ana", "total": 150.0, "num_pagos": 3, "pct": 42.3}],
    "gastos_por_concepto": [{"label": "Materiales", "value": 80.0}]
  }
  ```
- Produces: `GET /dashboard/vortex` → renders `templates/vortex.html` with `active_tab="vortex"` (route only works once Task 4 creates the template — that's expected at this point in the plan).
- Consumes: existing `parse_dates(req)`, `query_movs(desde, hasta, categoria=None, tipo=None)`, `agrupar_mensual(movs)`, `top_items(movs, n=8)`, all already defined above in `app.py`.

- [ ] **Step 1: Add the `ranking_por_descripcion` helper**

  In `app.py`, right after the `top_items` function (ends at line 82, right before the `# ── page routes ──` comment), insert:

  ```python
  def ranking_por_descripcion(movs):
      bucket = defaultdict(lambda: {"total": 0.0, "num_pagos": 0})
      for m in movs:
          b = bucket[m.descripcion]
          b["total"] += float(m.importe)
          b["num_pagos"] += 1
      total_general = sum(b["total"] for b in bucket.values())
      ranking = [
          {
              "alumno": k,
              "total": round(b["total"], 2),
              "num_pagos": b["num_pagos"],
              "pct": round(b["total"] / total_general * 100, 1) if total_general else 0,
          }
          for k, b in bucket.items()
      ]
      return sorted(ranking, key=lambda x: -x["total"])
  ```

- [ ] **Step 2: Verify the helper with a throwaway script (no DB needed)**

  Run this from the project root (importing `app` does not require a live database connection — `SQLAlchemy(app)` only connects lazily):

  ```bash
  python - <<'EOF'
  from collections import namedtuple
  from app import ranking_por_descripcion

  Mov = namedtuple("Mov", ["descripcion", "importe"])
  movs = [Mov("Ana", 100), Mov("Ana", 50), Mov("Luis", 150)]
  result = ranking_por_descripcion(movs)
  assert result == [
      {"alumno": "Ana", "total": 150.0, "num_pagos": 2, "pct": 50.0},
      {"alumno": "Luis", "total": 150.0, "num_pagos": 1, "pct": 50.0},
  ] or result == [
      {"alumno": "Luis", "total": 150.0, "num_pagos": 1, "pct": 50.0},
      {"alumno": "Ana", "total": 150.0, "num_pagos": 2, "pct": 50.0},
  ], result
  print("OK:", result)
  EOF
  ```

  Expected output: `OK: [...]` with no `AssertionError` (tie-break order between the two 150.0 entries doesn't matter here — both sum to the same total).

- [ ] **Step 3: Add the `/api/vortex` endpoint**

  In `app.py`, right after `api_inversion` (ends at line 304), before the `/inversiones` route, insert:

  ```python
  @app.route("/api/vortex")
  @login_requerido
  def api_vortex():
      desde, hasta = parse_dates(request)
      movs = query_movs(desde, hasta, categoria="VORTEX")
      movs_ingreso = [m for m in movs if m.tipo == "Ingreso"]
      movs_gasto   = [m for m in movs if m.tipo == "Gasto"]

      ing  = sum(float(m.importe) for m in movs_ingreso)
      gast = sum(float(m.importe) for m in movs_gasto)
      utilidad = ing - gast
      margen = round(utilidad / ing * 100, 1) if ing else 0

      por_mes = agrupar_mensual(movs)
      acum, evol = 0.0, []
      for item in por_mes:
          acum += item["ingresos"] - item["gastos"]
          evol.append({"mes": item["mes"], "acumulado": round(acum, 2)})

      ranking = ranking_por_descripcion(movs_ingreso)

      return jsonify({
          "kpis": {
              "total_ingresos": round(ing, 2),
              "total_gastos":   round(gast, 2),
              "utilidad_neta":  round(utilidad, 2),
              "margen_pct":     margen,
              "num_alumnos":    len(ranking),
          },
          "evolucion": evol,
          "por_mes": por_mes,
          "ingresos_por_alumno": [{"label": r["alumno"], "value": r["total"]} for r in ranking[:8]],
          "ranking_alumnos": ranking,
          "gastos_por_concepto": top_items(movs_gasto),
      })
  ```

- [ ] **Step 4: Add the `/dashboard/vortex` page route**

  In `app.py`, right after `dashboard_inversion` (ends at line 132), before `def nuevo():`, insert:

  ```python
  @app.route("/dashboard/vortex")
  @login_requerido
  def dashboard_vortex():
      return render_template("vortex.html", active_tab="vortex")
  ```

- [ ] **Step 5: Syntax check**

  Run: `python -m py_compile app.py`
  Expected: no output, exit code 0.

- [ ] **Step 6: Commit**

  ```bash
  git add app.py
  git commit -m "feat: add /api/vortex endpoint and /dashboard/vortex route"
  ```

---

### Task 2: `base.html` — nav tab, category color, badge, and card accent CSS

**Files:**
- Modify: `templates/base.html:230` (add `.badge-cyan`)
- Modify: `templates/base.html:331,336` (add `.cat-vortex` accent + hover rules)
- Modify: `templates/base.html:478` (add nav tab)
- Modify: `templates/base.html:606-616` (add `CAT_COLORS`/`CAT_COLORS_DARK` entries)

**Interfaces:**
- Produces: CSS classes `.badge-cyan`, `.cat-vortex` (with `::after` and `:hover` rules) usable by Tasks 3 and 4.
- Produces: nav link to `/dashboard/vortex` active when `active_tab == 'vortex'` (matches what Task 1's route sets).
- Produces: `catColor('VORTEX')` returns `#06b6d4` (light) / `#22d3ee` (dark) — used by the Resumen page's treemap (`dashboard.html`'s `renderTreemap`, which groups **all** categories including VORTEX gasto movements) so VORTEX slices don't fall back to the grey `#888` default.
- Consumes: nothing new — matches existing patterns for the other 4 categories verbatim.

- [ ] **Step 1: Add the badge color**

  In `templates/base.html`, in the badge block (right after line 230 `.badge-yellow { background: rgba(234,179,8,0.15);  color: #facc15; }`), add:

  ```css
      .badge-cyan   { background: rgba(6,182,212,0.15);  color: #06b6d4; }
  ```

- [ ] **Step 2: Add the category card accent CSS**

  In `templates/base.html`, in the `.cat-*::after` block (right after line 331 `.cat-inversion::after  { background: linear-gradient(90deg,#ca8a04,#facc15); }`), add:

  ```css
      .cat-vortex::after     { background: linear-gradient(90deg,#06b6d4,#22d3ee); }
  ```

  And in the `.cat-*:hover` block (right after line 336 `.cat-inversion:hover  { border-color:rgba(234,179,8,0.4);  box-shadow:0 12px 32px rgba(234,179,8,0.12); }`), add:

  ```css
      .cat-vortex:hover      { border-color:rgba(6,182,212,0.4);  box-shadow:0 12px 32px rgba(6,182,212,0.12); }
  ```

- [ ] **Step 3: Add the nav tab**

  In `templates/base.html`, in the `<div class="tabs" ...>` block, right after the Inversión tab (line 478) and before the Portafolio tab, insert:

  ```html
        <a href="/dashboard/vortex"       class="tab {% if active_tab=='vortex'      %}active{% endif %}" role="tab">VORTEX</a>
  ```

- [ ] **Step 4: Add category color mapping for the treemap**

  In `templates/base.html`, update the `CAT_COLORS` object (line ~605-610):

  ```js
    const CAT_COLORS = {
      'Necesidades': '#f97316',
      'Colchón':     '#22c55e',
      'Inversión':   '#3b82f6',
      'Diversión':   '#a855f7',
      'VORTEX':      '#06b6d4',
    };
  ```

  And `CAT_COLORS_DARK` (line ~611-616):

  ```js
    const CAT_COLORS_DARK = {
      'Necesidades': '#fb923c',
      'Colchón':     '#4ade80',
      'Inversión':   '#60a5fa',
      'Diversión':   '#c084fc',
      'VORTEX':      '#22d3ee',
    };
  ```

- [ ] **Step 5: Verify the new selectors exist exactly once each**

  ```bash
  grep -c "badge-cyan" templates/base.html
  grep -c "cat-vortex" templates/base.html
  grep -c "'VORTEX'" templates/base.html
  ```

  Expected: `badge-cyan` → at least 1 (CSS definition), `cat-vortex` → at least 2 (`::after` + `:hover`), `'VORTEX'` → 2 (one per color map).

- [ ] **Step 6: Commit**

  ```bash
  git add templates/base.html
  git commit -m "feat: add VORTEX nav tab, cyan accent CSS, and treemap color mapping"
  ```

---

### Task 3: `dashboard.html` — VORTEX category card

**Files:**
- Modify: `templates/dashboard.html:59-60` (insert new `cat-card` before the closing `</div>` of `.cat-nav-grid`)

**Interfaces:**
- Consumes: `.cat-vortex` CSS class from Task 2, `/dashboard/vortex` route from Task 1.
- Produces: nothing consumed by later tasks — this is a leaf change.

- [ ] **Step 1: Add the card**

  In `templates/dashboard.html`, right after the closing `</a>` of the Inversión card (line 59) and before the closing `</div>` of `.cat-nav-grid` (line 61), insert:

  ```html
    <a href="/dashboard/vortex" class="cat-card cat-vortex">
      <div class="cat-icon" style="background:rgba(6,182,212,0.15)">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#06b6d4" stroke-width="2.2"><path stroke-linecap="round" stroke-linejoin="round" d="M4.26 10.147a60.436 60.436 0 00-.491 6.347A48.627 48.627 0 0112 20.904a48.627 48.627 0 018.232-4.41 60.46 60.46 0 00-.491-6.347M4.26 10.147L12 13.489l7.74-3.342M4.26 10.147a50.57 50.57 0 012.658-.813m13.082.813a50.697 50.697 0 00-2.658-.813m0 0V6.478c0-1.131-.797-2.107-1.898-2.34a48.548 48.548 0 00-9.207 0c-1.101.233-1.898 1.209-1.898 2.34v2.856m13.003 0a48.53 48.53 0 00-13.003 0"/></svg>
      </div>
      <div class="cat-name">VORTEX</div>
      <div class="cat-desc">Emprendimiento educativo · ingresos por alumno y rentabilidad</div>
      <div class="cat-cta" style="color:#06b6d4">
        Ver dashboard
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"/></svg>
      </div>
    </a>
  ```

  (Icon is the heroicons "academic-cap" outline path, matching the stroke style/weight used by the other 4 cards.)

- [ ] **Step 2: Verify**

  ```bash
  grep -n "dashboard/vortex" templates/dashboard.html
  ```

  Expected: one match, inside an `<a href="...">` tag.

- [ ] **Step 3: Commit**

  ```bash
  git add templates/dashboard.html
  git commit -m "feat: add VORTEX card to Resumen dashboard grid"
  ```

---

### Task 4: `templates/vortex.html` — the dashboard page

**Files:**
- Create: `templates/vortex.html`

**Interfaces:**
- Consumes: `GET /api/vortex` (Task 1) response shape exactly as documented in Task 1's Interfaces block; `renderEtoroChart(canvasId, labels, values, hexColor, r, g, b, yLabel)`, `renderDonutChart(canvasId, items, centerHtml)`, `getDefaultDates()`, `setQuickFilter(type)`, `applyFilter()`, `window._charts` array — all defined in `templates/base.html`.
- Produces: nothing consumed by later tasks — this is the final leaf.

- [ ] **Step 1: Create the template**

  Create `templates/vortex.html`:

  ```html
  {% extends "base.html" %}
  {% block title %}VORTEX — App Finanzas{% endblock %}

  {% block content %}
  <div class="page-hdr">
    <h1 class="page-title">VORTEX y TECSUP</h1>
    <p class="page-sub">Tu emprendimiento educativo — ingresos, gastos y rentabilidad, alumno por alumno.</p>
  </div>

  <div class="filter-bar">
    <span class="filter-label">Período</span>
    <input type="date" id="desde" class="date-input">
    <span class="filter-sep">→</span>
    <input type="date" id="hasta" class="date-input">
    <button class="filter-btn" onclick="applyFilter()">Aplicar</button>
    <div class="quick-filters">
      <button class="qf" data-qf="mes"  onclick="setQuickFilter('mes')">Mes</button>
      <button class="qf" data-qf="3m"   onclick="setQuickFilter('3m')">3M</button>
      <button class="qf" data-qf="año"  onclick="setQuickFilter('año')">Año</button>
      <button class="qf" data-qf="todo" onclick="setQuickFilter('todo')">Todo</button>
    </div>
  </div>

  <div class="kpi-grid kpi-grid-4">
    <div class="card card-p">
      <div class="kpi-icon" style="background:rgba(6,182,212,0.15)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#22d3ee" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941"/></svg>
      </div>
      <div class="kpi-label">Ingresos</div>
      <div class="kpi-value" style="color:#06b6d4" id="kpi-ingresos">S/ —</div>
    </div>
    <div class="card card-p">
      <div class="kpi-icon" style="background:rgba(6,182,212,0.1)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#67e8f9" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 6L9 12.75l4.306-4.307a11.95 11.95 0 015.814 5.519l2.74 1.22m0 0l-5.94 2.28m5.94-2.28l-2.28-5.941"/></svg>
      </div>
      <div class="kpi-label">Gastos</div>
      <div class="kpi-value" style="color:#22d3ee" id="kpi-gastos">S/ —</div>
    </div>
    <div class="card card-p">
      <div class="kpi-icon" style="background:rgba(6,182,212,0.08)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a5f3fc" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v17.25m0 0c-1.472 0-2.882.265-4.185.75M12 20.25c1.472 0 2.882.265 4.185.75"/></svg>
      </div>
      <div class="kpi-label">Utilidad neta</div>
      <div class="kpi-value" style="color:#67e8f9" id="kpi-utilidad">S/ —</div>
    </div>
    <div class="card card-p">
      <div class="kpi-icon" style="background:rgba(6,182,212,0.06)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#cffafe" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M10.5 6a7.5 7.5 0 107.5 7.5h-7.5V6z"/><path stroke-linecap="round" stroke-linejoin="round" d="M13.5 10.5H21A7.5 7.5 0 0013.5 3v7.5z"/></svg>
      </div>
      <div class="kpi-label">Margen</div>
      <div class="kpi-value" style="color:#a5f3fc" id="kpi-margen">— %</div>
    </div>
  </div>

  <div class="charts-grid-main">
    <div class="card card-p">
      <div class="chart-title">
        Evolución de utilidad acumulada
        <span class="chart-badge badge-cyan">Área · eToro</span>
      </div>
      <div class="chart-area-wrap">
        <canvas id="chartArea"></canvas>
      </div>
    </div>
    <div class="card card-p">
      <div class="chart-title">
        Ingresos por alumno
        <span class="chart-badge badge-cyan">Pastel</span>
      </div>
      <div class="chart-donut-wrap" style="position:relative">
        <canvas id="chartDonutAlumno"></canvas>
      </div>
    </div>
  </div>

  <div class="charts-grid" style="margin-bottom:28px">
    <div class="card card-p">
      <div class="chart-title">Ingresos vs Gastos por mes</div>
      <div class="chart-legend">
        <div class="legend-item"><div class="legend-dot" style="background:#22c55e"></div>Ingresos</div>
        <div class="legend-item"><div class="legend-dot" style="background:#f87171"></div>Gastos</div>
      </div>
      <div style="position:relative;height:220px">
        <canvas id="chartBar"></canvas>
      </div>
    </div>
    <div class="card card-p">
      <div class="chart-title">
        Gastos por concepto
        <span class="chart-badge badge-cyan">Pastel</span>
      </div>
      <div class="chart-donut-wrap" style="position:relative">
        <canvas id="chartDonutGasto"></canvas>
      </div>
    </div>
  </div>

  <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:12px">
    <h2 style="font-size:15px;font-weight:700;color:var(--text)">Ranking de alumnos por ingresos</h2>
    <span style="font-size:12px;color:var(--text-muted)" id="lb-subtitle">— alumnos activos</span>
  </div>

  <div class="tbl-card">
    <div class="tbl-wrap">
      <table class="tbl">
        <thead>
          <tr>
            <th>#</th>
            <th>Alumno</th>
            <th style="text-align:right">Total pagado</th>
            <th style="text-align:right">N° pagos</th>
            <th style="text-align:right">% del total</th>
          </tr>
        </thead>
        <tbody id="lb-body"></tbody>
      </table>

      <div class="empty-state" id="lb-empty" style="display:none">
        <svg class="empty-icon" fill="none" viewBox="0 0 24 24" stroke-width="1.4" stroke="currentColor" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z"/>
        </svg>
        <p style="font-size:13px;margin-bottom:8px">Aún no hay ingresos de alumnos registrados en este período.</p>
        <a href="/nuevo" style="font-size:12px;font-weight:600;color:#06b6d4;text-decoration:none">Registrar el primero →</a>
      </div>
    </div>
  </div>
  {% endblock %}

  {% block scripts %}
  <script>
  let chartArea = null, chartDonutAlumno = null, chartBar = null, chartDonutGasto = null;

  function fmtMoney(v) {
    return 'S/ ' + v.toLocaleString('es-PE', {minimumFractionDigits:2, maximumFractionDigits:2});
  }

  function renderBarVortex(porMes) {
    const ctx = document.getElementById('chartBar').getContext('2d');
    const dark = document.documentElement.classList.contains('dark');
    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels: porMes.map(d => d.mes),
        datasets: [
          { label: 'Ingresos', data: porMes.map(d => d.ingresos), backgroundColor: 'rgba(34,197,94,0.7)', borderRadius: 4 },
          { label: 'Gastos',   data: porMes.map(d => d.gastos),   backgroundColor: 'rgba(248,113,113,0.7)', borderRadius: 4 },
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          x: {
            grid: { color: dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)' },
            ticks: { color: dark ? 'rgba(255,255,255,0.4)' : '#64748b' },
          },
          y: {
            grid: { color: dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)' },
            ticks: {
              color: dark ? 'rgba(255,255,255,0.4)' : '#64748b',
              callback: v => 'S/ ' + v.toLocaleString('es-PE'),
            }
          }
        },
        plugins: { legend: { display: false } }
      }
    });
  }

  function renderLeaderboard(ranking, numAlumnos) {
    document.getElementById('lb-subtitle').textContent =
      numAlumnos + (numAlumnos === 1 ? ' alumno activo' : ' alumnos activos');

    const tbody = document.getElementById('lb-body');
    const emptyState = document.getElementById('lb-empty');
    tbody.innerHTML = '';

    if (!ranking.length) {
      emptyState.style.display = 'block';
      return;
    }
    emptyState.style.display = 'none';

    ranking.forEach((r, i) => {
      const tr = document.createElement('tr');

      const tdPos = document.createElement('td');
      tdPos.className = 'muted';
      tdPos.textContent = i + 1;

      const tdAlumno = document.createElement('td');
      tdAlumno.style.fontWeight = '600';
      tdAlumno.textContent = r.alumno;

      const tdTotal = document.createElement('td');
      tdTotal.className = 'right';
      tdTotal.style.fontWeight = '700';
      tdTotal.style.color = '#06b6d4';
      tdTotal.textContent = fmtMoney(r.total);

      const tdPagos = document.createElement('td');
      tdPagos.className = 'right muted';
      tdPagos.textContent = r.num_pagos;

      const tdPct = document.createElement('td');
      tdPct.className = 'right muted';
      tdPct.textContent = r.pct + '%';

      tr.append(tdPos, tdAlumno, tdTotal, tdPagos, tdPct);
      tbody.appendChild(tr);
    });
  }

  function loadData(desde, hasta) {
    fetch(`/api/vortex?desde=${desde}&hasta=${hasta}`)
      .then(r => r.json())
      .then(data => {
        document.getElementById('kpi-ingresos').textContent = fmtMoney(data.kpis.total_ingresos);
        document.getElementById('kpi-gastos').textContent   = fmtMoney(data.kpis.total_gastos);

        const kpiUtilidad = document.getElementById('kpi-utilidad');
        kpiUtilidad.textContent = fmtMoney(data.kpis.utilidad_neta);
        kpiUtilidad.style.color = data.kpis.utilidad_neta >= 0 ? '#06b6d4' : '#f87171';

        document.getElementById('kpi-margen').textContent = data.kpis.margen_pct + ' %';

        [chartArea, chartDonutAlumno, chartBar, chartDonutGasto].forEach(c => {
          if (c) { c.destroy(); window._charts = window._charts.filter(x => x !== c); }
        });

        const centerAlumno = `<div class="donut-center-val" style="color:#06b6d4">${fmtMoney(data.kpis.total_ingresos)}</div>
                               <div class="donut-center-lbl">Ingresos</div>`;
        const centerGasto = `<div class="donut-center-val" style="color:#06b6d4">${fmtMoney(data.kpis.total_gastos)}</div>
                              <div class="donut-center-lbl">Gastos</div>`;

        chartArea = renderEtoroChart(
          'chartArea', data.evolucion.map(d => d.mes), data.evolucion.map(d => d.acumulado),
          '#06b6d4', 6, 182, 212
        );
        chartDonutAlumno = renderDonutChart(
          'chartDonutAlumno',
          data.ingresos_por_alumno.length ? data.ingresos_por_alumno : [{label:'Sin datos',value:1}],
          centerAlumno
        );
        chartBar = renderBarVortex(data.por_mes);
        chartDonutGasto = renderDonutChart(
          'chartDonutGasto',
          data.gastos_por_concepto.length ? data.gastos_por_concepto : [{label:'Sin datos',value:1}],
          centerGasto
        );

        window._charts.push(chartArea, chartDonutAlumno, chartBar, chartDonutGasto);

        renderLeaderboard(data.ranking_alumnos, data.kpis.num_alumnos);
      });
  }

  window.addEventListener('DOMContentLoaded', () => {
    const d = getDefaultDates();
    document.getElementById('desde').value = d.desde;
    document.getElementById('hasta').value = d.hasta;
    document.querySelector('[data-qf="mes"]').classList.add('active');
    loadData(d.desde, d.hasta);
  });
  </script>
  {% endblock %}
  ```

- [ ] **Step 2: Verify the template renders without a Jinja error (no DB needed)**

  Run from the project root:

  ```bash
  python - <<'EOF'
  from app import app

  with app.test_request_context():
      html = app.jinja_env.get_template("vortex.html").render(active_tab="vortex")
      assert 'id="chartArea"' in html
      assert 'id="chartDonutAlumno"' in html
      assert 'id="chartBar"' in html
      assert 'id="chartDonutGasto"' in html
      assert 'id="lb-body"' in html
      assert 'VORTEX y TECSUP' in html
  print("OK: template renders")
  EOF
  ```

  Expected: `OK: template renders`, no traceback. (This only exercises Jinja rendering — it does not touch the database, since `vortex.html` receives no DB-derived context variables; all data loads client-side via `fetch`.)

- [ ] **Step 3: Commit**

  ```bash
  git add templates/vortex.html
  git commit -m "feat: add VORTEX dashboard page"
  ```

---

### Task 5: End-to-end manual verification

**Files:** none (verification only; fix-and-recommit if issues are found)

- [ ] **Step 1: Start the app**

  If a `DATABASE_URL` (and `APP_USER`/`APP_PASSWORD`/`SECRET_KEY`) is available locally (e.g. in a local `.env`), run:

  ```bash
  python app.py
  ```

  If no local database is configured, skip to verifying against the deployed environment after pushing, using the same checklist below.

- [ ] **Step 2: Register test data**

  Log in and go to `/nuevo`. Register at least:
  - 3 "Ingreso" movements with `categoria=VORTEX`, using different descriptions (e.g. "Ana", "Luis", "Ana" again with a different amount) to exercise the per-alumno grouping and repeat-payment counting.
  - 2 "Gasto" movements with `categoria=VORTEX`, using different descriptions (e.g. "Instructor", "Materiales") to exercise the gasto-por-concepto breakdown.

- [ ] **Step 3: Check the VORTEX dashboard**

  Visit `/dashboard/vortex` and confirm:
  - The 4 KPI cards show non-placeholder values (Ingresos, Gastos, Utilidad neta, Margen).
  - The area chart shows the accumulated utility trend.
  - The "Ingresos por alumno" donut shows one slice per distinct description used above.
  - The bar chart shows green/red bars for the month the test data falls in.
  - The "Gastos por concepto" donut shows one slice per gasto description.
  - The leaderboard table lists both alumnos, with correct totals, payment counts, and percentages that sum to ~100%.

- [ ] **Step 4: Check Resumen and navigation**

  Visit `/dashboard` and confirm:
  - A new "VORTEX" card appears in the grid and links to `/dashboard/vortex`.
  - The treemap ("Gastos por categoría") shows the VORTEX slice in cyan, not grey.
  - The "VORTEX" tab appears in the top navbar on every page and is highlighted active only on `/dashboard/vortex`.

- [ ] **Step 5: Check dark/light mode and empty state**

  - Toggle the theme switch and confirm all VORTEX charts/KPIs re-render with readable colors in both modes.
  - Change the date filter to a range with no VORTEX movements (e.g. a past year) and confirm both donuts show "Sin datos" and the leaderboard shows the empty-state message with a working "Registrar el primero" link.

- [ ] **Step 6: Fix any issues found, then commit**

  If any step above fails, fix the relevant file from Tasks 1-4 and commit:

  ```bash
  git add <fixed files>
  git commit -m "fix: <description of the fix>"
  ```

  If everything passes, no commit is needed for this task.
