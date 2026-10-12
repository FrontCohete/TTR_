"""Endpoints de la cartografía base (README_INTEGRACION §4.5 y §4.6)."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.servicios import mapa as servicio

router = APIRouter(prefix="/api/mapa", tags=["Mapa"])


@router.get("/limite", summary="Contorno de GAM")
def limite():
    """FeatureCollection con una sola Feature `Polygon`: el contorno de GAM."""
    try:
        return JSONResponse(servicio.contorno_gam())
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/colonias", summary="Colonias de GAM")
def colonias():
    """FeatureCollection con las 179 colonias de GAM."""
    return JSONResponse(servicio.colonias_gam())