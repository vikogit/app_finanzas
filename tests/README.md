# Pruebas de App Finanzas

Dos suites que se complementan. Ninguna toca la base de datos real: la de
backend usa sqlite en memoria y la de navegador levanta un servidor aparte
con datos de ejemplo.

## 1. Backend — `auditoria.py`

```bash
python tests/auditoria.py
```

Sin dependencias extra ni servidor: usa el cliente de pruebas de Flask.
Comprueba ~80 cosas:

- que cargan las 13 páginas y los 19 endpoints de API;
- que el rango "Todo" no devuelve respuestas gigantes;
- que un consumo de tarjeta cae dentro del rango del ciclo que se le muestra;
- reglas de negocio: neto invertido no negativo, fondo de tarjeta = aportes −
  repagos, un ciclo sin consumos no se marca "pagado";
- que un movimiento tipo `Fondo` se puede editar sin perder su tipo;
- que borrar solo se permite por POST;
- validación: rechaza importes negativos o cero, no numéricos, categorías
  inventadas, descripciones vacías y fechas inválidas;
- transferencias: crea exactamente dos movimientos y rechaza los casos
  inválidos (misma categoría, Inversión, Tarjeta);
- paginado del listado y que los totales cubren el filtro, no solo la página;
- CRUD de presupuesto y de metas por rango.

Devuelve código de salida 1 si algo falla, así que sirve para CI.

## 2. Navegador — `navegador.js`

Necesita Playwright con Chromium. En dos terminales:

```bash
python tests/servidor_pruebas.py          # deja el servidor en :5055
node tests/navegador.js
```

Abre la app de verdad en Chromium y revisa ~80 puntos:

- que cada pantalla carga sin errores de consola ni excepciones de JS, con
  todos los gráficos pintados y sin KPIs que se queden en "S/ —";
- el flujo completo: crear → editar → eliminar un movimiento;
- el asistente de activo de Inversión y la conversión de dólares;
- crear metas por rango y borrarlas, en los cuatro dashboards que las tienen;
- **seguridad**: mete `<img onerror=...>` en una descripción y verifica que
  ninguna pantalla lo ejecute;
- que no se escapen entidades HTML a la vista (`R &amp; D`);
- accesibilidad: todo input con etiqueta y todo botón con nombre;
- móvil a 390 px: ninguna página con scroll horizontal;
- modo claro.

## Datos de ejemplo

`servidor_pruebas.py` rehace la base en cada arranque con movimientos de
marzo a septiembre de 2026 en todas las categorías, incluidos días de pérdida
en Earnings (para ver barras rojas), un ciclo de tarjeta con consumo, repago y
fondo, y metas mensuales. Usuario y contraseña: `tester` / `tester`.

> `pruebas.db`, los `.log` y `capturas/` están en `.gitignore`.
