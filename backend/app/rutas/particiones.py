"""Endpoints de la partición en grafos (etapa 4, README_INTEGRACION §4.10).

    POST /api/particiones          {"n_grafos": 3} → reparte los hotspots vigentes en 3 grafos
    GET  /api/particiones/{id}     la misma respuesta, para consultar una partición guardada
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.basedatos import engine
from app.servicios import particion as P

router = APIRouter(prefix="/api/particiones", tags=["Analizar · Grafos"])


class PedidoParticion(BaseModel):
    n_grafos: int = Field(..., ge=1, le=5, description="Número de grafos, de 1 a 5")


def conexion():
    """Una conexión por petición (las pruebas la reemplazan por una que se deshace)."""
    with engine.connect() as con:
        yield con


def transaccion(con):
    """Transacción normal; dentro de las pruebas, un punto de guardado dentro de la suya."""
    return con.begin_nested() if con.in_transaction() else con.begin()


@router.post("", summary="Repartir los hotspots vigentes en N grafos (Louvain)")
def crear(pedido: PedidoParticion, con=Depends(conexion)):
    try:
        with transaccion(con):
            return P.nueva_particion(con, pedido.n_grafos)
    except P.SinAnalisis as error:
        raise HTTPException(status_code=404, detail=str(error))
    except P.HotspotsInsuficientes as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.get("/{id_particion}", summary="Consultar una partición guardada")
def consultar(id_particion: int, con=Depends(conexion)):
    try:
        return P.respuesta(con, id_particion)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))