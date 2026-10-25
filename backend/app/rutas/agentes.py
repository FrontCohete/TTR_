"""Endpoints de los agentes (etapa 5, README_INTEGRACION §4.12–4.17).

    POST /api/agentes                          lanza un algoritmo genético por grafo (202, en segundo plano)
    GET  /api/agentes/{id}                     estado y avance (el frontend pregunta cada segundo)
    GET  /api/agentes/{id}/generaciones        resumen de cada generación (vista Rutas)
    GET  /api/generaciones/{id}/individuos     las rutas y operaciones de una generación (vista Rutas)
    GET  /api/agentes/{id}/ruta                la mejor ruta como LineString (vista Simular)
    GET  /api/agentes/{id}/ruta-calles         la misma ruta dibujada por calles (OSRM, se guarda; etapa 6)
    POST /api/simulaciones                     registra un recorrido simulado
"""
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.basedatos import engine
from app.servicios import agentes as S
from app.servicios import genetico as AG
from app.servicios import ruteo

router = APIRouter(prefix="/api", tags=["Rutas y Simular · Agentes"])


class ParametrosAG(BaseModel):
    tam_poblacion: int = Field(100, ge=2, le=500)
    n_generaciones: int = Field(1000, ge=1, le=2000)
    tam_torneo: int = Field(5, ge=2, le=500)
    prob_cruce: float = Field(0.9, ge=0, le=1)
    prob_mutacion: float = Field(0.5, ge=0, le=1)
    op_cruce: Literal["OX", "PMX"] = "OX"
    op_mutacion: Literal["swap", "inversion"] = "inversion"
    semilla: int = Field(42, ge=0, le=999_999)
    ruta_cerrada: bool = True


class PedidoAgentes(BaseModel):
    id_particion: int
    parametros: ParametrosAG = ParametrosAG()


class PedidoSimulacion(BaseModel):
    id_ejecucion: int
    distancia_total: float | None = Field(None, ge=0)
    duracion_s: float | None = Field(None, ge=0)


def conexion():
    """Una conexión por petición (las pruebas la reemplazan por una que se deshace)."""
    with engine.connect() as con:
        yield con


def transaccion(con):
    return con.begin_nested() if con.in_transaction() else con.begin()


def lanzar(ids: list[int]) -> None:
    """Lo que corre en segundo plano (las pruebas lo reemplazan)."""
    S.ejecutar_agentes(ids)


@router.post("/agentes", status_code=202, summary="Generar un agente por grafo de la partición")
def crear(pedido: PedidoAgentes, tareas: BackgroundTasks, con=Depends(conexion)):
    p = AG.Parametros(**pedido.parametros.model_dump(), n_elite=1)      # élite fija
    try:
        with transaccion(con):
            creadas = S.crear_ejecuciones(con, pedido.id_particion, p)
    except AG.ParametrosInvalidos as error:
        raise HTTPException(status_code=422, detail=str(error))
    except S.NoEncontrado as error:
        raise HTTPException(status_code=404, detail=str(error))
    except S.Ocupado as error:
        raise HTTPException(status_code=409, detail=str(error))
    tareas.add_task(lanzar, [c["id_ejecucion"] for c in creadas])
    return {"ejecuciones": creadas}


def _responder(funcion, *args):
    try:
        return funcion(*args)
    except S.NoEncontrado as error:
        raise HTTPException(status_code=404, detail=str(error))
    except S.NoTerminado as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.get("/agentes/{id_ejecucion}", summary="Estado de un agente")
def consultar(id_ejecucion: int, con=Depends(conexion)):
    return _responder(S.agente, con, id_ejecucion)


@router.get("/agentes/{id_ejecucion}/generaciones", summary="Resumen de cada generación")
def generaciones(id_ejecucion: int, con=Depends(conexion)):
    return _responder(S.generaciones, con, id_ejecucion)


@router.get("/generaciones/{id_generacion}/individuos", summary="Rutas y operaciones de una generación")
def individuos(id_generacion: int, con=Depends(conexion)):
    return _responder(S.individuos, con, id_generacion)


@router.get("/agentes/{id_ejecucion}/ruta", summary="La mejor ruta del agente (LineString)")
def ruta(id_ejecucion: int, con=Depends(conexion)):
    return _responder(S.ruta, con, id_ejecucion)


@router.get("/agentes/{id_ejecucion}/ruta-calles", summary="La mejor ruta del agente dibujada por calles (OSRM)")
def ruta_calles(id_ejecucion: int, con=Depends(conexion)):
    """La primera vez se la pide al servidor de ruteo (unos segundos) y la guarda; después sale de la base."""
    try:
        with transaccion(con):
            return ruteo.ruta_calles(con, id_ejecucion)
    except S.NoEncontrado as error:
        raise HTTPException(status_code=404, detail=str(error))
    except S.NoTerminado as error:
        raise HTTPException(status_code=409, detail=str(error))
    except ruteo.RuteoNoDisponible as error:
        raise HTTPException(status_code=503, detail=f"{error} Se muestra la ruta en línea recta.")


@router.post("/simulaciones", status_code=201, summary="Registrar un recorrido simulado")
def simular(pedido: PedidoSimulacion, con=Depends(conexion)):
    try:
        with transaccion(con):
            return S.registrar_simulacion(con, pedido.id_ejecucion, pedido.distancia_total, pedido.duracion_s)
    except S.NoEncontrado as error:
        raise HTTPException(status_code=404, detail=str(error))
