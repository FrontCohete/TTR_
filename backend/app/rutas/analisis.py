"""Endpoints de la vista Analizar (etapa 3, pieza 3.7).

    GET /api/analisis/vigente            ficha del análisis vigente (404 si todavía no hay)
    GET /api/analisis/vigente/puntos     los puntos analizados, en formato ligero
    GET /api/analisis/vigente/hotspots   los hotspots como FeatureCollection

El formato de cada respuesta es el que espera el frontend: README_INTEGRACION §4.7–4.9.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text

from app.basedatos import engine
from app.servicios import analisis as A

router = APIRouter(prefix="/api/analisis", tags=["Analizar"])

SIN_ANALISIS = "Todavía no hay un análisis: carga un dataset para generar los hotspots."


def conexion():
    """Una conexión de solo lectura por petición (las pruebas la reemplazan por la suya)."""
    with engine.connect() as con:
        yield con


def id_vigente(con) -> int:
    """id del análisis vigente, o 404 si no hay (para el frontend es un estado normal)."""
    id_analisis = con.execute(text(
        "SELECT id_analisis FROM analisis_hdbscan WHERE vigente"
    )).scalar()
    if id_analisis is None:
        raise HTTPException(status_code=404, detail=SIN_ANALISIS)
    return id_analisis


# ------------------------------------------------------------------ §4.7
@router.get("/vigente", summary="Ficha del análisis vigente")
def analisis_vigente(con=Depends(conexion)):
    fila = con.execute(text("""
        SELECT a.id_analisis, a.fecha, a.n_puntos, a.n_hotspots, a.n_ruido,
               a.min_cluster_size, a.min_samples, a.metrica, a.peso_minimo,
               a.duracion_s, a.id_carga_origen,
               p.n_hotspots AS n_hotspots_previo
        FROM analisis_hdbscan a
        LEFT JOIN analisis_hdbscan p ON p.id_analisis = a.id_analisis_previo
        WHERE a.vigente
    """)).mappings().first()
    if fila is None:
        raise HTTPException(status_code=404, detail=SIN_ANALISIS)
    datos = dict(fila)
    datos["fecha"] = datos["fecha"].isoformat()
    datos["pct_ruido"] = round(100 * datos["n_ruido"] / datos["n_puntos"], 1) if datos["n_puntos"] else 0.0
    return datos


# ------------------------------------------------------------------ §4.8
CONSULTA_PUNTOS = text("""
    SELECT round(p.longitud::numeric, 5)::float8 AS lon,
           round(p.latitud::numeric, 5)::float8  AS lat,
           d.peso_gravedad                       AS peso,
           m.id_hotspot
    FROM membresia_hotspot m
    JOIN punto_delictivo p USING (id_punto)
    JOIN cat_delito d      USING (id_delito)
    WHERE m.id_analisis = :id
    ORDER BY m.id_punto
""")


@router.get("/vigente/puntos", summary="Puntos del análisis vigente (formato ligero)")
def puntos_vigentes(formato: str = "ligero", con=Depends(conexion)):
    """~54 mil puntos como tabla compacta: columnas + datos. id_hotspot null = ruido.

    Se arma el JSON a mano (json.dumps) porque es bastante más rápido que dejar que
    FastAPI revise 54 mil listas una por una.
    """
    if formato != "ligero":
        raise HTTPException(status_code=400, detail="Solo existe el formato 'ligero'.")
    id_analisis = id_vigente(con)
    datos = [list(fila) for fila in con.execute(CONSULTA_PUNTOS, {"id": id_analisis})]
    cuerpo = {"id_analisis": id_analisis, "columnas": ["lon", "lat", "peso", "id_hotspot"], "datos": datos}
    return Response(json.dumps(cuerpo, separators=(",", ":")), media_type="application/json")


# ------------------------------------------------------------------ §4.9
@router.get("/vigente/hotspots", summary="Hotspots del análisis vigente (GeoJSON)")
def hotspots_vigentes(con=Depends(conexion)):
    return A.hotspots_geojson(con, id_vigente(con))