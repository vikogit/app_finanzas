# Dashboard VORTEX — Diseño

## Contexto

`VORTEX` es una categoría de movimiento (ingreso/gasto) que representa un emprendimiento
educativo (VORTEX y TECSUP) que el usuario gestiona como gerente. Actualmente, al igual
que Colchón, Necesidades, Diversión e Inversión, los movimientos VORTEX se registran vía
`/nuevo`, pero no existe una página de dashboard dedicada para analizarlos.

El usuario quiere:
- Un dashboard financiero de VORTEX (ingresos vs gastos, igual estilo visual que las demás
  categorías).
- Ver los ingresos desglosados por alumno — el alumno se identifica por el campo
  `descripcion` que se ingresa al registrar cada ingreso.
- Gráficos adicionales que den buen storytelling para la gestión del negocio.

## Alcance

Incluye: nueva página `/dashboard/vortex`, nuevo endpoint `/api/vortex`, entrada en el
navbar y en la grilla de Resumen. No incluye: cambios al modelo de datos, autenticación
por alumno, ni un CRUD de alumnos — todo se deriva de los campos existentes
(`categoria`, `tipo`, `descripcion`, `importe`, `fecha`) de `Movimiento`.

## Color y navegación

- Color de acento: cian/turquesa — `#06b6d4` (modo claro) / `#22d3ee` (modo oscuro).
  No colisiona con los colores ya usados (verde=Colchón, índigo=Necesidades,
  naranja=Diversión, amarillo=Inversión).
- Nuevo tab **"VORTEX"** en `base.html`, entre "Inversión" y "Portafolio".
- Nueva tarjeta **"VORTEX"** en `dashboard.html` (Resumen), mismo patrón `cat-card` que
  las 4 existentes, con su propio ícono y color cian.
- Nueva ruta `/dashboard/vortex` → `vortex.html`, con `active_tab="vortex"`.

## KPIs (kpi-grid-4, igual patrón que Diversión)

1. Ingresos totales del período
2. Gastos totales del período
3. Utilidad neta (ingresos − gastos)
4. Margen (%) = utilidad / ingresos × 100 (0 si no hay ingresos)

## Gráficos

**Fila 1** (`charts-grid-main`, patrón eToro de Colchón/Inversión):
- Área: evolución de utilidad acumulada mes a mes (`renderEtoroChart`)
- Donut: ingresos por alumno — top alumnos por descripción (`renderDonutChart`)

**Fila 2** (`charts-grid`, patrón bar chart del Resumen):
- Barras: ingresos vs gastos por mes (dos datasets, mismo estilo que `chartBarMensual`
  en `dashboard.html`)
- Donut: gastos por concepto — agrupado por descripción de los gastos

**Tabla leaderboard** (estilo `tbl`/`tbl-card` de `movimientos.html`):
- Ranking de alumnos: posición, nombre (descripción), total pagado, N° de pagos, %
  del total de ingresos — ordenado de mayor a menor.
- Subtítulo con el conteo de alumnos activos (descripciones distintas con ingresos)
  en el período.
- Estado vacío (`empty-state`) si no hay ingresos en el período.

## Backend

Nuevo endpoint `GET /api/vortex?desde&hasta` en `app.py`, mismo patrón que
`api_colchon`/`api_diversion`:

- Filtra `Movimiento` por `categoria == "VORTEX"` en el rango de fechas
  (`query_movs(desde, hasta, categoria="VORTEX")`).
- KPIs: suma de ingresos, suma de gastos, utilidad neta, margen % (protegido contra
  división por cero).
- `evolucion`: utilidad acumulada por mes — reutiliza `agrupar_mensual` + acumulador
  (igual que `api_colchon`).
- `por_mes`: ingresos y gastos por mes tal cual devuelve `agrupar_mensual` (para el bar
  chart).
- `ingresos_por_alumno`: nuevo helper `ranking_por_descripcion(movs)` que agrupa
  movimientos `tipo="Ingreso"` por `descripcion`, sumando importe y contando pagos.
  Devuelve tanto la forma `{label, value}` (para el donut) como la forma extendida
  `{alumno, total, num_pagos, pct}` (para la tabla leaderboard).
- `gastos_por_concepto`: reutiliza el helper `top_items` existente sobre movimientos
  `tipo="Gasto"`.

No se modifica el modelo `Movimiento` ni se crean tablas nuevas.

## Frontend

- `templates/vortex.html` extiende `base.html`, reutiliza `renderEtoroChart`,
  `renderDonutChart`, filtros de fecha (`getDefaultDates`, `setQuickFilter`,
  `applyFilter`) y el patrón de bar chart de `dashboard.html`. Sin nuevas dependencias
  JS ni CSS fuera de lo ya definido en `base.html`.
- Estados vacíos: donuts caen a `{label:'Sin datos', value:1}` (patrón ya usado); tabla
  leaderboard usa el `empty-state` ya existente en `movimientos.html`.

## Verificación

El proyecto no tiene suite de pruebas automatizadas (app Flask simple). Verificación
manual: correr la app localmente, registrar movimientos VORTEX de prueba (ingresos con
distintas descripciones de "alumno", gastos con distintos conceptos) y confirmar que
KPIs, gráficos y tabla reflejan los datos correctamente en modo claro y oscuro, y que
el filtro de fechas actualiza todo correctamente.
