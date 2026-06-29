from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from config import Config
from datetime import datetime, date as date_type
from functools import wraps
from collections import defaultdict
import os

app = Flask(__name__)
app.config.from_object(Config)

USUARIO_ADMIN = os.getenv("APP_USER")
PASSWORD_ADMIN = os.getenv("APP_PASSWORD")

db = SQLAlchemy(app)


def login_requerido(f):
    @wraps(f)
    def funcion_protegida(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return funcion_protegida


class Movimiento(db.Model):
    __tablename__ = "movimientos"
    id          = db.Column(db.Integer, primary_key=True)
    fecha       = db.Column(db.Date, nullable=False)
    tipo        = db.Column(db.String(20), nullable=False)
    categoria   = db.Column(db.String(30), nullable=False)
    descripcion = db.Column(db.String(255), nullable=False)
    importe     = db.Column(db.Numeric(10, 2), nullable=False)


# ── helpers ──────────────────────────────────────────────────────────

def parse_dates(req):
    def _p(s, fallback):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date() if s else fallback
        except ValueError:
            return fallback
    return (
        _p(req.args.get("desde", ""), date_type(2000, 1, 1)),
        _p(req.args.get("hasta", ""), date_type.today()),
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


def agrupar_mensual(movs):
    bucket = defaultdict(lambda: {"ingresos": 0.0, "gastos": 0.0})
    for m in movs:
        key = m.fecha.strftime("%b %Y")
        v = float(m.importe)
        bucket[key]["ingresos" if m.tipo == "Ingreso" else "gastos"] += v
    def _sk(k):
        return datetime.strptime(k, "%b %Y")
    return [{"mes": k, **v} for k, v in sorted(bucket.items(), key=lambda x: _sk(x[0]))]


def top_items(movs, n=8):
    bucket = defaultdict(float)
    for m in movs:
        bucket[m.descripcion] += float(m.importe)
    return [{"label": k, "value": round(v, 2)}
            for k, v in sorted(bucket.items(), key=lambda x: -x[1])[:n]]


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


@app.route("/nuevo", methods=["GET", "POST"])
@login_requerido
def nuevo():
    if request.method == "POST":
        try:
            m = Movimiento(
                fecha=datetime.strptime(request.form["fecha"], "%Y-%m-%d").date(),
                tipo=request.form["tipo"],
                categoria=request.form["categoria"],
                descripcion=request.form["descripcion"],
                importe=float(request.form["importe"])
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
    movimientos = Movimiento.query.order_by(Movimiento.id.desc()).all()
    return render_template("movimientos.html", movimientos=movimientos)


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


@app.route("/crear-tabla")
@login_requerido
def crear_tabla():
    try:
        db.create_all()
        return "Tabla creada correctamente"
    except Exception as e:
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
        "por_mes": agrupar_mensual(movs),
    })


@app.route("/api/colchon")
@login_requerido
def api_colchon():
    desde, hasta = parse_dates(request)
    movs = query_movs(desde, hasta, categoria="Colchón")
    ing  = sum(float(m.importe) for m in movs if m.tipo == "Ingreso")
    gast = sum(float(m.importe) for m in movs if m.tipo == "Gasto")
    por_mes = agrupar_mensual(movs)
    acum, evol = 0.0, []
    for item in por_mes:
        acum += item["ingresos"] - item["gastos"]
        evol.append({"mes": item["mes"], "acumulado": round(acum, 2)})
    return jsonify({
        "kpis": {"neto": round(ing - gast, 2), "total_periodo": round(ing + gast, 2), "num_movimientos": len(movs)},
        "por_mes": por_mes, "evolucion": evol,
        "top_items": top_items(movs),
    })


@app.route("/api/necesidades")
@login_requerido
def api_necesidades():
    desde, hasta = parse_dates(request)
    movs = query_movs(desde, hasta, categoria="Necesidades", tipo="Gasto")
    total = sum(float(m.importe) for m in movs)
    por_mes = agrupar_mensual(movs)
    meses = len(por_mes)
    return jsonify({
        "kpis": {
            "total_periodo": round(total, 2),
            "promedio_mensual": round(total / meses, 2) if meses else 0,
            "num_transacciones": len(movs),
        },
        "top_items": top_items(movs),
        "tendencia_mensual": [{"mes": i["mes"], "total": round(i["gastos"], 2)} for i in por_mes],
    })


@app.route("/api/diversion")
@login_requerido
def api_diversion():
    desde, hasta = parse_dates(request)
    movs_div = query_movs(desde, hasta, categoria="Diversión", tipo="Gasto")
    movs_all = query_movs(desde, hasta, tipo="Gasto")
    total_div  = sum(float(m.importe) for m in movs_div)
    total_gast = sum(float(m.importe) for m in movs_all)
    pct = round(total_div / total_gast * 100, 1) if total_gast else 0
    por_mes = agrupar_mensual(movs_div)
    meses = len(por_mes)
    importes = [float(m.importe) for m in movs_div]
    return jsonify({
        "kpis": {
            "total_periodo": round(total_div, 2),
            "pct_del_total": pct,
            "promedio_mensual": round(total_div / meses, 2) if meses else 0,
            "gasto_max": round(max(importes), 2) if importes else 0,
        },
        "por_mes": [{"mes": i["mes"], "total": round(i["gastos"], 2)} for i in por_mes],
        "top_items": top_items(movs_div),
    })


@app.route("/api/inversion")
@login_requerido
def api_inversion():
    desde, hasta = parse_dates(request)
    movs = query_movs(desde, hasta, categoria="Inversión")
    ing  = sum(float(m.importe) for m in movs if m.tipo == "Ingreso")
    gast = sum(float(m.importe) for m in movs if m.tipo == "Gasto")
    por_mes = agrupar_mensual(movs)
    acum, evol = 0.0, []
    for item in por_mes:
        acum += item["gastos"]
        evol.append({"mes": item["mes"], "acumulado": round(acum, 2)})
    return jsonify({
        "kpis": {"neto": round(ing - gast, 2), "total_periodo": round(ing + gast, 2), "meses_activos": len(por_mes)},
        "evolucion": evol,
        "aportes_mensuales": [{"mes": i["mes"], "monto": round(i["gastos"], 2)} for i in por_mes],
        "top_items": top_items(movs),
    })


if __name__ == "__main__":
    app.run(debug=True)
