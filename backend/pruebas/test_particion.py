"""Louvain y partición en grafos (etapa 4).

Las primeras pruebas usan hotspots inventados y no tocan la base. Las últimas usan el análisis
vigente real dentro de una transacción que se deshace (no queda ninguna partición guardada).
"""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.rutas import particiones as R
from app.servicios import particion as P
from pruebas.test_insercion import con  # noqa: F401  (fixture: conexión que se deshace)

CENTROS = [(19.56, -99.14), (19.54, -99.08), (19.50, -99.16), (19.48, -99.10), (19.45, -99.13)]


def ciudad(por_zona=(9, 7, 8, 6, 10), semilla=3) -> pd.DataFrame:
    """Cinco zonas de hotspots separadas ~4 km, de norte a sur."""
    rng = np.random.default_rng(semilla)
    filas, etiqueta = [], 1
    for z, (n, (lat, lon)) in enumerate(zip(por_zona, CENTROS)):
        for _ in range(n):
            filas.append({"id_hotspot": 1000 + etiqueta, "etiqueta": etiqueta, "zona": z,
                          "lat": lat + rng.normal(0, 0.004), "lon": lon + rng.normal(0, 0.004)})
            etiqueta += 1
    return pd.DataFrame(filas)


# ------------------------------------------------------------------ cálculo
def test_haversine_un_grado_de_latitud():
    assert P.haversine(19.0, -99.0, 20.0, -99.0) == pytest.approx(111_195, abs=1)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_exactamente_n_grafos_sin_repetir_hotspots(n):
    h = ciudad()
    r = P.particionar(h, n)
    assert r.n_grafos == n and len(r.grafos) == n
    todos = [x for g in r.grafos for x in g["hotspots"]]
    assert sorted(todos) == sorted(h.id_hotspot) and len(todos) == len(set(todos))


def test_cinco_zonas_separadas_dan_cinco_grafos_limpios():
    h = ciudad()
    zona = dict(zip(h.id_hotspot, h.zona))
    r = P.particionar(h, 5)
    for g in r.grafos:
        assert len({zona[x] for x in g["hotspots"]}) == 1      # cada grafo es una sola zona
    assert not r.fusion and r.resolucion is not None and r.modularidad > 0.5


def test_numerados_de_norte_a_sur_con_sus_colores():
    h = ciudad()
    lat = dict(zip(h.id_hotspot, h.lat))
    r = P.particionar(h, 5)
    medias = [np.mean([lat[x] for x in g["hotspots"]]) for g in r.grafos]
    assert medias == sorted(medias, reverse=True)
    assert [g["color"] for g in r.grafos] == P.COLORES


def test_aristas_todas_las_parejas_en_metros():
    h = ciudad()
    pos = {i: (a, o) for i, a, o in zip(h.id_hotspot, h.lat, h.lon)}
    for g in P.particionar(h, 3).grafos:
        k = len(g["hotspots"])
        assert len(g["aristas"]) == k * (k - 1) // 2
        for a, b, d in g["aristas"]:
            assert a < b
            assert d == pytest.approx(P.haversine(*pos[a], *pos[b]), abs=0.1)


def test_misma_semilla_mismo_resultado():
    h = ciudad()
    uno = [g["hotspots"] for g in P.particionar(h, 4).grafos]
    dos = [g["hotspots"] for g in P.particionar(h, 4).grafos]
    assert uno == dos


def test_fusion_junta_la_mas_chica_con_la_mas_cercana():
    pos = {1: (19.50, -99.10), 2: (19.501, -99.10), 3: (19.60, -99.10), 4: (19.601, -99.10), 5: (19.502, -99.10)}
    resultado = P.fusionar([{1, 2}, {3, 4}, {5}], pos, 2)
    assert sorted(map(sorted, resultado)) == [[1, 2, 5], [3, 4]]


def test_mas_grafos_que_hotspots():
    with pytest.raises(P.HotspotsInsuficientes):
        P.particionar(ciudad(por_zona=(1, 1, 1, 0, 0)), 5)


# ------------------------------------------------------------------ base real (se deshace)
@pytest.fixture
def vigente(con):
    id_analisis = con.execute(text("SELECT id_analisis FROM analisis_hdbscan WHERE vigente")).scalar()
    if id_analisis is None:
        pytest.skip("no hay análisis vigente: corre primero python crear_analisis.py")
    return id_analisis


def test_guarda_grafos_nodos_y_aristas(con, vigente):
    datos = P.nueva_particion(con, 3)
    p = datos["id_particion"]
    n_hotspots = con.execute(text("SELECT count(*) FROM hotspot WHERE id_analisis = :a"), {"a": vigente}).scalar()
    assert datos["n_grafos"] == 3 and len(datos["grafos"]) == 3
    assert con.execute(text("SELECT count(*) FROM nodo_grafo WHERE id_particion = :p"), {"p": p}).scalar() == n_hotspots
    esperadas = sum(g["n_nodos"] * (g["n_nodos"] - 1) // 2 for g in datos["grafos"])
    reales = con.execute(text("""
        SELECT count(*) FROM arista a JOIN grafo g USING (id_grafo) WHERE g.id_particion = :p
    """), {"p": p}).scalar()
    assert reales == esperadas
    assert all(isinstance(h, int) for g in datos["grafos"] for h in g["hotspots"])


def test_mismo_n_reutiliza_y_otro_n_cambia_la_vigente(con, vigente):
    primera = P.nueva_particion(con, 2)["id_particion"]
    assert P.nueva_particion(con, 2)["id_particion"] == primera          # se reutiliza
    otra = P.nueva_particion(con, 4)["id_particion"]
    assert otra != primera
    vigentes = con.execute(text("""
        SELECT id_particion FROM particion_louvain WHERE id_analisis = :a AND vigente
    """), {"a": vigente}).scalars().all()
    assert vigentes == [otra]


# ------------------------------------------------------------------ API
@pytest.fixture
def cliente(con):
    app.dependency_overrides[R.conexion] = lambda: con
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_post_particiones(cliente, vigente):
    r = cliente.post("/api/particiones", json={"n_grafos": 2})
    assert r.status_code == 200
    datos = r.json()
    assert datos["n_grafos"] == 2
    for g in datos["grafos"]:
        assert set(g) >= {"id_grafo", "numero", "color", "hotspots"}
        assert g["color"].startswith("#") and len(g["color"]) == 7
    assert cliente.get(f"/api/particiones/{datos['id_particion']}").json()["grafos"] == datos["grafos"]


def test_n_fuera_de_rango_y_particion_inexistente(cliente):
    assert cliente.post("/api/particiones", json={"n_grafos": 7}).status_code == 422
    assert cliente.post("/api/particiones", json={"n_grafos": ""}).status_code == 422
    r = cliente.get("/api/particiones/999999999")
    assert r.status_code == 404 and isinstance(r.json()["detail"], str)