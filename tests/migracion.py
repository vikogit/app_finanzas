"""Migración al arrancar: una columna nueva en el modelo no debe romper la app.

    python tests/migracion.py

Reproduce lo que pasó en producción con `dinero_separado`: la tabla
`movimientos` ya existía con datos y sin las columnas nuevas, así que toda
consulta fallaba hasta entrar a mano a /crear-tabla. Arma una base con el
esquema viejo, arranca la app encima y comprueba que se migra sola, que no
pierde datos y que es idempotente.

Usa una base temporal: no toca `pruebas.db` ni la base real.
"""
import os
import sqlite3
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
BD = os.path.join(tempfile.mkdtemp(prefix="finanzas-migracion-"), "vieja.db").replace("\\", "/")

FALLOS = []


def check(etiqueta, cond, detalle=""):
    if cond:
        print(f"  OK   {etiqueta}")
    else:
        print(f"  FAIL {etiqueta} :: {detalle}")
        FALLOS.append((etiqueta, detalle))


# ── 1. base con el esquema anterior y una fila dentro ─────────────────
# Las columnas son las de `movimientos` antes de agregar dinero_separado.
ESQUEMA_VIEJO = """
CREATE TABLE movimientos (
    id INTEGER PRIMARY KEY,
    fecha DATE NOT NULL,
    tipo VARCHAR(20) NOT NULL,
    categoria VARCHAR(30) NOT NULL,
    descripcion VARCHAR(255) NOT NULL,
    importe NUMERIC(10,2) NOT NULL,
    investment_asset_type VARCHAR(50),
    investment_asset_name VARCHAR(100),
    pagado_con_tarjeta BOOLEAN NOT NULL DEFAULT FALSE
);
INSERT INTO movimientos (fecha, tipo, categoria, descripcion, importe, pagado_con_tarjeta)
VALUES ('2026-10-10', 'Gasto', 'Tarjeta', 'Netflix', 44.90, 1);
"""


def columnas_de(tabla="movimientos"):
    con = sqlite3.connect(BD)
    try:
        return [f[1] for f in con.execute(f"PRAGMA table_info({tabla})")]
    finally:
        con.close()


def main():
    con = sqlite3.connect(BD)
    con.executescript(ESQUEMA_VIEJO)
    con.commit()
    con.close()

    print("=== 1. Base con el esquema viejo ===")
    antes = columnas_de()
    check("la base arranca sin las columnas nuevas",
          "dinero_separado" not in antes and "dinero_separado_el" not in antes, str(antes))

    # ── 2. importar la app la migra en el arranque ────────────────────
    print("\n=== 2. El arranque aplica el esquema ===")
    os.environ["DATABASE_URL"] = f"sqlite:///{BD}"
    os.environ["SECRET_KEY"] = "clave-de-pruebas"
    os.environ["APP_USER"] = "tester"
    os.environ["APP_PASSWORD"] = "tester"
    sys.path.insert(0, RAIZ)
    import app as appmod  # noqa: E402  (tiene que importarse con el entorno ya puesto)

    despues = columnas_de()
    for columna in ("dinero_separado", "dinero_separado_el"):
        check(f"agregó {columna}", columna in despues, str(despues))

    con = sqlite3.connect(BD)
    filas = con.execute("SELECT descripcion, dinero_separado FROM movimientos").fetchall()
    con.close()
    check("conservó la fila que ya existía", len(filas) == 1 and filas[0][0] == "Netflix", str(filas))
    check("la fila vieja queda como 'sin dinero apartado'", filas and filas[0][1] in (0, False),
          str(filas))

    # ── 3. las consultas que fallaban vuelven a responder ─────────────
    print("\n=== 3. Las páginas y APIs que consultan movimientos ===")
    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "tester"

    for ruta in ["/movimientos", "/nuevo", "/dashboard/tarjeta", "/dashboard/necesidades",
                 "/api/resumen", "/api/tarjeta"]:
        r = c.get(ruta)
        check(f"GET {ruta}", r.status_code == 200,
              f"{r.status_code}: {(r.get_data(as_text=True) or '')[:150]}")

    # el endpoint que escribe en la columna nueva
    r = c.post("/api/tarjeta/consumos/1/dinero", json={"separado": True})
    check("POST /api/tarjeta/consumos/1/dinero", r.status_code == 200,
          f"{r.status_code}: {(r.get_data(as_text=True) or '')[:150]}")

    # ── 4. idempotencia ──────────────────────────────────────────────
    print("\n=== 4. Aplicarlo de nuevo no cambia nada ===")
    with appmod.app.app_context():
        notas = appmod.aplicar_esquema()
    check("la segunda pasada no agrega columnas", all("agregada" not in n for n in notas), str(notas))

    con = sqlite3.connect(BD)
    guardado = con.execute("SELECT dinero_separado FROM movimientos WHERE id = 1").fetchone()
    con.close()
    check("el dato guardado sobrevive", guardado and guardado[0] in (1, True), str(guardado))

    # ── 5. toda columna del modelo está en COLUMNAS_AGREGADAS o nace con la tabla ──
    print("\n=== 5. El inventario de columnas no se quedó corto ===")
    modelo = {c.name for c in appmod.Movimiento.__table__.columns}
    faltantes = modelo - set(columnas_de())
    check("la tabla migrada tiene todas las columnas del modelo", not faltantes, str(faltantes))

    # ── 6. los errores de base no filtran la contraseña ──────────────
    print("\n=== 6. Los errores de base no filtran credenciales ===")
    # El DSN aparece en los errores de conexión, y esos errores se muestran al
    # administrador y se imprimen en el log de Render.
    uri_falsa = "postgresql://usuario:s3cr3t0@host.interno:5432/finanzas"
    original = appmod.app.config["SQLALCHEMY_DATABASE_URI"]
    appmod.app.config["SQLALCHEMY_DATABASE_URI"] = uri_falsa
    try:
        limpio = appmod.sin_credenciales(Exception(f"could not connect to {uri_falsa}: timeout"))
    finally:
        appmod.app.config["SQLALCHEMY_DATABASE_URI"] = original
    check("oculta la contraseña del DSN", "s3cr3t0" not in limpio, limpio)
    check("oculta el DSN completo", uri_falsa not in limpio, limpio)
    check("conserva el detalle del error", "timeout" in limpio, limpio)

    print("\n" + "=" * 62)
    print(f"RESULTADO: {len(FALLOS)} fallos")
    for etiqueta, detalle in FALLOS:
        print(f"  - {etiqueta} :: {detalle}")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
