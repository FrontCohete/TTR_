"""Endpoints de Analizar (pieza 3.7), contra la base real.

Las peticiones usan la conexión 'con', que se deshace al terminar; así la prueba
del 404 puede "apagar" el análisis vigente sin tocar la base de verdad.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.rutas import analisis as R
from pruebas.test_insercion import con  # noqa: F401  (fixture: conexión que se deshace)


@pytest.fixture
def cliente(con):
    app.dependency_overrides[R.conexion] = lambda: con
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def vigente(cliente):
    r = cliente.get("/api/analisis/vigente")
    if r.status_code == 404:
        pytest.skip("no hay análisis vigente: corre primero python crear_analisis.py")
    return r.json()


def test_ficha_del_vigente(vigente):
    for campo in ("id_analisis", "n_hotspots", "n_puntos", "n_ruido", "fecha",
                  "min_cluster_size", "min_samples", "n_hotspots_previo"):
        assert campo in vigente
    assert isinstance(vigente["id_analisis"], int)
    assert 0 <= vigente["n_ruido"] <= vigente["n_puntos"]


def test_sin_analisis_responde_404_en_espanol(cliente, con):
    con.execute(text("UPDATE analisis_hdbscan SET vigente = false WHERE vigente"))   # se deshace
    for ruta in ("/api/analisis/vigente", "/api/analisis/vigente/puntos",
                 "/api/analisis/vigente/hotspots"):
        r = cliente.get(ruta)
        assert r.status_code == 404
        assert r.json()["detail"].startswith("Todavía no hay un análisis")


def test_puntos_en_formato_ligero(cliente, vigente):
    r = cliente.get("/api/analisis/vigente/puntos", params={"formato": "ligero"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["columnas"] == ["lon", "lat", "peso", "id_hotspot"]
    datos = cuerpo["datos"]
    assert len(datos) == vigente["n_puntos"]
    assert sum(1 for d in datos if d[3] is None) == vigente["n_ruido"]
    lon, lat, peso, _ = datos[0]
    assert -99.3 < lon < -98.9 and 19.3 < lat < 19.7          # [lon, lat] dentro de la zona
    assert all(isinstance(d[2], int) and 0 <= d[2] <= 4 for d in datos)   # peso = índice entero


def test_hotspots_como_featurecollection(cliente, vigente):
    fc = cliente.get("/api/analisis/vigente/hotspots").json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == vigente["n_hotspots"]
    f = fc["features"][0]
    assert f["geometry"]["type"] in ("Polygon", "MultiPolygon")
    p = f["properties"]
    assert isinstance(p["id_hotspot"], int) and isinstance(p["etiqueta"], int)
    assert p["codigo"] == "H-01" and p["indice_gravedad"] is not None
    assert len(p["centroide"]) == 2 and p["centroide"][0] < 0       # [lon, lat]


def test_puntos_y_hotspots_usan_los_mismos_ids(cliente, vigente):
    ids_hotspots = {f["properties"]["id_hotspot"]
                    for f in cliente.get("/api/analisis/vigente/hotspots").json()["features"]}
    ids_puntos = {d[3] for d in cliente.get("/api/analisis/vigente/puntos").json()["datos"]} - {None}
    assert ids_puntos == ids_hotspots


def test_formato_desconocido(cliente, vigente):
    r = cliente.get("/api/analisis/vigente/puntos", params={"formato": "completo"})
    assert r.status_code == 400 and "ligero" in r.json()["detail"]