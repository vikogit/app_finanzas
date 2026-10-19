import os
from dotenv import load_dotenv

load_dotenv()

def _url_con_driver(url):
    """Fija el driver de Postgres de forma explícita.

    SQLAlchemy 2.1 elige psycopg (v3) para "postgresql://", pero requirements.txt
    instala psycopg2-binary. En Render (que instala SQLAlchemy 2.1) eso hacía
    fallar el arranque con ModuleNotFoundError. Con el driver escrito en la URL
    el resultado no depende de la versión de SQLAlchemy que se instale.
    """
    for prefijo in ("postgres://", "postgresql://"):
        if url and url.startswith(prefijo):
            return "postgresql+psycopg2://" + url[len(prefijo):]
    return url


class Config:
    SQLALCHEMY_DATABASE_URI = _url_con_driver(os.getenv("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY")