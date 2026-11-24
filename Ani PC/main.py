"""
Servidor de Aniriame (versión 0.2).

Conecta la base de datos (Postgres en Supabase, via DATABASE_URL) con el exterior. No traduce por sí mismo:
usa el motor de motor.py, que por ahora es un marcador de prueba.

Para encenderlo:   uvicorn main:app --reload
Para probarlo:     abrir http://127.0.0.1:8000/docs
"""
import os
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

import aniriame_db as db
import extraccion
import motor
import plantilla

TOKEN = os.environ.get("ANIRIAME_TOKEN")  # si se define, las rutas que escriben piden este token

@asynccontextmanager
async def ciclo_de_vida(app):
    # Al encender, comprobamos que la base de datos exista y tenga sus tablas
    con = db.conectar()
    try:
        db.verificar_base(con)
    finally:
        con.close()
    yield


app = FastAPI(title="Aniriame", version="0.2", lifespan=ciclo_de_vida)

# Solo se permiten estos orígenes (la página se sirve desde el mismo servidor, así que no hace falta más).
# Para otro dominio: ANIRIAME_ORIGENES=https://tu-dominio.com
ORIGENES = [o.strip() for o in os.environ.get("ANIRIAME_ORIGENES", "http://127.0.0.1:8000,http://localhost:8000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ORIGENES, allow_methods=["*"], allow_headers=["*"])


def get_con():
    con = db.conectar()
    try:
        yield con
    finally:
        con.close()


def verificar_token(x_token: Optional[str] = Header(default=None)):
    if TOKEN and x_token != TOKEN:
        raise HTTPException(status_code=401, detail="Falta el token de acceso o es incorrecto")


# ---------- Datos que esperamos recibir ----------

class PeticionTraducir(BaseModel):
    texto: str = Field(min_length=1, max_length=20000)
    area: Optional[str] = None
    documento: Optional[str] = None


class PeticionRevision(BaseModel):
    par_id: int
    estrellas: int = Field(ge=0, le=5)
    revisor: str = Field(min_length=1)
    correccion: Optional[str] = None


class PeticionPar(BaseModel):
    texto_es: str = Field(min_length=1)
    texto_rar: str = Field(min_length=1)
    tipo: str = "frase"
    origen: str = "institucional"
    documento: Optional[str] = None
    area: Optional[str] = None
    estado: str = "pendiente"
    validado_por: Optional[str] = None


class ParEntrenamiento(BaseModel):
    texto_es: str = Field(min_length=1, max_length=10000)
    texto_rar: str = Field(min_length=1, max_length=10000)
    documento: Optional[str] = None
    area: Optional[str] = None


class PeticionEntrenar(BaseModel):
    pares: List[ParEntrenamiento] = Field(min_length=1, max_length=500)
    estrellas: int = Field(ge=1, le=5)
    revisor: str = Field(min_length=1)
    documento: Optional[str] = None
    area: Optional[str] = None
    confirmar: bool = False  # False: solo vista previa. True: guarda en la base.


# ---------- Rutas ----------

@app.get("/")
def estado():
    return {"servicio": "Aniriame", "version": "0.2", "motor": motor.NOMBRE,
            "acceso_protegido": bool(TOKEN)}


@app.get("/buscar")
def buscar(q: str, limite: int = 10, con=Depends(get_con)):
    """Busca en el léxico del CEEES, de español a rarámuri."""
    return {"consulta": q, "resultados": db.buscar(con, q, limite=limite)}


@app.post("/traducir", dependencies=[Depends(verificar_token)])
def traducir(p: PeticionTraducir, con=Depends(get_con)):
    """Traduce un texto párrafo por párrafo.
    Si ya existe una referencia validada, la devuelve. Si no, genera un borrador por revisar."""
    resultados = []
    for parrafo in db.dividir_parrafos(p.texto):
        tipo = db.tipo_de(parrafo)
        encontrado = db.buscar_frase(con, parrafo)
        if encontrado["exacta"]:
            resultados.append({
                "par_id": encontrado["exacta"]["id"], "texto_es": parrafo,
                "texto_rar": encontrado["exacta"]["texto_rar"],
                "estado": "referencia validada", "aviso": None,
            })
            continue
        terminos = db.terminos_del_texto(con, parrafo)
        try:
            texto_rar = motor.traducir(parrafo, encontrado["parecidos"], terminos)
        except motor.MotorError as e:
            raise HTTPException(status_code=503, detail=str(e))
        par_id = db.guardar_borrador(con, parrafo, texto_rar, tipo=tipo,
                                     area=p.area, documento=p.documento)
        resultados.append({
            "par_id": par_id, "texto_es": parrafo, "texto_rar": texto_rar,
            "estado": "borrador",
            "aviso": "Borrador por revisar: no publicar sin la revisión de la persona evaluadora.",
            "ejemplos_usados": [e["id"] for e in encontrado["parecidos"]],
            "terminos_del_lexico": terminos,
        })
    return {"motor": motor.NOMBRE, "resultados": resultados}


MAX_ARCHIVO = 20 * 1024 * 1024  # 20 MB


@app.post("/extraer", dependencies=[Depends(verificar_token)])
def extraer(archivo: UploadFile = File(...)):
    """Lee un PDF, Word (.docx) o .txt y devuelve su texto, para revisarlo antes de traducir."""
    datos = archivo.file.read(MAX_ARCHIVO + 1)
    if len(datos) > MAX_ARCHIVO:
        raise HTTPException(status_code=413, detail="El archivo pesa más de 20 MB.")
    try:
        texto, avisos = extraccion.extraer(archivo.filename or "", datos)
    except extraccion.ErrorExtraccion as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"texto": texto, "avisos": avisos}


@app.get("/pendientes")
def pendientes(limite: int = 50, con=Depends(get_con)):
    """Borradores que esperan la revisión de la persona evaluadora."""
    return {"pendientes": db.pendientes(con, limite=limite)}


@app.post("/revisar", dependencies=[Depends(verificar_token)])
def revisar(p: PeticionRevision, con=Depends(get_con)):
    """Registra estrellas y, si la hay, la corrección. Con 5 estrellas o con una corrección,
    el resultado entra a las referencias validadas."""
    try:
        referencia_id = db.registrar_revision(con, p.par_id, p.estrellas, p.revisor, p.correccion)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "referencia_id": referencia_id}


@app.post("/pares", dependencies=[Depends(verificar_token)])
def agregar_par(p: PeticionPar, con=Depends(get_con)):
    """Agrega una frase o un párrafo con su traducción (por ejemplo, de un documento ya traducido)."""
    par_id = db.agregar_par(con, p.texto_es, p.texto_rar, tipo=p.tipo, origen=p.origen,
                            documento=p.documento, area=p.area, estado=p.estado,
                            validado_por=p.validado_por)
    return {"ok": True, "par_id": par_id}


@app.get("/indicadores")
def indicadores(con=Depends(get_con)):
    """Indicadores de avance y de crecimiento."""
    return db.indicadores(con)


@app.get("/app", include_in_schema=False)
def pagina():
    """Sirve la página (index.html, que debe estar junto a main.py). Solo sirve ese archivo, nada más."""
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Falta index.html en la misma carpeta que main.py")
    return FileResponse(ruta)


@app.post("/entrenar", dependencies=[Depends(verificar_token)])
def entrenar(p: PeticionEntrenar, con=Depends(get_con)):
    """Carga pares ya establecidos, con un nivel de confianza en estrellas.
    Con confirmar=false devuelve solo la vista previa (cuántos son nuevos, repetidos o con conflicto)."""
    return db.cargar_pares(con, [x.model_dump() for x in p.pares], p.estrellas, p.revisor.strip(),
                           p.documento, p.area, aplicar=p.confirmar)


@app.get("/plantilla.xlsx")
def descargar_plantilla_xlsx():
    """Plantilla de Excel limpia, para cargar muchos pares de traducción."""
    return Response(content=plantilla.plantilla_xlsx(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="plantilla_aniriame.xlsx"'})


@app.get("/plantilla.csv")
def descargar_ejemplo_csv():
    """Ejemplo en CSV (con la marca de orden de bytes para que Excel respete los acentos)."""
    return Response(content=plantilla.csv_ejemplo().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="ejemplo_aniriame.csv"'})


@app.post("/leer-pares", dependencies=[Depends(verificar_token)])
def leer_pares(archivo: UploadFile = File(...)):
    """Lee un Excel (.xlsx) lleno con la plantilla y devuelve los pares, para revisarlos antes de guardar."""
    if not (archivo.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Sube un archivo Excel .xlsx (o un CSV).")
    datos = archivo.file.read(MAX_ARCHIVO + 1)
    if len(datos) > MAX_ARCHIVO:
        raise HTTPException(status_code=413, detail="El archivo pesa más de 20 MB.")
    try:
        pares, avisos = plantilla.leer_pares_xlsx(datos)
    except plantilla.ErrorPlantilla as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"pares": pares, "avisos": avisos}
