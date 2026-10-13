"""Punto de entrada de la API de TTR_ClusterAgent.

Se enciende desde la carpeta backend con:
    uvicorn app.main:app --reload --reload-dir app --port 8000
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.basedatos import engine
from app.errores import registrar_manejadores

from app.rutas import cargas, mapa, analisis, particiones
from app.servicios import procesamiento
from fastapi.middleware.gzip import GZipMiddleware

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    """Lo de antes del yield corre al encender la API; lo de después, al apagarla."""
    try:
        interrumpidas = procesamiento.recuperar_interrumpidas()
        if interrumpidas:
            log.warning("%s carga(s) quedaron a medias y se marcaron como error.", interrumpidas)
    except SQLAlchemyError:
        log.warning("No se pudo revisar las cargas interrumpidas: ¿está encendida la base?")
    yield


app = FastAPI(
    title="TTR_ClusterAgent · API",
    description=(
        "Backend de TTR_: ingesta de datos de la FGJ, HDBSCAN, Louvain y "
        "algoritmo genético sobre la alcaldía Gustavo A. Madero."
    ),
    version="0.3.0",
    lifespan=ciclo_de_vida,
)
# Comprime las respuestas de más de 1 KB (puntos, colonias, generaciones)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Todos los errores salen como {"detail": "texto en español"}
registrar_manejadores(app)

# Endpoints de cada vista
app.include_router(mapa.router)
app.include_router(cargas.router)
app.include_router(analisis.router)
app.include_router(particiones.router)


@app.get("/", include_in_schema=False)
def raiz():
    """Abrir localhost:8000 lleva directo a la documentación."""
    return RedirectResponse("/docs")


@app.get("/api/salud", tags=["Sistema"])
def salud():
    """Comprueba que la API está encendida y que alcanza la base de datos."""
    try:
        with engine.connect() as conexion:
            postgis = conexion.execute(text("SELECT postgis_lib_version()")).scalar()
            colonias = conexion.execute(text("SELECT count(*) FROM colonia")).scalar()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="La API está encendida, pero no pudo conectarse a la base de datos.",
        )
    return {"estado": "ok", "postgis": postgis, "colonias": colonias}