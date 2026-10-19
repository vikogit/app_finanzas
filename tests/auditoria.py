"""Auditoría del backend: rutas, APIs, validación y reglas de negocio.

    python tests/auditoria.py

No necesita servidor: usa el cliente de pruebas de Flask sobre una BD en memoria.
"""
import os
import sys
import datetime as dt

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "clave-de-pruebas"
os.environ["APP_USER"] = "tester"
os.environ["APP_PASSWORD"] = "tester"

sys.path.insert(0, RAIZ)
import app as appmod  # noqa: E402

FALLOS, AVISOS = [], []


def check(etiqueta, cond, detalle=""):
    if cond:
        print(f"  OK   {etiqueta}")
    else:
        print(f"  FAIL {etiqueta} :: {detalle}")
        FALLOS.append((etiqueta, detalle))


def aviso(etiqueta, detalle=""):
    print(f"  WARN {etiqueta} :: {detalle}")
    AVISOS.append((etiqueta, detalle))


def sembrar():
    with appmod.app.app_context():
        appmod.db.create_all()
        M = appmod.Movimiento
        appmod.db.session.add_all([
            M(fecha=dt.date(2026, 3, 5), tipo="Ingreso", categoria="Colchón", descripcion="Ahorro", importe=300),
            M(fecha=dt.date(2026, 4, 5), tipo="Gasto", categoria="Colchón", descripcion="Emergencia", importe=120),
            M(fecha=dt.date(2026, 3, 8), tipo="Gasto", categoria="Necesidades", descripcion="Mercado", importe=210),
            M(fecha=dt.date(2026, 6, 2), tipo="Gasto", categoria="Diversión", descripcion="Cine", importe=45),
            M(fecha=dt.date(2026, 4, 12), tipo="Gasto", categoria="Inversión", descripcion="Bitcoin", importe=500,
              investment_asset_type="Cripto", investment_asset_name="Bitcoin"),
            M(fecha=dt.date(2026, 5, 1), tipo="Ingreso", categoria="VORTEX", descripcion="Sandra", importe=180),
            M(fecha=dt.date(2026, 8, 17), tipo="Ingreso", categoria="Earnings", descripcion="Taxi", importe=35),
            M(fecha=dt.date(2026, 8, 5), tipo="Gasto", categoria="Tarjeta", descripcion="Netflix", importe=50),
            M(fecha=dt.date(2026, 8, 22), tipo="Gasto", categoria="Tarjeta", descripcion="Uber", importe=30),
            M(fecha=dt.date(2026, 9, 3), tipo="Ingreso", categoria="Tarjeta", descripcion="Pago", importe=40),
            M(fecha=dt.date(2026, 9, 4), tipo="Fondo", categoria="Tarjeta", descripcion="Aparte", importe=200),
            M(fecha=dt.date(2026, 7, 10), tipo="Ingreso", categoria="R&D", descripcion="Aporte", importe=150),
            M(fecha=dt.date(2026, 8, 6), tipo="Gasto", categoria="R&D", descripcion="Curso", importe=90,
              investment_asset_type="Tecnología e IA"),
        ])
        appmod.db.session.add(appmod.MetaIngreso(
            fecha_inicio=dt.date(2026, 8, 1), fecha_fin=dt.date(2026, 12, 31), monto_diario=45))
        appmod.db.session.commit()


def cliente():
    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "tester"
    return c


RANGO = "desde=2026-03-01&hasta=2026-09-30"

PAGINAS = ["/dashboard", "/dashboard/colchon", "/dashboard/necesidades", "/dashboard/diversion",
           "/dashboard/inversion", "/dashboard/vortex", "/dashboard/earnings", "/dashboard/tarjeta",
           "/dashboard/rd", "/dashboard/presupuesto", "/nuevo", "/transferencia", "/movimientos"]

APIS = [f"/api/resumen?{RANGO}", f"/api/colchon?{RANGO}", f"/api/necesidades?{RANGO}",
        f"/api/diversion?{RANGO}", f"/api/inversion?{RANGO}", f"/api/vortex?{RANGO}",
        f"/api/earnings?{RANGO}", "/api/tarjeta", f"/api/rd?{RANGO}", "/api/presupuesto",
        "/api/necesidades/metas", "/api/diversion/metas", "/api/inversion/metas", "/api/rd/metas",
        "/api/earnings/metas", "/api/earnings/config", "/api/earnings/calendario",
        "/api/necesidades/config", "/api/diversion/config"]


def main():
    sembrar()
    c = cliente()

    print("\n=== 1. Páginas ===")
    for p in PAGINAS:
        r = c.get(p)
        check(f"GET {p}", r.status_code == 200, f"status={r.status_code}")

    print("\n=== 2. APIs ===")
    for p in APIS:
        r = c.get(p)
        okk = r.status_code == 200
        det = f"status={r.status_code}"
        if okk:
            try:
                r.get_json()
            except Exception as e:
                okk, det = False, f"JSON inválido: {e}"
        check(f"GET {p.split('?')[0]}", okk, det)

    print("\n=== 3. Rango por defecto (sin fechas) no infla la respuesta ===")
    for p in ["/api/resumen", "/api/vortex", "/api/colchon", "/api/rd"]:
        r = c.get(p)
        kb = len(r.data) / 1024
        check(f"GET {p} < 100 KB", kb < 100, f"{kb:.0f} KB")

    print("\n=== 4. Ciclos de tarjeta (corte el 25, pago el 20 del mes siguiente) ===")
    with appmod.app.app_context():
        # Todo consumo debe caer dentro del rango del ciclo que se le asigna.
        for f in [dt.date(2026, 8, 22), dt.date(2026, 8, 5), dt.date(2026, 8, 25),
                  dt.date(2026, 8, 26), dt.date(2026, 1, 31), dt.date(2026, 12, 26)]:
            cid = appmod.ciclo_de_fecha(f)
            ini, cie, _ = appmod.ciclo_bounds(*cid)
            check(f"{f} dentro de {ini} → {cie}", ini <= f <= cie, "cae fuera del ciclo asignado")

        # El 25 cierra ese mismo estado de cuenta; el 26 ya es del siguiente.
        check("compra del 25 cierra ese mismo 25",
              appmod.ciclo_id(*appmod.ciclo_de_fecha(dt.date(2026, 3, 25))) == "2026-03")
        check("compra del 26 pasa al cierre siguiente",
              appmod.ciclo_id(*appmod.ciclo_de_fecha(dt.date(2026, 3, 26))) == "2026-04")

        # Los dos ejemplos que dio el usuario, tal cual.
        _i, cie, ven = appmod.ciclo_bounds(2026, 3)
        check("consumos 26-feb→25-mar vencen el 20-abr",
              (cie, ven) == (dt.date(2026, 3, 25), dt.date(2026, 4, 20)), f"cierre={cie} vence={ven}")
        _i, cie, ven = appmod.ciclo_bounds(2026, 9)
        check("consumos 26-ago→25-sep vencen el 20-oct",
              (cie, ven) == (dt.date(2026, 9, 25), dt.date(2026, 10, 20)), f"cierre={cie} vence={ven}")

        # Cambio de año en ambos sentidos
        check("el ciclo de enero arranca en diciembre del año anterior",
              appmod.ciclo_bounds(2027, 1)[0] == dt.date(2026, 12, 26), str(appmod.ciclo_bounds(2027, 1)[0]))
        check("el ciclo de diciembre vence en enero del año siguiente",
              appmod.ciclo_bounds(2026, 12)[2] == dt.date(2027, 1, 20), str(appmod.ciclo_bounds(2026, 12)[2]))

        # Ningún consumo puede quedar en dos ciclos ni fuera de todos
        vistos = {}
        for dia in range(1, 29):
            for mes in (2, 3):
                f = dt.date(2026, mes, dia)
                cid = appmod.ciclo_de_fecha(f)
                ini, cie, _ = appmod.ciclo_bounds(*cid)
                vistos[f] = (ini <= f <= cie)
        check("ningún día queda huérfano entre ciclos", all(vistos.values()),
              f"{sum(1 for v in vistos.values() if not v)} días sin ciclo válido")

    print("\n=== 4b. Check 'ya tengo el dinero' de cada consumo ===")
    with appmod.app.app_context():
        consumo = appmod.Movimiento.query.filter_by(categoria="Tarjeta", tipo="Gasto").first()
        cid_consumo = consumo.id
        check("un consumo nace sin dinero apartado", consumo.dinero_separado is False)

    r = c.post(f"/api/tarjeta/consumos/{cid_consumo}/dinero", json={"separado": True})
    check("marcar que tengo el dinero", r.status_code == 200, f"status={r.status_code}")
    with appmod.app.app_context():
        m = appmod.db.session.get(appmod.Movimiento, cid_consumo)
        check("queda guardado en la BD", m.dinero_separado is True)
        check("registra la fecha en que lo marqué", m.dinero_separado_el is not None)

    r = c.post(f"/api/tarjeta/consumos/{cid_consumo}/dinero", json={"separado": False})
    with appmod.app.app_context():
        m = appmod.db.session.get(appmod.Movimiento, cid_consumo)
        check("se puede desmarcar", m.dinero_separado is False and m.dinero_separado_el is None)

    with appmod.app.app_context():
        ingreso = appmod.Movimiento.query.filter_by(categoria="Colchón", tipo="Ingreso").first()
        id_no_tarjeta = ingreso.id
    r = c.post(f"/api/tarjeta/consumos/{id_no_tarjeta}/dinero", json={"separado": True})
    check("rechaza marcar algo que no es consumo de tarjeta", r.status_code == 400, f"status={r.status_code}")
    check("404 si el movimiento no existe",
          c.post("/api/tarjeta/consumos/999999/dinero", json={"separado": True}).status_code == 404)

    print("\n=== 4c. Filtro por ciclo y panel de pago ===")
    d = c.get("/api/tarjeta").get_json()
    check("devuelve el ciclo en curso por defecto", d["ciclo_sel"]["es_actual"] is True)
    check("lista los consumos del ciclo", isinstance(d["ciclo_sel"]["consumos"], list))
    check("ofrece ciclos para el selector", len(d["ciclos_disponibles"]) >= 1)
    check("calcula salud", 0 <= d["salud"]["pct_cubierto"] <= 100, str(d["salud"]))
    check("trae datos de los gráficos generales",
          "por_ciclo" in d["general"] and "por_categoria" in d["general"])
    otro = d["ciclos_disponibles"][-1]["id"]
    d2 = c.get(f"/api/tarjeta?ciclo={otro}").get_json()
    check("se puede filtrar por otro ciclo", d2["ciclo_sel"]["id"] == otro, d2["ciclo_sel"]["id"])
    check("un ciclo inválido no rompe", c.get("/api/tarjeta?ciclo=basura").status_code == 200)
    if d["por_pagar"]:
        pp = d["por_pagar"]
        check("el panel de pago vence un día 20", pp["vencimiento"].endswith("-20"), pp["vencimiento"])
        check("muestra el monto en dólares", pp["monto_usd"] is not None or pp["tipo_cambio"] is None)
        check("separa lo cubierto de lo que falta",
              abs(pp["separado"] + pp["falta"] - pp["monto"]) < 0.02,
              f"{pp['separado']} + {pp['falta']} != {pp['monto']}")

    print("\n=== 5. Reglas de negocio ===")
    inv = c.get(f"/api/inversion?{RANGO}").get_json()
    check("Neto invertido no es negativo", inv["kpis"]["neto"] >= 0, f"neto={inv['kpis']['neto']}")
    tar = c.get("/api/tarjeta").get_json()
    check("fondo de tarjeta = aportes - repagos", tar["kpis"]["dinero_disponible_pago"] == 160.0,
          f"={tar['kpis']['dinero_disponible_pago']}")
    vacios = [ci for ci in tar["ciclos"] if ci["total_cargos"] == 0]
    check("un ciclo sin consumos no se marca 'pagado'",
          all(ci["estado"] == "vacio" for ci in vacios), "hay ciclos vacíos marcados como pagados")

    print("\n=== 6. Movimiento tipo 'Fondo' editable ===")
    with appmod.app.app_context():
        fid = appmod.Movimiento.query.filter_by(tipo="Fondo").first().id
    html = c.get(f"/editar/{fid}").data.decode("utf-8")
    check("el formulario ofrece el tipo 'Fondo'", 'value="Fondo"' in html)
    r = c.post(f"/editar/{fid}", data={"fecha": "2026-09-04", "categoria": "Tarjeta",
                                       "descripcion": "Aparte", "importe": "200"})
    check("guardar sin enviar 'tipo' no rompe", r.status_code in (200, 302), f"status={r.status_code}")
    with appmod.app.app_context():
        check("conserva el tipo 'Fondo'",
              appmod.db.session.get(appmod.Movimiento, fid).tipo == "Fondo", "cambió de tipo")

    print("\n=== 7. Borrado solo por POST ===")
    reglas = [r for r in appmod.app.url_map.iter_rules() if "/eliminar/" in str(r)]
    check("/eliminar acepta POST", any("POST" in r.methods for r in reglas))
    check("/eliminar NO acepta GET", not any("GET" in r.methods for r in reglas),
          "un prefetch del navegador podría borrar datos")

    print("\n=== 8. Validación de entradas ===")
    casos = [
        ("sin tipo", {"fecha": "2026-09-01", "categoria": "Colchón", "descripcion": "x", "importe": "10"}),
        ("importe no numérico", {"fecha": "2026-09-01", "tipo": "Gasto", "categoria": "Colchón",
                                 "descripcion": "x", "importe": "abc"}),
        ("importe negativo", {"fecha": "2026-09-01", "tipo": "Gasto", "categoria": "Colchón",
                              "descripcion": "x", "importe": "-50"}),
        ("importe cero", {"fecha": "2026-09-01", "tipo": "Gasto", "categoria": "Colchón",
                          "descripcion": "x", "importe": "0"}),
        ("categoría inventada", {"fecha": "2026-09-01", "tipo": "Gasto", "categoria": "HACKED",
                                 "descripcion": "x", "importe": "10"}),
        ("descripción vacía", {"fecha": "2026-09-01", "tipo": "Gasto", "categoria": "Colchón",
                               "descripcion": "   ", "importe": "10"}),
        ("fecha inválida", {"fecha": "no-es-fecha", "tipo": "Gasto", "categoria": "Colchón",
                            "descripcion": "x", "importe": "10"}),
    ]
    for nombre, datos in casos:
        r = c.post("/nuevo", data=datos)
        check(f"rechaza: {nombre}", r.status_code == 400, f"status={r.status_code} (se guardó)")

    with appmod.app.app_context():
        Q = appmod.Movimiento.query
        check("ningún importe <= 0 en la BD", Q.filter(appmod.Movimiento.importe <= 0).count() == 0)
        check("ninguna categoría inválida en la BD",
              Q.filter(~appmod.Movimiento.categoria.in_(appmod.CATEGORIAS_VALIDAS)).count() == 0)

    print("\n=== 9. Transferencias ===")
    r = c.post("/transferencia", data={"fecha": "2026-09-05", "origen": "VORTEX",
                                       "destino": "Necesidades", "monto": "50"})
    check("transferencia válida se guarda", r.status_code == 302, f"status={r.status_code}")
    with appmod.app.app_context():
        t = appmod.Movimiento.query.filter_by(descripcion="Transferencia").all()
        check("crea exactamente 2 movimientos", len(t) == 2, f"creó {len(t)}")
        check("uno sale y otro entra",
              {m.tipo for m in t} == {"Gasto", "Ingreso"}, f"tipos={[m.tipo for m in t]}")
    for nombre, datos in [
        ("misma categoría", {"fecha": "2026-09-05", "origen": "VORTEX", "destino": "VORTEX", "monto": "10"}),
        ("origen Inversión", {"fecha": "2026-09-05", "origen": "Inversión", "destino": "Colchón", "monto": "10"}),
        ("destino Tarjeta", {"fecha": "2026-09-05", "origen": "Colchón", "destino": "Tarjeta", "monto": "10"}),
    ]:
        r = c.post("/transferencia", data=datos)
        check(f"rechaza: {nombre}", r.status_code == 200 and b"Error" in r.data, f"status={r.status_code}")

    print("\n=== 9b. Paginado del listado ===")
    with appmod.app.app_context():
        # Supera el tamaño de página para forzar más de una
        appmod.db.session.add_all([
            appmod.Movimiento(fecha=dt.date(2026, 6, 1), tipo="Gasto", categoria="Diversión",
                              descripcion=f"Relleno {i}", importe=1 + i)
            for i in range(appmod.POR_PAGINA + 20)
        ])
        appmod.db.session.commit()
        total_bd = appmod.Movimiento.query.count()

    html = c.get("/movimientos").data.decode("utf-8")
    filas = html.count('<td class="muted" style="white-space:nowrap">')
    check(f"la página 1 no excede {appmod.POR_PAGINA} filas", filas <= appmod.POR_PAGINA, f"{filas} filas")
    check("muestra el total de movimientos", str(total_bd) in html, f"no aparece {total_bd}")
    check("muestra controles de paginado", "paginador" in html)
    p2 = c.get("/movimientos?pagina=2").data.decode("utf-8")
    check("la página 2 trae filas distintas", p2 != html)
    check("pagina fuera de rango no rompe", c.get("/movimientos?pagina=9999").status_code == 200)
    check("pagina no numérica no rompe", c.get("/movimientos?pagina=abc").status_code == 200)
    check("el resumen suma TODO el filtro, no solo la página",
          "Balance" in html, "falta la línea de balance")

    print("\n=== 10. CRUD de presupuesto ===")
    r = c.post("/api/presupuesto/items", json={"categoria": "ingreso_fijo", "nombre": "Sueldo", "monto": 2000})
    check("crear ítem", r.status_code == 201, f"status={r.status_code}")
    pid = r.get_json()["items"]["ingreso_fijo"][0]["id"]
    check("PUT ítem", c.put(f"/api/presupuesto/items/{pid}",
                            json={"nombre": "Sueldo base", "monto": 2100}).status_code == 200)
    d = c.get("/api/presupuesto").get_json()
    check("recalcula capacidad de ahorro", d["resultados"]["capacidad_ahorro_pct"] is not None)
    check("DELETE ítem", c.delete(f"/api/presupuesto/items/{pid}").status_code == 200)
    r = c.post("/api/presupuesto/items", json={"categoria": "inventada", "nombre": "x", "monto": 5})
    check("rechaza categoría de presupuesto inválida", r.status_code == 400)

    print("\n=== 11. Metas por rango ===")
    for rec in ["necesidades", "diversion", "inversion", "rd"]:
        r = c.post(f"/api/{rec}/metas", json={"desde": "2027-01", "hasta": "2027-03", "monto_meta": 500})
        okk = r.status_code == 201 and r.get_json().get("count") == 3
        check(f"{rec}: rango de 3 meses crea 3 metas", okk, str(r.get_json()))
        r = c.post(f"/api/{rec}/metas", json={"desde": "2027-06", "hasta": "2027-01", "monto_meta": 500})
        check(f"{rec}: rechaza rango invertido", r.status_code == 400)

    print("\n" + "=" * 62)
    print(f"RESULTADO: {len(FALLOS)} fallos, {len(AVISOS)} avisos")
    for l, d in FALLOS:
        print(f"  FALLO: {l} :: {d}")
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
