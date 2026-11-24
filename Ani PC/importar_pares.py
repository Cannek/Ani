"""
Carga documentos ya traducidos a la base de datos.

Uso:
    python importar_pares.py documentos.csv --validado-por "Nombre de la persona" --estado validado

El CSV debe tener las columnas de plantilla_pares.csv:
    texto_es, texto_rar, tipo, documento, area
"""
import argparse

import aniriame_db as db

parser = argparse.ArgumentParser()
parser.add_argument("csv")
parser.add_argument("--origen", default="institucional")
parser.add_argument("--estado", default="pendiente", help="pendiente o validado")
parser.add_argument("--validado-por", default=None)
args = parser.parse_args()

con = db.conectar()
n = db.importar_pares_csv(con, args.csv, origen=args.origen, estado=args.estado,
                          validado_por=args.validado_por)
print(f"Se cargaron {n} pares.")
