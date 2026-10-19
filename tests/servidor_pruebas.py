"""Levanta la app con una BD sqlite sembrada, para pruebas manuales o de navegador.

    python tests/servidor_pruebas.py       →  http://127.0.0.1:5055  (tester / tester)
"""
import os
import sys
import datetime as dt

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DB = os.path.join(AQUI, "pruebas.db").replace("\\", "/")

os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["SECRET_KEY"] = "clave-de-pruebas"
os.environ["APP_USER"] = "tester"
os.environ["APP_PASSWORD"] = "tester"

sys.path.insert(0, RAIZ)
import app as appmod  # noqa: E402


def sembrar():
    with appmod.app.app_context():
        appmod.db.drop_all()
        appmod.db.create_all()
        M = appmod.Movimiento
        filas = []
        for i, (mes, dia) in enumerate([(3, 4), (4, 6), (5, 8), (6, 3), (7, 9), (8, 12), (9, 2)]):
            filas += [
                M(fecha=dt.date(2026, mes, dia), tipo="Ingreso", categoria="Colchón",
                  descripcion="Ahorro mensual", importe=200 + i * 25),
                M(fecha=dt.date(2026, mes, dia + 1), tipo="Gasto", categoria="Necesidades",
                  descripcion=["Mercado", "Pasajes", "Farmacia", "Recibos"][i % 4], importe=120 + i * 18),
                M(fecha=dt.date(2026, mes, dia + 2), tipo="Gasto", categoria="Diversión",
                  descripcion=["Cine", "Comida", "Música", "Salidas", "Bebidas"][i % 5], importe=40 + i * 9),
                M(fecha=dt.date(2026, mes, dia + 3), tipo="Gasto", categoria="Inversión",
                  descripcion="Bitcoin" if i % 2 else "S&P 500", importe=150 + i * 30,
                  investment_asset_type="Cripto" if i % 2 else "ETFs",
                  investment_asset_name="Bitcoin" if i % 2 else "S&P 500"),
                M(fecha=dt.date(2026, mes, dia + 4), tipo="Ingreso", categoria="VORTEX",
                  descripcion=["Sandra", "Abigail", "Marco", "Lucía"][i % 4], importe=180 + i * 15),
                M(fecha=dt.date(2026, mes, dia + 5), tipo="Ingreso", categoria="Earnings",
                  descripcion="Taxi", importe=35 + i * 4),
            ]
        # Días de pérdida en Earnings → barras rojas
        filas += [
            M(fecha=dt.date(2026, 5, 14), tipo="Gasto", categoria="Earnings", descripcion="Gasolina", importe=70),
            M(fecha=dt.date(2026, 7, 21), tipo="Gasto", categoria="Earnings", descripcion="Mantenimiento", importe=120),
            M(fecha=dt.date(2026, 7, 21), tipo="Ingreso", categoria="Earnings", descripcion="Taxi", importe=45),
            M(fecha=dt.date(2026, 9, 12), tipo="Gasto", categoria="Earnings", descripcion="Multa", importe=40),
            M(fecha=dt.date(2026, 9, 18), tipo="Ingreso", categoria="Earnings", descripcion="Taxi", importe=8),
            # Tarjeta: consumo, repago y fondo
            M(fecha=dt.date(2026, 8, 5), tipo="Gasto", categoria="Tarjeta", descripcion="Netflix", importe=50),
            M(fecha=dt.date(2026, 8, 22), tipo="Gasto", categoria="Tarjeta", descripcion="Uber", importe=30),
            # Consumos del ciclo en curso (26-sep → 25-oct), unos con dinero y otros sin él
            M(fecha=dt.date(2026, 9, 28), tipo="Gasto", categoria="Tarjeta", descripcion="Netflix", importe=44.90),
            M(fecha=dt.date(2026, 10, 1), tipo="Gasto", categoria="Necesidades", descripcion="Supermercado",
              importe=312.40, pagado_con_tarjeta=True, dinero_separado=True),
            M(fecha=dt.date(2026, 10, 3), tipo="Gasto", categoria="Tarjeta", descripcion="Spotify", importe=26.90),
            M(fecha=dt.date(2026, 10, 7), tipo="Gasto", categoria="Diversión", descripcion="Cine",
              importe=58.00, pagado_con_tarjeta=True),
            M(fecha=dt.date(2026, 10, 11), tipo="Gasto", categoria="Necesidades", descripcion="Farmacia",
              importe=89.50, pagado_con_tarjeta=True, dinero_separado=True),
            M(fecha=dt.date(2026, 10, 14), tipo="Gasto", categoria="Tarjeta", descripcion="Uber", importe=37.20),
            M(fecha=dt.date(2026, 10, 16), tipo="Gasto", categoria="Diversión", descripcion="Restaurante",
              importe=145.00, pagado_con_tarjeta=True),
            # Ciclo anterior (26-ago → 25-sep): es el que vence el 20-oct
            M(fecha=dt.date(2026, 9, 2), tipo="Gasto", categoria="Tarjeta", descripcion="Amazon", importe=210.00,
              dinero_separado=True),
            M(fecha=dt.date(2026, 9, 12), tipo="Gasto", categoria="Necesidades", descripcion="Supermercado",
              importe=268.30, pagado_con_tarjeta=True),
            M(fecha=dt.date(2026, 9, 3), tipo="Ingreso", categoria="Tarjeta", descripcion="Pago ciclo", importe=40),
            M(fecha=dt.date(2026, 9, 4), tipo="Fondo", categoria="Tarjeta", descripcion="Aparte sueldo", importe=200),
            M(fecha=dt.date(2026, 8, 10), tipo="Gasto", categoria="Necesidades", descripcion="Farmacia",
              importe=25, pagado_con_tarjeta=True),
            M(fecha=dt.date(2026, 7, 10), tipo="Ingreso", categoria="R&D", descripcion="Aporte", importe=150),
            M(fecha=dt.date(2026, 8, 6), tipo="Gasto", categoria="R&D", descripcion="Curso IA", importe=90,
              investment_asset_type="Tecnología e IA", investment_asset_name="IA Generativa & Prompting"),
            M(fecha=dt.date(2026, 9, 6), tipo="Ingreso", categoria="R&D", descripcion="Aporte", importe=120),
        ]
        appmod.db.session.add_all(filas)
        appmod.db.session.add(appmod.MetaIngreso(
            fecha_inicio=dt.date(2026, 8, 1), fecha_fin=dt.date(2026, 12, 31), monto_diario=45))
        for mes in range(3, 10):
            appmod.db.session.add(appmod.MetaNecesidadesMes(year=2026, month=mes, monto_meta=450))
            appmod.db.session.add(appmod.MetaDiversionMes(year=2026, month=mes, monto_meta=200))
            appmod.db.session.add(appmod.MetaInversionMes(year=2026, month=mes, monto_meta=300))
            appmod.db.session.add(appmod.MetaRdMes(year=2026, month=mes, monto_meta=150))
        appmod.db.session.commit()
        appmod.seed_presupuesto_si_vacio()
        print(f"Sembrado: {M.query.count()} movimientos", flush=True)


if __name__ == "__main__":
    sembrar()
    appmod.app.run(port=5055, debug=False, use_reloader=False)
