"""
Copia aniriame.db (SQLite) a Postgres (Supabase). Se corre una sola vez.
Lee DATABASE_URL del archivo .env. Requiere que schema.sql ya este aplicado.
Se niega a correr si las tablas de destino ya tienen datos.

    python migrar_a_postgres.py
"""
import os
import sqlite3
import sys

import psycopg
from dotenv import load_dotenv

AQUI = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(AQUI, ".env"))
URL = os.environ.get("DATABASE_URL")
if not URL:
    sys.exit("Falta DATABASE_URL en .env")

# (tabla, columnas, tiene identidad). Orden respeta las llaves foraneas.
TABLAS = [
    ("entradas", ["id_registro", "palabra_raramuri", "homonimo", "clase", "traduccion",
                  "ejemplos_y_comentarios", "variantes", "fuente", "pagina_inicio", "pagina_fin",
                  "estado_validacion", "es_nota"], False),
    ("significados", ["id", "id_registro", "significado_es", "significado_norm"], True),
    ("pares_traduccion", ["id", "tipo", "texto_es", "texto_es_norm", "texto_rar", "origen", "documento",
                          "area", "estado", "par_original_id", "validado_por", "fecha"], True),
    ("revisiones", ["id", "par_id", "estrellas", "correccion", "revisor", "fecha"], True),
    ("metadatos", ["clave", "valor"], False),
]

lite = sqlite3.connect(os.path.join(AQUI, "aniriame.db"))
lite.text_factory = lambda b: b.decode("utf-8", errors="replace")

with psycopg.connect(URL, prepare_threshold=None) as pg:
    with pg.cursor() as cur:
        for t, _, _ in TABLAS:
            cur.execute(f"select count(*) from public.{t}")
            if cur.fetchone()[0]:
                sys.exit(f"La tabla {t} ya tiene datos. No se copia nada.")

        # pares_traduccion se autorreferencia: se insertan en orden de id, y la FK se difiere
        cur.execute("set constraints all deferred")
        for t, cols, ident in TABLAS:
            orden = "order by id" if "id" in cols else ""
            filas = lite.execute(f"select {', '.join(cols)} from {t} {orden}").fetchall()
            ph = ", ".join(["%s"] * len(cols))
            over = "overriding system value " if ident else ""
            cur.executemany(
                f"insert into public.{t} ({', '.join(cols)}) {over}values ({ph})", filas)
            print(f"{t}: {len(filas)} filas copiadas")
            if ident:
                cur.execute(
                    f"select setval(pg_get_serial_sequence('public.{t}', 'id'), "
                    f"coalesce((select max(id) from public.{t}), 1), "
                    f"(select count(*) > 0 from public.{t}))")

        print("\nVerificacion (SQLite -> Postgres):")
        ok = True
        for t, _, _ in TABLAS:
            n_lite = lite.execute(f"select count(*) from {t}").fetchone()[0]
            cur.execute(f"select count(*) from public.{t}")
            n_pg = cur.fetchone()[0]
            ok &= n_lite == n_pg
            print(f"  {t}: {n_lite} -> {n_pg} {'OK' if n_lite == n_pg else 'DIFERENTE'}")
        if not ok:
            raise SystemExit("Los conteos no coinciden; se revierte todo.")
    pg.commit()
print("\nListo.")
