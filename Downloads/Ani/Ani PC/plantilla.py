"""
Plantilla de Excel y CSV para cargar pares de traducción en bloque, y lectura del Excel lleno.

La plantilla tiene dos columnas con nombres fijos (texto_es y texto_rar), un par por fila
(un párrafo o una oración). La fila 1 está protegida para evitar que se cambien los nombres.
"""
import csv
import io

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side

MAX_PARES = 500
ENCABEZADOS = ("texto_es", "texto_rar")
EJEMPLO_ES = "EJEMPLO (borra esta fila): Se abre el registro de aspirantes."
EJEMPLO_RAR = "EJEMPLO (borra esta fila): aquí va la traducción al rarámuri."


class ErrorPlantilla(Exception):
    """Un problema con el archivo, con un mensaje que se le puede mostrar a la persona usuaria."""


def csv_ejemplo():
    s = io.StringIO()
    w = csv.writer(s, lineterminator="\r\n")
    w.writerow(ENCABEZADOS)
    w.writerow([EJEMPLO_ES, EJEMPLO_RAR])
    return s.getvalue()


INSTRUCCIONES = [
    ("title", "Cómo llenar esta plantilla"),
    ("p", "1. Escribe cada par en una fila: el texto en español en la columna A (texto_es) y su traducción al rarámuri en la columna B (texto_rar)."),
    ("p", "2. Un par por fila: un párrafo o una oración. No juntes varios párrafos en una celda ni dividas uno en varias filas."),
    ("p", "3. No cambies, muevas ni borres los nombres de la fila 1 (texto_es y texto_rar). El sistema los necesita para leer el archivo."),
    ("p", "4. Llena las dos columnas de cada fila. Si falta una, esa fila se omite y la página te avisa."),
    ("p", "5. Escribe la traducción tal como la validó la persona hablante. No uses borradores sin revisar."),
    ("p", "6. Máximo 500 pares por archivo. Si tienes más, divídelos en varios archivos."),
    ("p", "7. Para borrar un par, borra el contenido de sus dos celdas."),
    ("p", "8. Guarda el archivo como Excel (.xlsx) y súbelo en la pestaña Entrenar de la página, con el botón \"Cargar Excel o CSV\". Antes de guardar en la base verás una ventana de confirmación."),
    ("title", "Ejemplo de cómo se llena (no copies esta fila)"),
    ("p", "texto_es: Se abre el registro de aspirantes."),
    ("p", "texto_rar: (aquí va la traducción al rarámuri, ya revisada)"),
]


def plantilla_xlsx():
    wb = Workbook()
    ws = wb.active
    ws.title = "Pares"
    arena = PatternFill("solid", fgColor="E9D5A6")
    gris = PatternFill("solid", fgColor="EEEEEE")
    lado = Side(style="thin", color="999999")
    borde = Border(left=lado, right=lado, top=lado, bottom=lado)

    for col, nombre in enumerate(ENCABEZADOS, start=1):
        c = ws.cell(row=1, column=col, value=nombre)
        c.font, c.fill, c.border = Font(bold=True, size=12), arena, borde
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.column_dimensions["A"].width = 60
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 3
    ws.column_dimensions["D"].width = 50

    notas = ["INSTRUCCIONES (no borrar)", "• Un par por fila: un párrafo o una oración.",
             "• No cambies los nombres de la fila 1.", "• Llena las dos columnas en cada fila.",
             "• Máximo 500 pares por archivo.", "• Más detalles en la hoja Instrucciones."]
    for i, t in enumerate(notas, start=1):
        c = ws.cell(row=i, column=4, value=t)
        c.fill, c.font = gris, Font(bold=(i == 1), color="444444")
        c.alignment = Alignment(wrap_text=True, vertical="top")

    for fila in range(2, MAX_PARES + 2):  # filas libres para escribir
        for col in (1, 2):
            c = ws.cell(row=fila, column=col)
            c.protection = Protection(locked=False)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.border = borde
    ws.freeze_panes = "A2"
    ws.protection.sheet = True  # protege la fila 1 y las notas; sin contraseña
    ws.protection.formatColumns = False
    ws.protection.formatRows = False

    ins = wb.create_sheet("Instrucciones")
    ins.column_dimensions["A"].width = 110
    for i, (tipo, texto) in enumerate(INSTRUCCIONES, start=1):
        c = ins.cell(row=i, column=1, value=texto)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if tipo == "title":
            c.font = Font(bold=True, size=13)

    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _texto(fila, i):
    v = fila[i] if i < len(fila) else None
    return "" if v is None else str(v).strip()


def leer_pares_xlsx(datos):
    """Lee un Excel lleno con la plantilla. Devuelve (pares, avisos)."""
    try:
        wb = load_workbook(io.BytesIO(datos), read_only=True, data_only=True)
    except Exception:
        raise ErrorPlantilla("No se pudo abrir el archivo. Debe ser un Excel .xlsx que no esté dañado.")
    ws = wb["Pares"] if "Pares" in wb.sheetnames else wb.worksheets[0]
    filas = ws.iter_rows(values_only=True)
    cab = next(filas, None) or ()
    nombres = [("" if x is None else str(x).strip().lower()) for x in cab]
    if "texto_es" not in nombres or "texto_rar" not in nombres:
        raise ErrorPlantilla("No encuentro las columnas texto_es y texto_rar en la primera fila. "
                             "No cambies los nombres de la plantilla.")
    ies, irar = nombres.index("texto_es"), nombres.index("texto_rar")
    pares, incompletas = [], []
    for n, fila in enumerate(filas, start=2):
        es, rar = _texto(fila, ies), _texto(fila, irar)
        if not es and not rar:
            continue
        if es.upper().startswith("EJEMPLO"):
            continue
        if not es or not rar:
            incompletas.append(n)
            continue
        pares.append({"texto_es": es, "texto_rar": rar, "documento": None, "area": None})
        if len(pares) > MAX_PARES:
            raise ErrorPlantilla(f"El archivo tiene más de {MAX_PARES} pares. Divídelo en partes.")
    wb.close()
    avisos = []
    if incompletas:
        lista = ", ".join(str(n) for n in incompletas[:20]) + ("…" if len(incompletas) > 20 else "")
        avisos.append(f"Se omitieron filas incompletas (les falta el español o el rarámuri): {lista}.")
    return pares, avisos
