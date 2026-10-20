"""Cuadre de la tarjeta: /cuadrar-tarjeta deja el dashboard en su estado real.

    python tests/cuadre_tarjeta.py

Reproduce la base de producción de octubre de 2026 (estados de cuenta viejos
sin pagar y el ciclo en curso incompleto), aplica el cuadre por la ruta y
comprueba contra /api/tarjeta que el panel queda como debe: la deuda del
período que se paga el 20/11, cuánto está cubierto y cuánto falta.

Usa una base temporal: no toca `pruebas.db` ni la base real.
"""
import os
import sys
import datetime as dt
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
BD = os.path.join(tempfile.mkdtemp(prefix="finanzas-cuadre-"), "cuadre.db").replace("\\", "/")

os.environ["DATABASE_URL"] = f"sqlite:///{BD}"
os.environ["SECRET_KEY"] = "clave-de-pruebas"
os.environ["APP_USER"] = "tester"
os.environ["APP_PASSWORD"] = "tester"

sys.path.insert(0, RAIZ)
import app as appmod  # noqa: E402

M, db = appmod.Movimiento, appmod.db
HOY = dt.date(2026, 10, 19)
FALLOS = []


def check(etiqueta, obtenido, esperado):
    if obtenido == esperado:
        print(f"  OK   {etiqueta}: {obtenido!r}")
    else:
        print(f"  FAIL {etiqueta}: {obtenido!r} (esperado {esperado!r})")
        FALLOS.append(etiqueta)


def sembrar():
    """El mismo panorama que mostraba el dashboard antes del cuadre."""
    with appmod.app.app_context():
        db.create_all()
        db.session.add_all([
            # Estados de cuenta cerrados: 4369.03 de cargos, 534.25 ya pagados
            M(fecha=dt.date(2026, 8, 26), tipo="Gasto", categoria="Tarjeta",
              descripcion="Bitcoin", importe=1341.46),
            M(fecha=dt.date(2026, 8, 26), tipo="Gasto", categoria="Tarjeta",
              descripcion="Bitcoin", importe=335.03),
            M(fecha=dt.date(2026, 9, 10), tipo="Gasto", categoria="Tarjeta",
              descripcion="Pasaje", importe=2692.54),
            M(fecha=dt.date(2026, 7, 1), tipo="Fondo", categoria="Tarjeta",
              descripcion="Aporte", importe=500),
            M(fecha=dt.date(2026, 7, 20), tipo="Ingreso", categoria="Tarjeta",
              descripcion="Pago anterior", importe=534.25),
            # Ciclo en curso 26 sep → 25 oct: 135.00, con 15.00 ya marcado
            M(fecha=dt.date(2026, 9, 26), tipo="Gasto", categoria="Earnings",
              descripcion="Gasolina", importe=20, pagado_con_tarjeta=True),
            M(fecha=dt.date(2026, 9, 26), tipo="Gasto", categoria="Earnings",
              descripcion="Indrive", importe=15, pagado_con_tarjeta=True),
            M(fecha=dt.date(2026, 10, 2), tipo="Gasto", categoria="Earnings",
              descripcion="Gasolina", importe=20, pagado_con_tarjeta=True),
            M(fecha=dt.date(2026, 10, 2), tipo="Gasto", categoria="Earnings",
              descripcion="Gasolina", importe=50, pagado_con_tarjeta=True),
            M(fecha=dt.date(2026, 10, 2), tipo="Gasto", categoria="Earnings",
              descripcion="Indrive", importe=15, pagado_con_tarjeta=True),
            M(fecha=dt.date(2026, 10, 19), tipo="Gasto", categoria="Earnings",
              descripcion="Indrive", importe=15, pagado_con_tarjeta=True,
              dinero_separado=True, dinero_separado_el=HOY),
        ])
        db.session.commit()


def cliente():
    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "tester"
    return c


def main():
    appmod.hoy_local = lambda: HOY      # "hoy" fijo: la prueba no caduca
    sembrar()
    c = cliente()

    print("=== 1. Antes del cuadre ===")
    d = c.get("/api/tarjeta").get_json()
    check("deuda total arrastrada", d["kpis"]["deuda_total"], 3969.78)
    check("el panel apunta al estado de cuenta viejo", d["por_pagar"]["monto"], 3834.78)

    print("\n=== 2. La página explica qué va a hacer, sin tocar nada ===")
    r = c.get("/cuadrar-tarjeta")
    check("GET /cuadrar-tarjeta responde", r.status_code, 200)
    check("no escribió nada todavía",
          c.get("/api/tarjeta").get_json()["kpis"]["deuda_total"], 3969.78)

    print("\n=== 3. Aplicarlo deja el dashboard en su estado real ===")
    r = c.post("/cuadrar-tarjeta")
    check("POST /cuadrar-tarjeta responde", r.status_code, 200)

    d = c.get("/api/tarjeta").get_json()
    sel, ac = d["ciclo_sel"], d["acumulando"]
    check("deuda total", d["kpis"]["deuda_total"], 1465.46)
    check("total del período", sel["total"], 1465.46)
    check("con dinero", sel["separado"], 1347.60)
    check("sin dinero", sel["sin_separar"], 117.86)
    check("período mostrado", ac["periodo"], "26 sep → 25 oct")
    check("se paga hasta", ac["vencimiento"], "2026-11-20")
    check("sin estados de cuenta cerrados por pagar", d["por_pagar"], None)
    check("avisos de consumos olvidados", len(d["alertas"]), 0)
    viejo = next((x for x in d["ciclos"] if x["inicio"] == "2026-08-26"), None)
    check("el ciclo viejo queda pagado", viejo and viejo["estado"], "pagado")
    check("no se borró ningún consumo viejo",
          len([x for x in d["ciclos"] if x["inicio"] == "2026-08-26"]), 1)
    check("el fondo no se desploma por el pago registrado",
          d["kpis"]["dinero_disponible_pago"], -34.25)

    print("\n=== 4. Repetirlo no duplica nada ===")
    c.post("/cuadrar-tarjeta")
    d = c.get("/api/tarjeta").get_json()
    check("deuda total sigue igual", d["kpis"]["deuda_total"], 1465.46)
    check("con dinero sigue igual", d["ciclo_sel"]["separado"], 1347.60)
    check("sin dinero sigue igual", d["ciclo_sel"]["sin_separar"], 117.86)
    cuadres = [x for x in d["ciclo_sel"]["consumos"] if x["descripcion"] == "cuadre"]
    check("siguen siendo dos consumos de cuadre", len(cuadres), 2)

    print("\n" + "=" * 62)
    print(f"RESULTADO: {len(FALLOS)} fallos")
    for f in FALLOS:
        print(f"  - {f}")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
