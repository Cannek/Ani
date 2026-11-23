"""
Funciones de Aniriame: búsqueda, pares de traducción y revisión humana.
Se usa junto con la base aniriame.db (ver build_db.py).
"""
import csv
import difflib
import os
import re
import sqlite3
import unicodedata


# ---------- Normalización para buscar sin importar acentos, mayúsculas ni plurales simples ----------

def _sin_acentos(texto):
    t = unicodedata.normalize("NFKD", str(texto).lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _raiz(palabra):
    # Quita la "s" final de plurales simples: abuelas -> abuela
    if len(palabra) > 3 and palabra.endswith("s"):
        return palabra[:-1]
    return palabra


def clave(texto):
    """Convierte un texto en una forma comparable: sin acentos, sin signos, sin plural simple."""
    t = re.sub(r"[^a-z0-9]+", " ", _sin_acentos(texto))
    return " ".join(_raiz(p) for p in t.split())


TABLAS_NECESARIAS = {"entradas", "significados", "pares_traduccion", "revisiones"}


def conectar(ruta="aniriame.db"):
    # SQLite crea un archivo vacío si no encuentra el que buscamos. Para evitarlo, lo comprobamos antes.
    if not os.path.exists(ruta):
        raise FileNotFoundError(
            f"No encuentro la base de datos. La busqué aquí: {os.path.abspath(ruta)}\n"
            "Debe estar en la misma carpeta desde donde enciendes el servidor."
        )
    # check_same_thread=False permite usarla desde el servidor web
    return sqlite3.connect(ruta, check_same_thread=False)


def verificar_base(con, ruta="aniriame.db"):
    """Comprueba que la base tenga las tablas esperadas, y si no, avisa con claridad."""
    tablas = {f[0] for f in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    faltan = TABLAS_NECESARIAS - tablas
    if faltan:
        raise RuntimeError(
            f"La base de datos {os.path.abspath(ruta)} está vacía o es incorrecta "
            f"(faltan las tablas: {', '.join(sorted(faltan))}).\n"
            "Apaga el servidor, borra ese archivo, copia aquí el aniriame.db correcto "
            "(unos 650 KB) o corre build_db.py, y vuelve a encender."
        )


# ---------- 1. Buscar en el léxico del CEEES (español -> rarámuri) ----------

def buscar(con, consulta, limite=10):
    q = clave(consulta)
    if not q:
        return []
    tokens = q.split()
    filtro = " OR ".join(["s.significado_norm LIKE ?"] * len(tokens))
    filas = con.execute(
        f"""SELECT e.id_registro, e.palabra_raramuri, e.clase, e.variantes,
                   e.ejemplos_y_comentarios, e.estado_validacion,
                   s.significado_es, s.significado_norm
            FROM significados s JOIN entradas e USING(id_registro)
            WHERE e.es_nota = 0 AND ({filtro})""",
        [f"%{t}%" for t in tokens],
    ).fetchall()

    mejores = {}
    for id_reg, palabra, clase, variantes, ejemplos, validacion, signif, norm in filas:
        palabras_norm = norm.split()
        if norm == q:
            puntos = 100
        elif norm.startswith(q + " "):
            puntos = 80
        elif f" {q} " in f" {norm} ":
            puntos = 60
        else:
            coinciden = sum(1 for t in tokens if t in palabras_norm)
            puntos = 10 + 40 * coinciden / len(tokens) if coinciden else 5
        fuerte = puntos >= 10  # coincide con palabras completas, no solo con un pedazo
        puntos -= len(norm) * 0.1  # a igualdad, preferimos significados más cortos
        if id_reg not in mejores or puntos > mejores[id_reg][0]:
            mejores[id_reg] = (puntos, fuerte, {
                "id_registro": id_reg, "palabra_raramuri": palabra, "clase": clase,
                "significado": signif, "variantes": variantes,
                "ejemplos": ejemplos, "validacion": validacion,
            })
    ordenados = sorted(mejores.values(), key=lambda x: -x[0])
    if any(f for _, f, _ in ordenados):  # si hay coincidencias buenas, descartamos las débiles
        ordenados = [x for x in ordenados if x[1]]
    return [r for _, _, r in ordenados[:limite]]


# ---------- 2. Pares de traducción (frases y párrafos de documentos) ----------

def agregar_par(con, texto_es, texto_rar, tipo="frase", origen="institucional",
                documento=None, area=None, estado="pendiente",
                validado_por=None, par_original_id=None):
    """Agrega una frase o un párrafo con su traducción. Devuelve el id del par."""
    norm = clave(texto_es)
    texto_rar = texto_rar.strip()
    if estado == "validado":  # evitar duplicar una referencia idéntica
        dup = con.execute(
            "SELECT id FROM pares_traduccion WHERE texto_es_norm=? AND texto_rar=? AND estado='validado'",
            (norm, texto_rar),
        ).fetchone()
        if dup:
            return dup[0]
    cur = con.execute(
        """INSERT INTO pares_traduccion
           (tipo, texto_es, texto_es_norm, texto_rar, origen, documento, area,
            estado, validado_por, par_original_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (tipo, texto_es.strip(), norm, texto_rar, origen, documento, area,
         estado, validado_por, par_original_id),
    )
    con.commit()
    return cur.lastrowid


def importar_pares_csv(con, ruta_csv, origen="institucional", estado="pendiente", validado_por=None):
    """Carga muchos pares desde un CSV con columnas:
    texto_es, texto_rar, tipo (opcional), documento (opcional), area (opcional)."""
    n = 0
    with open(ruta_csv, newline="", encoding="utf-8-sig") as f:
        for fila in csv.DictReader(f):
            if not (fila.get("texto_es") or "").strip() or not (fila.get("texto_rar") or "").strip():
                continue
            agregar_par(
                con, fila["texto_es"], fila["texto_rar"],
                tipo=(fila.get("tipo") or "parrafo").strip() or "parrafo",
                origen=origen, documento=fila.get("documento") or None,
                area=fila.get("area") or None, estado=estado, validado_por=validado_por,
            )
            n += 1
    return n


def guardar_borrador(con, texto_es, texto_rar_sistema, tipo="frase", area=None, documento=None):
    """Guarda lo que tradujo el sistema, como borrador por revisar."""
    return agregar_par(con, texto_es, texto_rar_sistema, tipo=tipo, origen="sistema",
                       documento=documento, area=area, estado="borrador")


def buscar_frase(con, texto_es, k=3, minimo=0.3):
    """Busca en las referencias validadas: una coincidencia exacta y las k más parecidas.
    Las parecidas sirven como ejemplos para guiar al traductor."""
    n = clave(texto_es)
    exacta = con.execute(
        "SELECT id, texto_es, texto_rar FROM pares_traduccion "
        "WHERE texto_es_norm=? AND estado='validado' ORDER BY id DESC LIMIT 1", (n,)
    ).fetchone()
    tokens = set(n.split())
    parecidos = []
    for id_, es, rar, norm in con.execute(
        "SELECT id, texto_es, texto_rar, texto_es_norm FROM pares_traduccion WHERE estado='validado'"
    ):
        otros = set(norm.split())
        union = tokens | otros
        if not union:
            continue
        similitud = len(tokens & otros) / len(union)
        if similitud >= minimo and norm != n:
            parecidos.append((similitud, {"id": id_, "texto_es": es, "texto_rar": rar}))
    parecidos.sort(key=lambda x: -x[0])
    return {
        "exacta": None if not exacta else {"id": exacta[0], "texto_es": exacta[1], "texto_rar": exacta[2]},
        "parecidos": [p for _, p in parecidos[:k]],
    }


# ---------- 3. Revisión humana: estrellas y correcciones ----------

def registrar_revision(con, par_id, estrellas, revisor, correccion=None):
    """Registra la evaluación de una traducción.
    - Con corrección: la corrección se guarda como NUEVA referencia validada,
      y el borrador original queda como 'corregido'.
    - Con 5 estrellas y sin corrección: el par pasa a 'validado' (referencia).
    - 3 o 4 estrellas: 'revisado'. 0 a 2 estrellas: 'rechazado'.
    Devuelve el id del par que quedó como referencia (o None si no hay)."""
    if not 0 <= estrellas <= 5:
        raise ValueError("Las estrellas van de 0 a 5")
    par = con.execute(
        "SELECT tipo, texto_es, texto_rar, area, documento FROM pares_traduccion WHERE id=?", (par_id,)
    ).fetchone()
    if par is None:
        raise ValueError("No existe ese par")
    tipo, texto_es, texto_rar, area, documento = par
    correccion = (correccion or "").strip()

    con.execute(
        "INSERT INTO revisiones (par_id, estrellas, correccion, revisor) VALUES (?,?,?,?)",
        (par_id, estrellas, correccion or None, revisor),
    )

    if correccion and correccion != texto_rar.strip():
        nuevo = agregar_par(con, texto_es, correccion, tipo=tipo, origen="correccion",
                            documento=documento, area=area, estado="validado",
                            validado_por=revisor, par_original_id=par_id)
        con.execute("UPDATE pares_traduccion SET estado='corregido' WHERE id=?", (par_id,))
        con.commit()
        return nuevo
    if estrellas == 5:
        con.execute("UPDATE pares_traduccion SET estado='validado', validado_por=? WHERE id=?",
                    (revisor, par_id))
        con.commit()
        return par_id
    estado = "revisado" if estrellas >= 3 else "rechazado"
    con.execute("UPDATE pares_traduccion SET estado=? WHERE id=?", (estado, par_id))
    con.commit()
    return None


# ---------- 4. Apoyos para el servidor ----------

def dividir_parrafos(texto):
    """Divide un texto en párrafos (separados por línea en blanco o, si no hay, por salto de línea)."""
    partes = [p.strip() for p in re.split(r"\n\s*\n", texto.strip()) if p.strip()]
    if len(partes) <= 1:
        partes = [p.strip() for p in texto.strip().split("\n") if p.strip()]
    return partes


def tipo_de(texto):
    return "frase" if len(texto) < 120 and "\n" not in texto else "parrafo"


def terminos_del_texto(con, texto, maximo=8):
    """Busca en el léxico del CEEES las palabras del texto, como pistas para el traductor."""
    vistos, salida = set(), []
    for palabra in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", texto):
        w = palabra.lower()
        if len(w) <= 3 or w in vistos:
            continue
        vistos.add(w)
        r = buscar(con, w, limite=1)
        if r:
            salida.append({"palabra_es": w, "palabra_raramuri": r[0]["palabra_raramuri"],
                           "significado": r[0]["significado"]})
        if len(salida) >= maximo:
            break
    return salida


def pendientes(con, limite=50):
    """Borradores que esperan revisión de la persona evaluadora."""
    filas = con.execute(
        "SELECT id, tipo, texto_es, texto_rar, documento, area, fecha FROM pares_traduccion "
        "WHERE estado='borrador' ORDER BY id LIMIT ?", (limite,)
    ).fetchall()
    return [dict(zip(("id", "tipo", "texto_es", "texto_rar", "documento", "area", "fecha"), f)) for f in filas]


def indicadores(con, umbral_correccion_menor=0.9):
    """Indicadores de avance y de crecimiento, calculados con lo que hay en la base.

    pct_aceptables = de los borradores del sistema que ya se revisaron, qué porcentaje
    quedó sin corrección (con 4 o 5 estrellas) o con una corrección menor
    (el texto corregido se parece al original en al menos el umbral, 90% por defecto)."""
    q = lambda sql, *a: con.execute(sql, a).fetchone()[0]
    r = {
        "lexico_entradas": q("SELECT COUNT(*) FROM entradas WHERE es_nota=0"),
        "referencias_validadas": q("SELECT COUNT(*) FROM pares_traduccion WHERE estado='validado'"),
        "borradores_pendientes": q("SELECT COUNT(*) FROM pares_traduccion WHERE estado='borrador'"),
        "documentos": q("SELECT COUNT(DISTINCT documento) FROM pares_traduccion WHERE documento IS NOT NULL"),
        "revisiones": q("SELECT COUNT(*) FROM revisiones"),
        "revisores_activos": q("SELECT COUNT(DISTINCT revisor) FROM revisiones"),
        "estrellas_promedio": q("SELECT ROUND(AVG(estrellas), 2) FROM revisiones"),
    }
    r["referencias_por_origen"] = dict(con.execute(
        "SELECT origen, COUNT(*) FROM pares_traduccion WHERE estado='validado' GROUP BY origen").fetchall())

    filas = con.execute(
        "SELECT p.texto_rar, r.correccion, r.estrellas FROM revisiones r "
        "JOIN pares_traduccion p ON p.id = r.par_id WHERE p.origen = 'sistema'").fetchall()
    aceptables = 0
    for texto_rar, correccion, estrellas in filas:
        if not correccion or correccion.strip() == texto_rar.strip():
            aceptables += 1 if estrellas >= 4 else 0
        else:
            parecido = difflib.SequenceMatcher(None, texto_rar.strip(), correccion.strip()).ratio()
            aceptables += 1 if parecido >= umbral_correccion_menor else 0
    r["borradores_revisados"] = len(filas)
    r["pct_aceptables"] = round(100 * aceptables / len(filas), 1) if filas else None

    semanas, acumulado = [], 0
    for semana, n in con.execute(
        "SELECT strftime('%Y-S%W', fecha), COUNT(*) FROM pares_traduccion WHERE estado='validado' "
        "AND origen IN ('sistema', 'correccion') GROUP BY 1 ORDER BY 1"):
        acumulado += n
        semanas.append({"semana": semana, "nuevas": n, "acumuladas": acumulado})
    r["crecimiento_semanal"] = semanas  # solo cuenta lo validado a partir del uso, no el corpus histórico
    return r
