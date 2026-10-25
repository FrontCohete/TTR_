"""Endpoints de mantenimiento (etapa 5.6), para la sección «Mantenimiento» de la vista Inicio.

    GET  /api/mantenimiento            qué hay en la base, cuánto ocupa y si se puede reiniciar
    POST /api/mantenimiento/reiniciar  «Empezar de cero»: borra los datos y conserva los catálogos
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.basedatos import engine
from app.servicios import mantenimiento as S

router = APIRouter(prefix="/api/mantenimiento", tags=["Inicio · Mantenimiento"])


class PedidoReinicio(BaseModel):
    confirmacion: str = Field(..., description="Debe ser exactamente BORRAR", examples=["BORRAR"])


def conexion():
    """Una conexión por petición (las pruebas la reemplazan por una que se deshace)."""
    with engine.connect() as con:
        yield con


def transaccion(con):
    return con.begin_nested() if con.in_transaction() else con.begin()


@router.get("", summary="Estado de la base y si se puede empezar de cero")
def estado(con=Depends(conexion)):
    return S.resumen(con)


@router.post("/reiniciar", summary="Empezar de cero: borra datasets, análisis, grafos y agentes")
def reiniciar(pedido: PedidoReinicio, con=Depends(conexion)):
    try:
        with transaccion(con):                         # commit solo si todo salió bien
            borrado = S.reiniciar(con, pedido.confirmacion)
    except S.NoPermitido as error:
        raise HTTPException(status_code=403, detail=str(error))
    except S.ConfirmacionInvalida as error:
        raise HTTPException(status_code=422, detail=str(error))
    except S.Ocupado as error:
        raise HTTPException(status_code=409, detail=str(error))
    archivos = S.limpiar_archivos()
    S.log.info("Base reiniciada: %s; archivos: %s", borrado, archivos)
    return {
        "mensaje": "Listo: la base quedó vacía. Ya puedes cargar tus datasets desde Inicio.",
        "borrado": borrado,
        "archivos": archivos,
    }
