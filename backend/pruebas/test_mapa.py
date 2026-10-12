"""Contrato de los endpoints del mapa (README_INTEGRACION §4.5 y §4.6).

Usa la API real y la base real, solo lectura.
"""
from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)


def test_limite_es_un_solo_polygon():
    r = cliente.get("/api/mapa/limite")
    assert r.status_code == 200
    datos = r.json()
    assert datos["type"] == "FeatureCollection"
    assert len(datos["features"]) == 1
    geometria = datos["features"][0]["geometry"]
    assert geometria["type"] == "Polygon"          # no MultiPolygon
    anillo = geometria["coordinates"][0]
    assert anillo[0] == anillo[-1]                 # anillo cerrado


def test_coordenadas_en_orden_lon_lat():
    anillo = cliente.get("/api/mapa/limite").json()["features"][0]["geometry"]["coordinates"][0]
    lon, lat = anillo[0]
    # Si estuvieran al revés, "lon" valdría ~19.5 y fallaría
    assert -99.25 <= lon <= -99.00
    assert 19.40 <= lat <= 19.65


def test_colonias_completas():
    datos = cliente.get("/api/mapa/colonias").json()
    assert len(datos["features"]) == 179
    for colonia in datos["features"]:
        assert colonia["geometry"]["type"] in ("Polygon", "MultiPolygon")
        assert isinstance(colonia["properties"]["id_colonia"], int)


def test_colonias_pesan_menos_de_1_mb():
    r = cliente.get("/api/mapa/colonias")
    print(f"\nColonias: {len(r.content) / 1024:.0f} KB sin comprimir")
    assert len(r.content) < 1_000_000


def test_respuestas_grandes_van_comprimidas():
    r = cliente.get("/api/mapa/colonias")
    assert r.headers.get("content-encoding") == "gzip"