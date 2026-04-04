from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from config import Config
from datetime import datetime
from functools import wraps
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

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    categoria = db.Column(db.String(30), nullable=False)
    descripcion = db.Column(db.String(255), nullable=False)
    importe = db.Column(db.Numeric(10, 2), nullable=False)


@app.route("/", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        usuario = request.form["usuario"]
        password = request.form["password"]

        if usuario == USUARIO_ADMIN and password == PASSWORD_ADMIN:
            session["usuario"] = usuario
            return redirect(url_for("dashboard"))
        else:
            error = "Usuario o contraseña incorrectos"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_requerido
def dashboard():
    movimientos = Movimiento.query.all()

    total_ingresos = sum(float(m.importe) for m in movimientos if m.tipo == "Ingreso")
    total_gastos = sum(float(m.importe) for m in movimientos if m.tipo == "Gasto")
    balance = total_ingresos - total_gastos

    return render_template(
        "dashboard.html",
        total_ingresos=total_ingresos,
        total_gastos=total_gastos,
        balance=balance
    )


@app.route("/nuevo", methods=["GET", "POST"])
@login_requerido
def nuevo():
    if request.method == "POST":
        fecha = request.form["fecha"]
        tipo = request.form["tipo"]
        categoria = request.form["categoria"]
        descripcion = request.form["descripcion"]
        importe = request.form["importe"]

        try:
            nuevo_movimiento = Movimiento(
                fecha=datetime.strptime(fecha, "%Y-%m-%d").date(),
                tipo=tipo,
                categoria=categoria,
                descripcion=descripcion,
                importe=float(importe)
            )

            db.session.add(nuevo_movimiento)
            db.session.commit()

            return "Movimiento guardado correctamente en la base de datos ✅"

        except Exception as e:
            db.session.rollback()
            return f"Error al guardar: {str(e)}"

    return render_template("nuevo_movimiento.html")


@app.route("/movimientos")
@login_requerido
def ver_movimientos():
    movimientos = Movimiento.query.order_by(Movimiento.id.desc()).all()
    return render_template("movimientos.html", movimientos=movimientos)


@app.route("/crear-tabla")
@login_requerido
def crear_tabla():
    try:
        db.create_all()
        return "Tabla movimientos creada correctamente ✅"
    except Exception as e:
        return f"Error al crear la tabla: {str(e)}"


@app.route("/test-db")
@login_requerido
def test_db():
    try:
        db.session.execute(db.text("SELECT 1"))
        return "Conexión a Supabase OK 🚀"
    except Exception as e:
        return f"Error: {str(e)}"


@app.route("/eliminar/<int:id>")
@login_requerido
def eliminar_movimiento(id):
    movimiento = Movimiento.query.get_or_404(id)

    try:
        db.session.delete(movimiento)
        db.session.commit()
        return redirect(url_for("ver_movimientos"))
    except Exception as e:
        db.session.rollback()
        return f"Error al eliminar: {str(e)}"


if __name__ == "__main__":
    app.run(debug=True)