"""Cartografía base de GAM: contorno y colonias.

PostGIS arma el GeoJSON completo; Python solo lo entrega.
Coordenadas en [longitud, latitud] (orden GeoJSON), WGS84 / EPSG:4326.
"""
from functools import lru_cache

from sqlalchemy import text

from app.basedatos import engine

# El contorno se guarda como MultiPolygon, pero el frontend espera un Polygon
# (lee coordinates[0] como anillo exterior). Se toma la parte de mayor área.
_SQL_CONTORNO = text("""
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', json_build_array(json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(g.geom, 0.00004), 6)::json,
            'properties', json_build_object(
                'nombre', a.nombre,
                'superficie_km2', round((ST_Area(a.geom::geography) / 1e6)::numeric, 1)
            )
        ))
    )
    FROM alcaldia a,
         LATERAL (SELECT d.geom FROM ST_Dump(a.geom) d
                  ORDER BY ST_Area(d.geom) DESC LIMIT 1) g
    WHERE a.nombre = 'Gustavo A. Madero'
""")

# Simplificación de ~5 m y 6 decimales: suficiente para el mapa y mucho más ligero
_SQL_COLONIAS = text("""
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', coalesce(json_agg(json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(c.geom, 0.00005), 6)::json,
            'properties', json_build_object(
                'id_colonia', c.id_colonia,
                'nombre', c.nombre,
                'clave_oficial', c.clave_oficial
            )
        ) ORDER BY c.id_colonia), '[]'::json)
    )
    FROM colonia c
""")


@lru_cache(maxsize=1)
def contorno_gam() -> dict:
    """FeatureCollection con el contorno de GAM como un solo Polygon."""
    with engine.connect() as conexion:
        geojson = conexion.execute(_SQL_CONTORNO).scalar()
    if geojson is None:
        raise LookupError("El contorno de GAM no está cargado en la base de datos.")
    return geojson


@lru_cache(maxsize=1)
def colonias_gam() -> dict:
    """FeatureCollection con las colonias de GAM (id_colonia, nombre, clave_oficial)."""
    with engine.connect() as conexion:
        return conexion.execute(_SQL_COLONIAS).scalar()