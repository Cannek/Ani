"""
Extracción de texto de archivos PDF, Word (.docx) y .txt, para traducirlos por párrafos.

Limitaciones conocidas:
- PDF escaneados (solo imagen) no tienen texto: necesitarían OCR, que aún no está.
- En los PDF, los párrafos se reconstruyen con una regla sencilla y pueden quedar unidos o
  cortados de forma imperfecta; por eso la página deja revisar y editar el texto antes de traducir.
- En Word se toma el cuerpo y las tablas; no los encabezados, pies de página ni cuadros de texto.
"""
import io
import re


class ErrorExtraccion(Exception):
    """Un problema con el archivo, con un mensaje que se le puede mostrar a la persona usuaria."""


def extraer(nombre, datos):
    """Devuelve (texto, avisos). Los párrafos quedan separados por una línea en blanco."""
    ext = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    if ext == "pdf":
        return _pdf(datos)
    if ext == "docx":
        return _docx(datos)
    if ext == "txt":
        return _txt(datos)
    raise ErrorExtraccion("Formato no compatible. Usa PDF, Word (.docx) o .txt. "
                          "Los Word antiguos (.doc) hay que guardarlos primero como .docx.")


def _txt(datos):
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            return datos.decode(codificacion).strip(), []
        except UnicodeDecodeError:
            continue
    raise ErrorExtraccion("No se pudo leer el archivo de texto.")


def _docx(datos):
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        doc = Document(io.BytesIO(datos))
    except ImportError:
        raise ErrorExtraccion("Falta instalar python-docx: python -m pip install -r requirements.txt")
    except Exception:
        raise ErrorExtraccion("No se pudo leer el archivo Word. Debe ser .docx y no estar dañado.")
    bloques = []
    for el in doc.element.body.iterchildren():
        if el.tag.endswith("}p"):
            t = Paragraph(el, doc).text.strip()
            if t:
                bloques.append(t)
        elif el.tag.endswith("}tbl"):
            for fila in Table(el, doc).rows:
                vistas, celdas = set(), []
                for c in fila.cells:
                    if id(c._tc) in vistas:  # celdas combinadas se repiten
                        continue
                    vistas.add(id(c._tc))
                    if c.text.strip():
                        celdas.append(c.text.strip().replace("\n", " "))
                if celdas:
                    bloques.append(" | ".join(celdas))
    avisos = ["Se tomó el cuerpo del documento y sus tablas; no se incluyen encabezados, "
              "pies de página ni cuadros de texto."]
    if not bloques:
        avisos.append("No se encontró texto en el documento.")
    return "\n\n".join(bloques), avisos


def _unir(lineas):
    t = ""
    for linea in lineas:
        if t.endswith("-") and linea[:1].islower():  # palabra cortada con guion al final de línea
            t = t[:-1] + linea
        else:
            t = (t + " " + linea).strip()
    return t


def _parrafos_de_pagina(texto):
    lineas = [l.strip() for l in texto.splitlines()]
    anchos = [len(l) for l in lineas if l]
    if not anchos:
        return []
    ancho_max = max(anchos)
    parrafos, actual = [], []
    for l in lineas:
        if not l or re.fullmatch(r"\d{1,3}", l):  # línea vacía o número de página
            if actual:
                parrafos.append(_unir(actual))
                actual = []
            continue
        actual.append(l)
        # una línea corta que termina en puntuación suele cerrar un párrafo
        if len(l) < 0.6 * ancho_max and re.search(r"[.!?:;]$", l):
            parrafos.append(_unir(actual))
            actual = []
    if actual:
        parrafos.append(_unir(actual))
    return parrafos


def _pdf(datos):
    try:
        from pypdf import PdfReader
        lector = PdfReader(io.BytesIO(datos))
        if lector.is_encrypted and not lector.decrypt(""):
            raise ErrorExtraccion("El PDF está protegido con contraseña.")
        paginas = [(p.extract_text() or "") for p in lector.pages]
    except ErrorExtraccion:
        raise
    except ImportError:
        raise ErrorExtraccion("Falta instalar pypdf: python -m pip install -r requirements.txt")
    except Exception:
        raise ErrorExtraccion("No se pudo leer el PDF. Puede estar dañado o protegido.")
    caracteres = sum(len(p.strip()) for p in paginas)
    if caracteres < 30 * max(1, len(paginas)):
        return "", ["Este PDF parece escaneado (solo imágenes) y no tiene texto que leer. "
                    "Para traducirlo haría falta reconocimiento de texto (OCR), que aún no está disponible."]
    parrafos = [p for pagina in paginas for p in _parrafos_de_pagina(pagina)]
    avisos = [f"PDF de {len(paginas)} página(s). Revisa el texto antes de traducir: puede traer "
              "encabezados, pies de página o párrafos unidos o cortados. Edítalo aquí mismo si hace falta."]
    return "\n\n".join(parrafos), avisos
