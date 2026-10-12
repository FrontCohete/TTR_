"""Endpoints de la vista Inicio (README_INTEGRACION §4.1 a §4.4)."""
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status

from app.basedatos import engine
from app.servicios import ingesta, procesamiento

router = APIRouter(prefix="/api/cargas", tags=["Inicio · Cargas"])


@router.post("", status_code=status.HTTP_201_CREATED, summary="Subir un archivo de la FGJ")
def subir(archivo: UploadFile = File(..., description="Archivo .csv, .xlsx o .xls")):
    """Lee el archivo, valida sus columnas y devuelve la vista previa.

    Todavía no inserta puntos: eso ocurre al llamar a /procesar.
    """
    contenido = archivo.file.read()
    try:
        return ingesta.recibir_carga(contenido, archivo.filename or "")
    except ingesta.ArchivoInvalido as error:
        raise HTTPException(status_code=422, detail=str(error))
    except ingesta.CargaDuplicada as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.get("", summary="Historial de cargas")
def historial():
    """Las cargas procesadas o con error, de la más nueva a la más vieja."""
    with engine.connect() as con:
        return procesamiento.listar_cargas(con)


@router.get("/{id_carga}", summary="Estado de una carga")
def estado(id_carga: int):
    """Estado, etapa y avance. El frontend lo consulta cada segundo."""
    with engine.connect() as con:
        try:
            return procesamiento.obtener_carga(con, id_carga)
        except procesamiento.CargaNoEncontrada as error:
            raise HTTPException(status_code=404, detail=str(error))


@router.post("/{id_carga}/procesar", status_code=status.HTTP_202_ACCEPTED,
             summary="Procesar una carga")
def procesar(id_carga: int, tareas: BackgroundTasks):
    """Responde de inmediato y deja la limpieza y la inserción corriendo en segundo plano."""
    try:
        with engine.begin() as con:
            procesamiento.iniciar(con, id_carga)
    except procesamiento.CargaNoEncontrada as error:
        raise HTTPException(status_code=404, detail=str(error))
    except procesamiento.ConflictoCarga as error:
        raise HTTPException(status_code=409, detail=str(error))
    tareas.add_task(procesamiento.procesar, id_carga)
    return {"id_carga": id_carga, "estado": "procesando"}