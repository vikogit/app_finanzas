from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from config import Config
from datetime import datetime, date as date_type, timedelta
from zoneinfo import ZoneInfo
from functools import wraps
from collections import defaultdict
import os
import calendar
import requests as http_requests
import time

app = Flask(__name__)
app.config.from_object(Config)

USUARIO_ADMIN = os.getenv("APP_USER")
PASSWORD_ADMIN = os.getenv("APP_PASSWORD")

db = SQLAlchemy(app)

# El servidor (Render) corre en UTC — usar date.today() ahí hace que "hoy"
# cambie ~7pm hora de Perú en vez de a medianoche local. Fijar la zona
# horaria explícitamente para toda fecha derivada de "ahora".
LOCAL_TZ = ZoneInfo("America/Lima")


def hoy_local():
    return datetime.now(LOCAL_TZ).date()


def login_requerido(f):
    @wraps(f)
    def funcion_protegida(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return funcion_protegida


class Movimiento(db.Model):
    __tablename__ = "movimientos"
    id                   = db.Column(db.Integer, primary_key=True)
    fecha                = db.Column(db.Date, nullable=False)
    tipo                 = db.Column(db.String(20), nullable=False)
    categoria            = db.Column(db.String(30), nullable=False)
    descripcion          = db.Column(db.String(255), nullable=False)
    importe              = db.Column(db.Numeric(10, 2), nullable=False)
    investment_asset_type = db.Column(db.String(50),  nullable=True)
    investment_asset_name = db.Column(db.String(100), nullable=True)
    pagado_con_tarjeta   = db.Column(db.Boolean, nullable=False, default=False)


class PagoTarjeta(db.Model):
    __tablename__ = "pagos_tarjeta"
    id     = db.Column(db.Integer, primary_key=True)
    fecha  = db.Column(db.Date, nullable=False)
    monto  = db.Column(db.Numeric(10, 2), nullable=False)
    nota   = db.Column(db.String(255), nullable=True)


class MetaIngreso(db.Model):
    __tablename__ = "metas_ingreso"
    id           = db.Column(db.Integer, primary_key=True)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin    = db.Column(db.Date, nullable=False)
    monto_diario = db.Column(db.Numeric(10, 2), nullable=False)


class MetaDiasMes(db.Model):
    __tablename__ = "metas_dias_mes"
    id        = db.Column(db.Integer, primary_key=True)
    year      = db.Column(db.Integer, nullable=False)
    month     = db.Column(db.Integer, nullable=False)
    dias_meta = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.UniqueConstraint("year", "month", name="uq_metas_dias_mes_year_month"),)


DIAS_META_DEFAULT = 20


def get_dias_meta_mes(year, month):
    row = MetaDiasMes.query.filter_by(year=year, month=month).first()
    return row.dias_meta if row else DIAS_META_DEFAULT


def set_dias_meta_mes(year, month, n):
    row = MetaDiasMes.query.filter_by(year=year, month=month).first()
    if row:
        row.dias_meta = n
    else:
        row = MetaDiasMes(year=year, month=month, dias_meta=n)
        db.session.add(row)
    db.session.commit()


class MetaNecesidadesMes(db.Model):
    __tablename__ = "metas_necesidades_mes"
    id         = db.Column(db.Integer, primary_key=True)
    year       = db.Column(db.Integer, nullable=False)
    month      = db.Column(db.Integer, nullable=False)
    monto_meta = db.Column(db.Numeric(10, 2), nullable=False)
    __table_args__ = (db.UniqueConstraint("year", "month", name="uq_metas_necesidades_mes_year_month"),)


def get_meta_necesidades_mes(year, month):
    row = MetaNecesidadesMes.query.filter_by(year=year, month=month).first()
    return float(row.monto_meta) if row else None


def set_meta_necesidades_mes(year, month, monto):
    row = MetaNecesidadesMes.query.filter_by(year=year, month=month).first()
    if row:
        row.monto_meta = monto
    else:
        row = MetaNecesidadesMes(year=year, month=month, monto_meta=monto)
        db.session.add(row)
    db.session.commit()


class MetaDiversionMes(db.Model):
    __tablename__ = "metas_diversion_mes"
    id         = db.Column(db.Integer, primary_key=True)
    year       = db.Column(db.Integer, nullable=False)
    month      = db.Column(db.Integer, nullable=False)
    monto_meta = db.Column(db.Numeric(10, 2), nullable=False)
    __table_args__ = (db.UniqueConstraint("year", "month", name="uq_metas_diversion_mes_year_month"),)


def get_meta_diversion_mes(year, month):
    row = MetaDiversionMes.query.filter_by(year=year, month=month).first()
    return float(row.monto_meta) if row else None


def set_meta_diversion_mes(year, month, monto):
    row = MetaDiversionMes.query.filter_by(year=year, month=month).first()
    if row:
        row.monto_meta = monto
    else:
        row = MetaDiversionMes(year=year, month=month, monto_meta=monto)
        db.session.add(row)
    db.session.commit()


# ── helpers ──────────────────────────────────────────────────────────

def parse_dates(req):
    def _p(s, fallback):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date() if s else fallback
        except ValueError:
            return fallback
    return (
        _p(req.args.get("desde", ""), date_type(2000, 1, 1)),
        _p(req.args.get("hasta", ""), hoy_local()),
    )


def query_movs(desde, hasta, categoria=None, tipo=None):
    q = Movimiento.query.filter(
        Movimiento.fecha >= desde, Movimiento.fecha <= hasta
    )
    if categoria:
        q = q.filter(Movimiento.categoria == categoria)
    if tipo:
        q = q.filter(Movimiento.tipo == tipo)
    return q.order_by(Movimiento.fecha).all()


def agrupar_mensual(movs, desde, hasta):
    bucket = defaultdict(lambda: {"ingresos": 0.0, "gastos": 0.0})
    for m in movs:
        key = (m.fecha.year, m.fecha.month)
        v = float(m.importe)
        bucket[key]["ingresos" if m.tipo == "Ingreso" else "gastos"] += v
    meses = []
    y, mo = desde.year, desde.month
    while (y, mo) <= (hasta.year, hasta.month):
        v = bucket.get((y, mo), {"ingresos": 0.0, "gastos": 0.0})
        meses.append({"mes": date_type(y, mo, 1).strftime("%b %Y"), "ingresos": v["ingresos"], "gastos": v["gastos"]})
        mo += 1
        if mo > 12:
            mo = 1
            y += 1
    return meses


def agrupar_diario(movs, desde, hasta):
    bucket = defaultdict(lambda: {"ingresos": 0.0, "gastos": 0.0})
    for m in movs:
        v = float(m.importe)
        bucket[m.fecha]["ingresos" if m.tipo == "Ingreso" else "gastos"] += v
    dias = []
    dia = desde
    while dia <= hasta:
        v = bucket.get(dia, {"ingresos": 0.0, "gastos": 0.0})
        dias.append({"fecha": dia.strftime("%d %b"), "ingresos": v["ingresos"], "gastos": v["gastos"]})
        dia += timedelta(days=1)
    return dias


def sma(values, window):
    out = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
        else:
            out.append(round(sum(values[i + 1 - window:i + 1]) / window, 2))
    return out


def top_items(movs, n=8):
    bucket = defaultdict(float)
    for m in movs:
        bucket[m.descripcion] += float(m.importe)
    return [{"label": k, "value": round(v, 2)}
            for k, v in sorted(bucket.items(), key=lambda x: -x[1])[:n]]


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


# ── ciclos de tarjeta de crédito ────────────────────────────────────────
# Corte el día 20: un ciclo agrupa consumos del 25 de un mes al 20 del
# siguiente, con vencimiento de pago el 20 del mes subsiguiente
# (ej. consumos del 25-jul al 20-ago vencen el 20-sep).

def _add_months(year, month, delta):
    total = (year * 12 + (month - 1)) + delta
    return total // 12, total % 12 + 1


def ciclo_de_fecha(fecha):
    """Devuelve (year, month) del día 25 en que abre el ciclo al que pertenece `fecha`."""
    if fecha.day >= 21:
        return fecha.year, fecha.month
    y, m = _add_months(fecha.year, fecha.month, -1)
    return y, m


def ciclo_bounds(year, month):
    inicio = date_type(year, month, 25)
    cy, cm = _add_months(year, month, 1)
    cierre = date_type(cy, cm, 20)
    dy, dm = _add_months(year, month, 2)
    vencimiento = date_type(dy, dm, 20)
    return inicio, cierre, vencimiento


def ciclo_id(year, month):
    return f"{year:04d}-{month:02d}"


# ── page routes ───────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if (request.form["usuario"] == USUARIO_ADMIN and
                request.form["password"] == PASSWORD_ADMIN):
            session["usuario"] = request.form["usuario"]
            return redirect(url_for("dashboard"))
        error = "Usuario o contraseña incorrectos"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_requerido
def dashboard():
    return render_template("dashboard.html", active_tab="resumen")


@app.route("/dashboard/colchon")
@login_requerido
def dashboard_colchon():
    return render_template("colchon.html", active_tab="colchon")


@app.route("/dashboard/necesidades")
@login_requerido
def dashboard_necesidades():
    return render_template("necesidades_dash.html", active_tab="necesidades")


@app.route("/dashboard/diversion")
@login_requerido
def dashboard_diversion():
    return render_template("diversion.html", active_tab="diversion")


@app.route("/dashboard/inversion")
@login_requerido
def dashboard_inversion():
    return render_template("inversion.html", active_tab="inversion")


@app.route("/dashboard/vortex")
@login_requerido
def dashboard_vortex():
    return render_template("vortex.html", active_tab="vortex")


@app.route("/dashboard/earnings")
@login_requerido
def dashboard_earnings():
    return render_template("earnings.html", active_tab="earnings")


@app.route("/dashboard/tarjeta")
@login_requerido
def dashboard_tarjeta():
    return render_template("tarjeta.html", active_tab="tarjeta")


@app.route("/dashboard/rd")
@login_requerido
def dashboard_rd():
    return render_template("rd.html", active_tab="rd")


@app.route("/nuevo", methods=["GET", "POST"])
@login_requerido
def nuevo():
    if request.method == "POST":
        if request.form.get("tipo") == "Meta":
            try:
                fecha_inicio = datetime.strptime(request.form["fecha"], "%Y-%m-%d").date()
                fecha_fin    = datetime.strptime(request.form["fecha_fin"], "%Y-%m-%d").date()
                monto_diario = float(request.form["importe"])
                if fecha_fin < fecha_inicio:
                    return "Error al guardar: la fecha fin no puede ser anterior a la fecha inicio"
                if monto_diario <= 0:
                    return "Error al guardar: el monto diario debe ser mayor a 0"
                meta = MetaIngreso(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, monto_diario=monto_diario)
                db.session.add(meta)
                db.session.commit()
                return redirect(url_for("dashboard_earnings"))
            except Exception as e:
                db.session.rollback()
                return f"Error al guardar: {str(e)}"
        try:
            m = Movimiento(
                fecha=datetime.strptime(request.form["fecha"], "%Y-%m-%d").date(),
                tipo=request.form["tipo"],
                categoria=request.form["categoria"],
                descripcion=request.form["descripcion"],
                importe=float(request.form["importe"]),
                investment_asset_type=request.form.get("investment_asset_type") or None,
                investment_asset_name=request.form.get("investment_asset_name") or None,
                pagado_con_tarjeta=bool(request.form.get("pagado_con_tarjeta")),
            )
            db.session.add(m)
            db.session.commit()
            return redirect(url_for("ver_movimientos"))
        except Exception as e:
            db.session.rollback()
            return f"Error al guardar: {str(e)}"
    return render_template("nuevo_movimiento.html")


@app.route("/movimientos")
@login_requerido
def ver_movimientos():
    desde_raw       = request.args.get("desde", "")
    hasta_raw       = request.args.get("hasta", "")
    tipo_raw        = request.args.get("tipo", "")
    categoria_raw   = request.args.get("categoria", "")
    descripcion_raw = request.args.get("descripcion", "")

    q = Movimiento.query
    try:
        if desde_raw:
            q = q.filter(Movimiento.fecha >= datetime.strptime(desde_raw, "%Y-%m-%d").date())
    except ValueError:
        desde_raw = ""
    try:
        if hasta_raw:
            q = q.filter(Movimiento.fecha <= datetime.strptime(hasta_raw, "%Y-%m-%d").date())
    except ValueError:
        hasta_raw = ""
    if tipo_raw:
        q = q.filter(Movimiento.tipo == tipo_raw)
    if categoria_raw:
        q = q.filter(Movimiento.categoria == categoria_raw)
    if descripcion_raw:
        q = q.filter(Movimiento.descripcion.ilike(f"%{descripcion_raw}%"))

    movimientos = q.order_by(Movimiento.id.desc()).all()
    return render_template(
        "movimientos.html", movimientos=movimientos,
        desde=desde_raw, hasta=hasta_raw,
        tipo=tipo_raw, categoria=categoria_raw, descripcion=descripcion_raw,
    )


@app.route("/eliminar/<int:id>")
@login_requerido
def eliminar_movimiento(id):
    m = Movimiento.query.get_or_404(id)
    try:
        db.session.delete(m)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return f"Error al eliminar: {str(e)}"
    return redirect(url_for("ver_movimientos"))


@app.route("/editar/<int:id>", methods=["GET", "POST"])
@login_requerido
def editar_movimiento(id):
    m = Movimiento.query.get_or_404(id)
    if request.method == "POST":
        try:
            m.fecha = datetime.strptime(request.form["fecha"], "%Y-%m-%d").date()
            m.tipo = request.form["tipo"]
            m.categoria = request.form["categoria"]
            m.descripcion = request.form["descripcion"]
            m.importe = float(request.form["importe"])
            m.investment_asset_type = request.form.get("investment_asset_type") or None
            m.investment_asset_name = request.form.get("investment_asset_name") or None
            m.pagado_con_tarjeta = bool(request.form.get("pagado_con_tarjeta"))
            db.session.commit()
            return redirect(url_for("ver_movimientos"))
        except Exception as e:
            db.session.rollback()
            return f"Error al guardar: {str(e)}"
    return render_template("editar_movimiento.html", m=m)


@app.route("/crear-tabla")
@login_requerido
def crear_tabla():
    try:
        db.create_all()
        # db.create_all() solo crea tablas nuevas — "movimientos" ya existe con
        # datos, así que la columna nueva se agrega aparte (idempotente).
        db.session.execute(db.text(
            "ALTER TABLE movimientos ADD COLUMN IF NOT EXISTS pagado_con_tarjeta "
            "BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        db.session.commit()
        return "Tabla creada correctamente"
    except Exception as e:
        db.session.rollback()
        return f"Error: {str(e)}"


@app.route("/test-db")
@login_requerido
def test_db():
    try:
        db.session.execute(db.text("SELECT 1"))
        return "Conexión OK"
    except Exception as e:
        return f"Error: {str(e)}"


# ── API endpoints ─────────────────────────────────────────────────────

@app.route("/api/resumen")
@login_requerido
def api_resumen():
    desde, hasta = parse_dates(request)
    movs = query_movs(desde, hasta)
    ing  = sum(float(m.importe) for m in movs if m.tipo == "Ingreso")
    gast = sum(float(m.importe) for m in movs if m.tipo == "Gasto")
    cat_map = defaultdict(float)
    for m in movs:
        if m.tipo == "Gasto":
            cat_map[m.categoria] += float(m.importe)
    return jsonify({
        "kpis": {
            "total_ingresos": round(ing, 2),
            "total_gastos":   round(gast, 2),
            "balance":        round(ing - gast, 2),
        },
        "gastos_por_categoria": [
            {"categoria": c, "total": round(t, 2)}
            for c, t in sorted(cat_map.items(), key=lambda x: -x[1])
        ],
        "por_mes": agrupar_mensual(movs, desde, hasta),
    })


@app.route("/api/colchon")
@login_requerido
def api_colchon():
    desde, hasta = parse_dates(request)
    movs = query_movs(desde, hasta, categoria="Colchón")
    ing  = sum(float(m.importe) for m in movs if m.tipo == "Ingreso")
    gast = sum(float(m.importe) for m in movs if m.tipo == "Gasto")
    por_mes = agrupar_mensual(movs, desde, hasta)
    acum, evol = 0.0, []
    for item in por_mes:
        acum += item["ingresos"] - item["gastos"]
        evol.append({"mes": item["mes"], "acumulado": round(acum, 2)})

    # Saldo actual: todo el historial de Colchón, sin importar el filtro de período.
    movs_todos = Movimiento.query.filter(Movimiento.categoria == "Colchón").all()
    saldo_actual = round(
        sum(float(m.importe) for m in movs_todos if m.tipo == "Ingreso") -
        sum(float(m.importe) for m in movs_todos if m.tipo == "Gasto"), 2
    )

    return jsonify({
        "kpis": {
            "neto": round(ing - gast, 2), "total_periodo": round(ing + gast, 2),
            "num_movimientos": len(movs), "saldo_actual": saldo_actual,
        },
        "por_mes": por_mes, "evolucion": evol,
        "top_items": top_items(movs),
    })


@app.route("/api/necesidades")
@login_requerido
def api_necesidades():
    desde, hasta = parse_dates(request)
    movs = query_movs(desde, hasta, categoria="Necesidades")
    movs_gasto = [m for m in movs if m.tipo == "Gasto"]
    total = sum(float(m.importe) for m in movs_gasto)

    # Tendencia mensual: ingresos, gastos y meta configurada, mes por mes —
    # incluye el mes en curso aunque esté incompleto, la meta debe verse igual.
    bucket = defaultdict(lambda: {"ingresos": 0.0, "gastos": 0.0})
    for m in movs:
        bucket[(m.fecha.year, m.fecha.month)]["ingresos" if m.tipo == "Ingreso" else "gastos"] += float(m.importe)

    tendencia = []
    y, mo = desde.year, desde.month
    while (y, mo) <= (hasta.year, hasta.month):
        v = bucket.get((y, mo), {"ingresos": 0.0, "gastos": 0.0})
        tendencia.append({
            "mes": date_type(y, mo, 1).strftime("%b %Y"),
            "ingresos": round(v["ingresos"], 2),
            "gastos": round(v["gastos"], 2),
            "meta": get_meta_necesidades_mes(y, mo),
        })
        mo += 1
        if mo > 12:
            mo = 1
            y += 1

    meses = len(tendencia)

    # Saldo disponible: todo el historial de Necesidades, sin importar el filtro de período.
    movs_todos = Movimiento.query.filter(Movimiento.categoria == "Necesidades").all()
    saldo_disponible = round(
        sum(float(m.importe) for m in movs_todos if m.tipo == "Ingreso") -
        sum(float(m.importe) for m in movs_todos if m.tipo == "Gasto"), 2
    )

    return jsonify({
        "kpis": {
            "total_periodo": round(total, 2),
            "promedio_mensual": round(total / meses, 2) if meses else 0,
            "num_transacciones": len(movs_gasto),
            "saldo_disponible": saldo_disponible,
        },
        "top_items": top_items(movs_gasto),
        "tendencia_mensual": tendencia,
    })


@app.route("/api/necesidades/config", methods=["GET", "POST"])
@login_requerido
def api_necesidades_config():
    hoy = hoy_local()

    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        try:
            year  = int(data.get("year", hoy.year))
            month = int(data.get("month", hoy.month))
            monto = float(data["monto_meta"])
            if not (1 <= month <= 12):
                return jsonify({"error": "Mes inválido"}), 400
            if monto <= 0:
                return jsonify({"error": "Ingresa un monto mayor a 0"}), 400
            set_meta_necesidades_mes(year, month, monto)
            return jsonify({"ok": True, "year": year, "month": month, "monto_meta": monto})
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    try:
        year  = int(request.args.get("year", hoy.year))
        month = int(request.args.get("month", hoy.month))
        if not (1 <= month <= 12):
            raise ValueError
    except (TypeError, ValueError):
        year, month = hoy.year, hoy.month

    return jsonify({"year": year, "month": month, "monto_meta": get_meta_necesidades_mes(year, month)})


@app.route("/api/necesidades/metas", methods=["GET", "POST"])
@login_requerido
def api_necesidades_metas():
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        try:
            year  = int(data["year"])
            month = int(data["month"])
            monto = float(data["monto_meta"])
            if not (1 <= month <= 12):
                return jsonify({"error": "Mes inválido"}), 400
            if monto <= 0:
                return jsonify({"error": "Ingresa un monto mayor a 0"}), 400
            existing = MetaNecesidadesMes.query.filter_by(year=year, month=month).first()
            if existing:
                return jsonify({"error": "Ya existe una meta para ese mes — edítala en vez de crear otra"}), 400
            set_meta_necesidades_mes(year, month, monto)
            row = MetaNecesidadesMes.query.filter_by(year=year, month=month).first()
            return jsonify({"id": row.id}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    metas = MetaNecesidadesMes.query.order_by(MetaNecesidadesMes.year.desc(), MetaNecesidadesMes.month.desc()).all()
    return jsonify([{
        "id": m.id, "year": m.year, "month": m.month,
        "mes_label": f"{MESES_ES[m.month]} {m.year}",
        "monto_meta": float(m.monto_meta),
    } for m in metas])


@app.route("/api/necesidades/metas/<int:id>", methods=["PUT", "DELETE"])
@login_requerido
def api_necesidades_meta_detail(id):
    m = MetaNecesidadesMes.query.get_or_404(id)

    if request.method == "DELETE":
        db.session.delete(m)
        db.session.commit()
        return jsonify({"ok": True})

    data = request.get_json(force=True, silent=True) or {}
    try:
        year  = int(data["year"])
        month = int(data["month"])
        monto = float(data["monto_meta"])
        if not (1 <= month <= 12):
            return jsonify({"error": "Mes inválido"}), 400
        if monto <= 0:
            return jsonify({"error": "Ingresa un monto mayor a 0"}), 400
        existing = MetaNecesidadesMes.query.filter_by(year=year, month=month).first()
        if existing and existing.id != m.id:
            return jsonify({"error": "Ya existe una meta para ese mes"}), 400
        m.year, m.month, m.monto_meta = year, month, monto
        db.session.commit()
        return jsonify({"ok": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@app.route("/api/diversion")
@login_requerido
def api_diversion():
    desde, hasta = parse_dates(request)
    movs_div = query_movs(desde, hasta, categoria="Diversión")
    movs_div_gasto = [m for m in movs_div if m.tipo == "Gasto"]
    movs_all_gasto = query_movs(desde, hasta, tipo="Gasto")
    total_div  = sum(float(m.importe) for m in movs_div_gasto)
    total_gast = sum(float(m.importe) for m in movs_all_gasto)
    pct = round(total_div / total_gast * 100, 1) if total_gast else 0
    importes = [float(m.importe) for m in movs_div_gasto]

    # Tendencia mensual: ingresos, gastos y meta configurada, mes por mes —
    # incluye el mes en curso aunque esté incompleto, la meta debe verse igual.
    bucket = defaultdict(lambda: {"ingresos": 0.0, "gastos": 0.0})
    for m in movs_div:
        bucket[(m.fecha.year, m.fecha.month)]["ingresos" if m.tipo == "Ingreso" else "gastos"] += float(m.importe)

    tendencia = []
    y, mo = desde.year, desde.month
    while (y, mo) <= (hasta.year, hasta.month):
        v = bucket.get((y, mo), {"ingresos": 0.0, "gastos": 0.0})
        tendencia.append({
            "mes": date_type(y, mo, 1).strftime("%b %Y"),
            "ingresos": round(v["ingresos"], 2),
            "gastos": round(v["gastos"], 2),
            "meta": get_meta_diversion_mes(y, mo),
        })
        mo += 1
        if mo > 12:
            mo = 1
            y += 1

    meses = len(tendencia)

    # Saldo disponible: todo el historial de Diversión, sin importar el filtro de período.
    movs_todos = Movimiento.query.filter(Movimiento.categoria == "Diversión").all()
    saldo_disponible = round(
        sum(float(m.importe) for m in movs_todos if m.tipo == "Ingreso") -
        sum(float(m.importe) for m in movs_todos if m.tipo == "Gasto"), 2
    )

    return jsonify({
        "kpis": {
            "pct_del_total": pct,
            "promedio_mensual": round(total_div / meses, 2) if meses else 0,
            "gasto_max": round(max(importes), 2) if importes else 0,
            "saldo_disponible": saldo_disponible,
        },
        "tendencia_mensual": tendencia,
        "top_items": top_items(movs_div_gasto),
    })


@app.route("/api/diversion/config", methods=["GET", "POST"])
@login_requerido
def api_diversion_config():
    hoy = hoy_local()

    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        try:
            year  = int(data.get("year", hoy.year))
            month = int(data.get("month", hoy.month))
            monto = float(data["monto_meta"])
            if not (1 <= month <= 12):
                return jsonify({"error": "Mes inválido"}), 400
            if monto <= 0:
                return jsonify({"error": "Ingresa un monto mayor a 0"}), 400
            set_meta_diversion_mes(year, month, monto)
            return jsonify({"ok": True, "year": year, "month": month, "monto_meta": monto})
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    try:
        year  = int(request.args.get("year", hoy.year))
        month = int(request.args.get("month", hoy.month))
        if not (1 <= month <= 12):
            raise ValueError
    except (TypeError, ValueError):
        year, month = hoy.year, hoy.month

    return jsonify({"year": year, "month": month, "monto_meta": get_meta_diversion_mes(year, month)})


@app.route("/api/diversion/metas", methods=["GET", "POST"])
@login_requerido
def api_diversion_metas():
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        try:
            year  = int(data["year"])
            month = int(data["month"])
            monto = float(data["monto_meta"])
            if not (1 <= month <= 12):
                return jsonify({"error": "Mes inválido"}), 400
            if monto <= 0:
                return jsonify({"error": "Ingresa un monto mayor a 0"}), 400
            existing = MetaDiversionMes.query.filter_by(year=year, month=month).first()
            if existing:
                return jsonify({"error": "Ya existe una meta para ese mes — edítala en vez de crear otra"}), 400
            set_meta_diversion_mes(year, month, monto)
            row = MetaDiversionMes.query.filter_by(year=year, month=month).first()
            return jsonify({"id": row.id}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    metas = MetaDiversionMes.query.order_by(MetaDiversionMes.year.desc(), MetaDiversionMes.month.desc()).all()
    return jsonify([{
        "id": m.id, "year": m.year, "month": m.month,
        "mes_label": f"{MESES_ES[m.month]} {m.year}",
        "monto_meta": float(m.monto_meta),
    } for m in metas])


@app.route("/api/diversion/metas/<int:id>", methods=["PUT", "DELETE"])
@login_requerido
def api_diversion_meta_detail(id):
    m = MetaDiversionMes.query.get_or_404(id)

    if request.method == "DELETE":
        db.session.delete(m)
        db.session.commit()
        return jsonify({"ok": True})

    data = request.get_json(force=True, silent=True) or {}
    try:
        year  = int(data["year"])
        month = int(data["month"])
        monto = float(data["monto_meta"])
        if not (1 <= month <= 12):
            return jsonify({"error": "Mes inválido"}), 400
        if monto <= 0:
            return jsonify({"error": "Ingresa un monto mayor a 0"}), 400
        existing = MetaDiversionMes.query.filter_by(year=year, month=month).first()
        if existing and existing.id != m.id:
            return jsonify({"error": "Ya existe una meta para ese mes"}), 400
        m.year, m.month, m.monto_meta = year, month, monto
        db.session.commit()
        return jsonify({"ok": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@app.route("/api/inversion")
@login_requerido
def api_inversion():
    desde, hasta = parse_dates(request)
    movs = query_movs(desde, hasta, categoria="Inversión")
    ing  = sum(float(m.importe) for m in movs if m.tipo == "Ingreso")
    gast = sum(float(m.importe) for m in movs if m.tipo == "Gasto")
    por_mes = agrupar_mensual(movs, desde, hasta)
    acum, evol = 0.0, []
    for item in por_mes:
        acum += item["gastos"]
        evol.append({"mes": item["mes"], "acumulado": round(acum, 2)})
    meses_activos = len([m for m in por_mes if m["ingresos"] or m["gastos"]])
    return jsonify({
        "kpis": {"neto": round(ing - gast, 2), "total_periodo": round(ing + gast, 2), "meses_activos": meses_activos},
        "evolucion": evol,
        "aportes_mensuales": [{"mes": i["mes"], "monto": round(i["gastos"], 2)} for i in por_mes],
        "top_items": top_items(movs),
    })


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

    por_mes = agrupar_mensual(movs, desde, hasta)
    por_dia = agrupar_diario(movs, desde, hasta)
    acum, evol = 0.0, []
    for item in por_dia:
        acum += item["ingresos"] - item["gastos"]
        evol.append({"fecha": item["fecha"], "acumulado": round(acum, 2)})

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


_EPOCH = date_type(1970, 1, 1)


def to_epoch_day(d):
    return (d - _EPOCH).days


@app.route("/api/earnings")
@login_requerido
def api_earnings():
    desde, hasta = parse_dates(request)
    movs = query_movs(desde, hasta, categoria="Earnings")
    movs_ingreso = [m for m in movs if m.tipo == "Ingreso"]
    ing  = sum(float(m.importe) for m in movs_ingreso)
    gast = sum(float(m.importe) for m in movs if m.tipo == "Gasto")

    por_fecha = defaultdict(lambda: {"ingresos": 0.0, "gastos": 0.0})
    for m in movs:
        v = float(m.importe)
        por_fecha[m.fecha]["ingresos" if m.tipo == "Ingreso" else "gastos"] += v

    fechas = sorted(por_fecha.keys())
    neto = [round(por_fecha[f]["ingresos"] - por_fecha[f]["gastos"], 2) for f in fechas]
    sma21 = sma(neto, 21)
    sma55 = sma(neto, 55)

    def puntos(valores):
        return [{"x": to_epoch_day(fechas[i]), "y": valores[i]} for i in range(len(fechas))]

    todas_metas = MetaIngreso.query.order_by(MetaIngreso.fecha_inicio).all()

    # Línea de meta: independiente de si hay movimientos registrados o no —
    # se dibuja mientras haya una meta activa que se cruce con el período filtrado.
    meta_linea = []
    prev_fin = None
    for m in todas_metas:
        seg_ini = max(m.fecha_inicio, desde)
        seg_fin = min(m.fecha_fin, hasta)
        if seg_ini > seg_fin:
            continue
        if prev_fin is not None and seg_ini > prev_fin + timedelta(days=1):
            meta_linea.append({"x": to_epoch_day(prev_fin + timedelta(days=1)), "y": None})
        monto = float(m.monto_diario)
        meta_linea.append({"x": to_epoch_day(seg_ini), "y": monto})
        meta_linea.append({"x": to_epoch_day(seg_fin), "y": monto})
        prev_fin = seg_fin

    hoy = hoy_local()
    meta_hoy_activa = None
    for m in todas_metas:
        if m.fecha_inicio <= hoy <= m.fecha_fin:
            if meta_hoy_activa is None or m.fecha_inicio > meta_hoy_activa.fecha_inicio:
                meta_hoy_activa = m
    meta_hoy = float(meta_hoy_activa.monto_diario) if meta_hoy_activa else None

    return jsonify({
        "kpis": {
            "total_ingresos":   round(ing, 2),
            "total_gastos":     round(gast, 2),
            "balance_neto":     round(ing - gast, 2),
            "dias_registrados": len(fechas),
        },
        "barras": {
            "neto":  puntos(neto),
            "sma21": puntos(sma21),
            "sma55": puntos(sma55),
        },
        "meta_linea": meta_linea,
        "meta_hoy": meta_hoy,
        "fuentes": top_items(movs_ingreso),
    })


@app.route("/api/earnings/metas", methods=["GET", "POST"])
@login_requerido
def api_earnings_metas():
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        try:
            fecha_inicio = datetime.strptime(data["fecha_inicio"], "%Y-%m-%d").date()
            fecha_fin    = datetime.strptime(data["fecha_fin"], "%Y-%m-%d").date()
            monto_diario = float(data["monto_diario"])
            if fecha_fin < fecha_inicio:
                return jsonify({"error": "La fecha fin no puede ser anterior a la fecha inicio"}), 400
            if monto_diario <= 0:
                return jsonify({"error": "El monto diario debe ser mayor a 0"}), 400
            m = MetaIngreso(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, monto_diario=monto_diario)
            db.session.add(m)
            db.session.commit()
            return jsonify({"id": m.id}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    metas = MetaIngreso.query.order_by(MetaIngreso.fecha_inicio.desc()).all()
    return jsonify([{
        "id":           m.id,
        "fecha_inicio": m.fecha_inicio.strftime("%Y-%m-%d"),
        "fecha_fin":    m.fecha_fin.strftime("%Y-%m-%d"),
        "monto_diario": float(m.monto_diario),
    } for m in metas])


@app.route("/api/earnings/metas/<int:id>", methods=["PUT", "DELETE"])
@login_requerido
def api_earnings_meta_detail(id):
    m = MetaIngreso.query.get_or_404(id)

    if request.method == "DELETE":
        db.session.delete(m)
        db.session.commit()
        return jsonify({"ok": True})

    data = request.get_json(force=True, silent=True) or {}
    try:
        fecha_inicio = datetime.strptime(data["fecha_inicio"], "%Y-%m-%d").date()
        fecha_fin    = datetime.strptime(data["fecha_fin"], "%Y-%m-%d").date()
        monto_diario = float(data["monto_diario"])
        if fecha_fin < fecha_inicio:
            return jsonify({"error": "La fecha fin no puede ser anterior a la fecha inicio"}), 400
        if monto_diario <= 0:
            return jsonify({"error": "El monto diario debe ser mayor a 0"}), 400
        m.fecha_inicio, m.fecha_fin, m.monto_diario = fecha_inicio, fecha_fin, monto_diario
        db.session.commit()
        return jsonify({"ok": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@app.route("/api/earnings/config", methods=["GET", "POST"])
@login_requerido
def api_earnings_config():
    hoy = hoy_local()

    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        try:
            year  = int(data.get("year", hoy.year))
            month = int(data.get("month", hoy.month))
            n     = int(data["dias_trabajo_mes"])
            if not (1 <= month <= 12):
                return jsonify({"error": "Mes inválido"}), 400
            if n <= 0 or n > 31:
                return jsonify({"error": "Ingresa un número de días entre 1 y 31"}), 400
            set_dias_meta_mes(year, month, n)
            return jsonify({"ok": True, "year": year, "month": month, "dias_trabajo_mes": n})
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

    try:
        year  = int(request.args.get("year", hoy.year))
        month = int(request.args.get("month", hoy.month))
        if not (1 <= month <= 12):
            raise ValueError
    except (TypeError, ValueError):
        year, month = hoy.year, hoy.month

    return jsonify({"year": year, "month": month, "dias_trabajo_mes": get_dias_meta_mes(year, month)})


MESES_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


@app.route("/api/earnings/calendario")
@login_requerido
def api_earnings_calendario():
    hoy = hoy_local()
    try:
        year  = int(request.args.get("year", hoy.year))
        month = int(request.args.get("month", hoy.month))
        if not (1 <= month <= 12):
            raise ValueError
    except (TypeError, ValueError):
        year, month = hoy.year, hoy.month

    primer_dia = date_type(year, month, 1)
    dias_en_mes = calendar.monthrange(year, month)[1]
    ultimo_dia = date_type(year, month, dias_en_mes)
    # Python: Lunes=0..Domingo=6 → convertir a Domingo=0..Sábado=6 (como el calendario nativo)
    primer_dia_semana = (calendar.monthrange(year, month)[0] + 1) % 7

    movs = Movimiento.query.filter(
        Movimiento.categoria == "Earnings",
        Movimiento.tipo == "Ingreso",
        Movimiento.fecha >= primer_dia,
        Movimiento.fecha <= ultimo_dia,
    ).all()
    dias_con_ingreso = sorted({m.fecha.day for m in movs})

    return jsonify({
        "year": year,
        "month": month,
        "mes_label": f"{MESES_ES[month]} de {year}",
        "dias_en_mes": dias_en_mes,
        "primer_dia_semana": primer_dia_semana,
        "dias_con_ingreso": dias_con_ingreso,
        "dias_trabajados": len(dias_con_ingreso),
        "meta_dias_mes": get_dias_meta_mes(year, month),
    })


@app.route("/api/tarjeta")
@login_requerido
def api_tarjeta():
    hoy = hoy_local()
    cargos_movs = Movimiento.query.filter(
        Movimiento.tipo == "Gasto",
        db.or_(Movimiento.pagado_con_tarjeta.is_(True), Movimiento.categoria == "Tarjeta"),
    ).all()

    # Los pagos de tarjeta vienen de dos fuentes: la categoría "Tarjeta" + tipo
    # Ingreso (flujo actual) y la tabla legada PagoTarjeta (del tipo "Pago
    # tarjeta" ya retirado) — se combinan para no perder pagos ya registrados.
    pagos_movs  = Movimiento.query.filter(Movimiento.tipo == "Ingreso", Movimiento.categoria == "Tarjeta").all()
    pagos_viejos = PagoTarjeta.query.all()
    pagos = sorted(
        [{"fecha": p.fecha, "monto": float(p.importe), "nota": p.descripcion, "id": p.id, "origen": "movimiento"} for p in pagos_movs] +
        [{"fecha": p.fecha, "monto": float(p.monto), "nota": p.nota, "id": p.id, "origen": "pago_tarjeta"} for p in pagos_viejos],
        key=lambda p: p["fecha"],
    )

    cargos_por_ciclo = defaultdict(float)
    for m in cargos_movs:
        cargos_por_ciclo[ciclo_de_fecha(m.fecha)] += float(m.importe)

    ciclo_actual_cid = ciclo_de_fecha(hoy)
    cids = set(cargos_por_ciclo.keys())
    cids.add(ciclo_actual_cid)

    ciclos = []
    for cid in sorted(cids):
        inicio, cierre, vencimiento = ciclo_bounds(*cid)
        total_cargos = round(cargos_por_ciclo.get(cid, 0.0), 2)
        ciclos.append({
            "cid": cid, "id": ciclo_id(*cid),
            "inicio": inicio, "cierre": cierre, "vencimiento": vencimiento,
            "total_cargos": total_cargos, "total_pagado": 0.0, "saldo": total_cargos,
        })

    # FIFO: cada pago se aplica al ciclo pendiente más antiguo primero.
    for pago in pagos:
        restante = pago["monto"]
        for c in ciclos:
            if restante <= 0:
                break
            if c["saldo"] > 0:
                aplicado = min(restante, c["saldo"])
                c["saldo"] = round(c["saldo"] - aplicado, 2)
                c["total_pagado"] = round(c["total_pagado"] + aplicado, 2)
                restante -= aplicado

    for c in ciclos:
        if c["saldo"] <= 0.001:
            c["estado"] = "pagado"
        elif c["vencimiento"] < hoy:
            c["estado"] = "vencido"
        else:
            c["estado"] = "pendiente"
        c["inicio"]      = c["inicio"].strftime("%Y-%m-%d")
        c["cierre"]      = c["cierre"].strftime("%Y-%m-%d")
        c["vencimiento"] = c["vencimiento"].strftime("%Y-%m-%d")

    ciclo_actual = next((c for c in ciclos if c["cid"] == ciclo_actual_cid), None)
    for c in ciclos:
        del c["cid"]
    ciclos.sort(key=lambda c: c["inicio"], reverse=True)

    pendientes = [c for c in ciclos if c["saldo"] > 0.001]
    proximo = min(pendientes, key=lambda c: c["vencimiento"]) if pendientes else None

    return jsonify({
        "kpis": {
            "deuda_total": round(sum(c["saldo"] for c in ciclos), 2),
            "proximo_vencimiento": proximo["vencimiento"] if proximo else None,
            "monto_proximo_vencimiento": proximo["saldo"] if proximo else 0,
            "ciclo_actual_total": ciclo_actual["total_cargos"] if ciclo_actual else 0,
        },
        "ciclos": ciclos,
        "pagos": [{
            "id": p["id"],
            "fecha": p["fecha"].strftime("%Y-%m-%d"),
            "monto": round(p["monto"], 2),
            "nota": p["nota"],
            "origen": p["origen"],
        } for p in reversed(pagos)],
    })


@app.route("/api/tarjeta/pagos/<int:id>", methods=["DELETE"])
@login_requerido
def api_tarjeta_pago_delete(id):
    p = PagoTarjeta.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    return jsonify({"ok": True})


# ── Research & Development (R&D) ───────────────────────────────────────
RD_META_INGRESO_MES = 150.0
RD_META_CURSOS_MES = 1
RD_AREAS = ["Enseñanza & Idiomas", "Tecnología e IA", "Negocios & Finanzas", "Desarrollo Creativo"]
RD_SUBAREAS = {
    "Enseñanza & Idiomas": ["Certificaciones (TEFL/TESOL/TKT/CELTA)", "Metodología & Didáctica", "Material Didáctico"],
    "Tecnología e IA": ["IA Generativa & Prompting", "Herramientas Digitales", "Automatización"],
    "Negocios & Finanzas": ["Finanzas Personales e Inversión", "Emprendimiento", "Marketing Educativo"],
    "Desarrollo Creativo": ["Teoría Musical & Instrumento", "Producción & Audio"],
}


@app.route("/api/rd")
@login_requerido
def api_rd():
    hoy = hoy_local()
    movs = Movimiento.query.filter(Movimiento.categoria == "R&D").order_by(Movimiento.fecha).all()
    ingresos = [m for m in movs if m.tipo == "Ingreso"]
    gastos   = [m for m in movs if m.tipo == "Gasto"]

    flujo_mes  = sum(float(m.importe) for m in ingresos if m.fecha.year == hoy.year and m.fecha.month == hoy.month)
    cursos_mes = sum(1 for m in gastos if m.fecha.year == hoy.year and m.fecha.month == hoy.month)
    fondo = round(sum(float(m.importe) for m in ingresos) - sum(float(m.importe) for m in gastos), 2)

    # Cumplimiento mensual: últimos 12 meses (ventana móvil, terminando en el mes actual)
    ventana = []
    y, m = hoy.year, hoy.month
    for _ in range(12):
        ventana.append((y, m))
        y, m = _add_months(y, m, -1)
    ventana.reverse()

    ingresos_por_mes = defaultdict(float)
    cursos_por_mes = defaultdict(int)
    for mv in ingresos:
        ingresos_por_mes[(mv.fecha.year, mv.fecha.month)] += float(mv.importe)
    for mv in gastos:
        cursos_por_mes[(mv.fecha.year, mv.fecha.month)] += 1

    cumplimiento_mensual = {
        "meses": [f"{MESES_ES[mm][:3]} {yy}" for yy, mm in ventana],
        "ingresos": [round(ingresos_por_mes.get(k, 0.0), 2) for k in ventana],
        "meta": RD_META_INGRESO_MES,
        "curso_comprado": [cursos_por_mes.get(k, 0) >= RD_META_CURSOS_MES for k in ventana],
    }

    # Flujo del fondo: saldo acumulado en el instante exacto de cada transacción
    flujo_fondo = []
    saldo = 0.0
    for mv in movs:
        delta = float(mv.importe) if mv.tipo == "Ingreso" else -float(mv.importe)
        saldo = round(saldo + delta, 2)
        flujo_fondo.append({
            "x": to_epoch_day(mv.fecha), "y": saldo,
            "fecha": mv.fecha.strftime("%Y-%m-%d"), "tipo": mv.tipo, "monto": float(mv.importe),
        })

    por_area = defaultdict(float)
    for mv in gastos:
        area = mv.investment_asset_type or "Sin clasificar"
        por_area[area] += float(mv.importe)
    por_area_list = [{"label": k, "value": round(v, 2)} for k, v in sorted(por_area.items(), key=lambda x: -x[1])]

    return jsonify({
        "kpis": {
            "flujo_mes_actual": round(flujo_mes, 2),
            "meta_flujo_mensual": RD_META_INGRESO_MES,
            "pct_flujo": round(flujo_mes / RD_META_INGRESO_MES * 100) if RD_META_INGRESO_MES else 0,
            "cursos_mes_actual": cursos_mes,
            "meta_cursos_mensual": RD_META_CURSOS_MES,
            "pct_cursos": round(cursos_mes / RD_META_CURSOS_MES * 100) if RD_META_CURSOS_MES else 0,
            "fondo_disponible": fondo,
        },
        "cumplimiento_mensual": cumplimiento_mensual,
        "flujo_fondo": flujo_fondo,
        "por_area": por_area_list,
    })


@app.route("/inversiones")
@login_requerido
def inversiones_portfolio():
    return render_template("inversiones.html", active_tab="portafolio")


@app.route("/api/inversiones")
@login_requerido
def api_inversiones():
    desde, hasta = parse_dates(request)
    cat_tipo = request.args.get("categoria", "ETFs")
    movs = Movimiento.query.filter(
        Movimiento.fecha >= desde,
        Movimiento.fecha <= hasta,
        Movimiento.categoria == "Inversión",
        Movimiento.tipo == "Gasto",
        Movimiento.investment_asset_type == cat_tipo
    ).order_by(Movimiento.fecha).all()

    total = sum(float(m.importe) for m in movs)

    by_asset = defaultdict(float)
    for m in movs:
        key = m.investment_asset_name or "Sin especificar"
        by_asset[key] += float(m.importe)

    por_mes = agrupar_mensual(movs, desde, hasta)
    acum, evol = 0.0, []
    for item in por_mes:
        acum += item["gastos"]
        evol.append({"mes": item["mes"], "acumulado": round(acum, 2)})

    tabla = [{
        "fecha": m.fecha.strftime("%Y-%m-%d"),
        "activo": m.investment_asset_name or "—",
        "monto": float(m.importe),
        "notas": m.descripcion,
    } for m in reversed(movs)]

    by_asset_list = [{"label": k, "value": round(v, 2)}
                     for k, v in sorted(by_asset.items(), key=lambda x: -x[1])]

    return jsonify({
        "total":    round(total, 2),
        "num_ops":  len(movs),
        "by_asset": by_asset_list if by_asset_list else [{"label": "Sin datos", "value": 1}],
        "evolucion": evol,
        "tabla":    tabla,
    })


_tc_cache = {"rate": None, "ts": 0}

@app.route("/api/tipo-cambio")
@login_requerido
def api_tipo_cambio():
    now = time.time()
    if _tc_cache["rate"] and now - _tc_cache["ts"] < 3600:
        return jsonify({"rate": _tc_cache["rate"]})
    apis = [
        ("https://api.frankfurter.app/latest?from=USD&to=PEN", lambda d: d["rates"]["PEN"]),
        ("https://open.er-api.com/v6/latest/USD",              lambda d: d["rates"]["PEN"]),
    ]
    for url, extractor in apis:
        try:
            resp = http_requests.get(url, timeout=5)
            rate = extractor(resp.json())
            _tc_cache["rate"] = rate
            _tc_cache["ts"]   = now
            return jsonify({"rate": rate})
        except Exception:
            continue
    return jsonify({"error": "no disponible"}), 503


if __name__ == "__main__":
    app.run(debug=True)
