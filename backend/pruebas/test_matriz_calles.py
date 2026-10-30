"""Matriz por calles (etapa 7, fase 1), SIN internet: el servidor OSRM «table» se reemplaza por uno falso.

El falso mide cada par «en escuadra» (primero este–oeste y luego norte–sur), así que por calles
siempre sale más que en línea recta; y yendo de oeste a este cobra 10 % más, para imitar calles
de un sentido (ida ≠ vuelta).
Las pruebas con base de datos corren dentro de la transacción que se deshace (fixture `con`).
"""
import math
import re

import numpy as np
import pytest
from sqlalchemy import text

from app.servicios import matriz_calles as M
from app.servicios import ruteo
from pruebas.test_insercion import con  # noqa: F401  (fixture: conexión que se deshace)


class TablaFalsa:
    def __init__(self, sin_camino=(), codigo="Ok"):
        self.consultas = []
        self.sin_camino = set(sin_camino)      # pares (i, j) en coordenadas de la consulta
        self.codigo = codigo

    def __call__(self, url):
        self.consultas.append(url)
        if self.codigo != "Ok":
            return {"code": self.codigo, "message": "falló"}
        puntos = re.search(r"/table/v1/\w+/([^?]+)", url).group(1)
        coords = [[float(x) for x in p.split(",")] for p in puntos.split(";")]
        fuentes = re.search(r"sources=([\d;]+)", url)
        destinos = re.search(r"destinations=([\d;]+)", url)
        fu = [int(x) for x in fuentes.group(1).split(";")] if fuentes else list(range(len(coords)))
        de = [int(x) for x in destinos.group(1).split(";")] if destinos else list(range(len(coords)))
        dist = [[None if (a, b) in self.sin_camino else escuadra(coords[a], coords[b]) for b in de] for a in fu]
        dur = [[None if x is None else x / 8.0 for x in fila] for fila in dist]
        return {"code": "Ok", "distances": dist, "durations": dur}


def escuadra(a, b):
    esquina = [b[0], a[1]]
    d = ruteo._metros(a, esquina) + ruteo._metros(esquina, b)
    return round(d * (1.10 if a[0] < b[0] else 1.0), 1)          # hacia el este: 10 % más


@pytest.fixture
def osrm(monkeypatch):
    falso = TablaFalsa()
    monkeypatch.setattr(ruteo, "_consultar", falso)
    monkeypatch.setattr(ruteo, "PAUSA_ENTRE_CONSULTAS_S", 0)
    return falso


def puntos(n):
    return [[round(-99.12 + 0.01 * math.cos(i), 6), round(19.48 + 0.01 * math.sin(i * 1.7), 6)] for i in range(n)]


@pytest.fixture
def analisis(con):
    a = con.execute(text("SELECT id_analisis FROM analisis_hdbscan WHERE vigente")).scalar()
    if a is None:
        pytest.skip("no hay análisis vigente: corre primero python crear_analisis.py")
    con.execute(text("DELETE FROM matriz_calles WHERE id_analisis = :a"), {"a": a})   # se deshace al final
    return a


# ------------------------------------------------------------------ cliente «table»
def test_hasta_100_hotspots_es_una_sola_consulta(osrm):
    d, t = M.tabla(puntos(12))
    assert len(osrm.consultas) == 1 and "/table/v1/driving/" in osrm.consultas[0]
    assert "annotations=distance,duration" in osrm.consultas[0]
    assert d.shape == (12, 12) and t.shape == (12, 12)
    assert not np.allclose(d, d.T)                              # ida ≠ vuelta


def test_con_muchos_hotspots_se_pide_en_bloques_y_da_lo_mismo(osrm, monkeypatch):
    c = puntos(11)
    completa, _ = M.tabla(c)
    monkeypatch.setattr(M, "MAX_COORDENADAS", 8)
    monkeypatch.setattr(M, "BLOQUE", 4)
    osrm.consultas.clear()
    por_bloques, _ = M.tabla(c)
    assert len(osrm.consultas) == 9                             # 3 bloques de orígenes × 3 de destinos
    assert all(len(re.search(r"/table/v1/\w+/([^?]+)", u).group(1).split(";")) <= 8 for u in osrm.consultas)
    assert np.allclose(por_bloques, completa)


def test_si_osrm_falla_avisa(monkeypatch):
    monkeypatch.setattr(ruteo, "_consultar", TablaFalsa(codigo="TooBig"))
    with pytest.raises(ruteo.RuteoNoDisponible):
        M.tabla(puntos(5))


def test_los_pares_sin_camino_se_penalizan():
    recta = np.array([[0, 100, 200], [100, 0, 150], [200, 150, 0]], dtype=float)
    dist = np.array([[0, 130, np.nan], [140, 0, 190], [260, 200, 0]], dtype=float)
    dur = dist / 10
    d, t, n = M._completar(dist, dur, recta)
    assert n == 1 and d[0, 2] == M.PENALIZACION * 200 and not np.isnan(d).any() and not np.isnan(t).any()
    assert d[1, 0] == 140                                        # lo demás no se toca


# ------------------------------------------------------------------ medir
def test_mejor_sentido_toma_el_recorrido_mas_corto():
    D = np.array([[0, 1, 9], [9, 0, 1], [1, 9, 0]], dtype=float)  # 0→1→2→0 = 3; al revés = 27
    assert M.largo([0, 1, 2], D) == 3 and M.largo([2, 1, 0], D) == 27
    assert M.mejor_sentido([0, 1, 2], D) == (3, False)
    assert M.mejor_sentido([2, 1, 0], D) == (3, True)


# ------------------------------------------------------------------ con la base
def test_se_pide_una_vez_por_analisis_y_se_reutiliza(con, analisis, osrm):
    m = M.obtener(con, analisis)
    n = con.execute(text("SELECT count(*) FROM hotspot WHERE id_analisis = :a"), {"a": analisis}).scalar()
    assert m.nueva and len(m.ids) == n and m.distancias.shape == (n, n) and len(osrm.consultas) >= 1
    pedidas = len(osrm.consultas)
    otra = M.obtener(con, analisis)
    assert not otra.nueva and len(osrm.consultas) == pedidas      # ya no se consulta a OSRM
    assert np.allclose(otra.distancias, m.distancias, atol=0.1) and otra.ids == m.ids
    fila = con.execute(text("SELECT proveedor, perfil, sin_camino FROM matriz_calles WHERE id_analisis = :a"),
                       {"a": analisis}).mappings().one()
    assert fila["proveedor"].startswith("osrm:") and fila["perfil"] == ruteo.RUTEO_PERFIL and fila["sin_camino"] == 0


def test_sin_pedir_no_consulta_y_si_osrm_falla_no_guarda_nada(con, analisis, monkeypatch):
    falso = TablaFalsa(codigo="NoTable")
    monkeypatch.setattr(ruteo, "_consultar", falso)
    assert M.obtener(con, analisis, pedir=False) is None and falso.consultas == []
    with pytest.raises(ruteo.RuteoNoDisponible):
        M.obtener(con, analisis)
    assert con.execute(text("SELECT count(*) FROM matriz_calles WHERE id_analisis = :a"), {"a": analisis}).scalar() == 0


def test_si_los_hotspots_no_coinciden_se_vuelve_a_pedir(con, analisis, osrm):
    M.obtener(con, analisis)
    con.execute(text("UPDATE matriz_calles SET ids = '[1, 2, 3]'::jsonb WHERE id_analisis = :a"), {"a": analisis})
    assert M.obtener(con, analisis, pedir=False) is None
    assert M.obtener(con, analisis).nueva


def test_submatrices_de_un_sector(con, analisis, osrm):
    m = M.obtener(con, analisis)
    sector = m.ids[::3][:6]
    s = M.Matriz.submatrices(m, sector)
    assert set(s) == set(M.METRICAS) and all(x.shape == (len(sector), len(sector)) for x in s.values())
    i, j = m.ids.index(sector[1]), m.ids.index(sector[4])
    assert s["calles"][1, 4] == m.distancias[i, j] and s["calles"][4, 1] == m.distancias[j, i]
    assert np.allclose(s["calles_promedio"], s["calles_promedio"].T)
    assert np.allclose(s["recta"], s["recta"].T) and (s["calles"] + 1e-6 >= s["recta"]).all()
    with pytest.raises(M.SinHotspots):
        m.submatrices([-1])


def test_rodeo_resume_la_matriz(con, analisis, osrm):
    r = M.rodeo(M.obtener(con, analisis))
    if r["pares"]:
        assert 1.0 <= r["p10"] <= r["mediana"] <= r["p90"] and r["asimetria_mediana_pct"] > 0


def test_analisis_inexistente(con):
    with pytest.raises(M.SinHotspots):
        M.obtener(con, 999_999_999)


def test_las_columnas_nuevas_de_ejecucion_ag(con):
    columnas = set(con.execute(text("""
        SELECT column_name FROM information_schema.columns WHERE table_name = 'ejecucion_ag'
    """)).scalars())
    assert {"metrica", "distancia_recta_m", "comparacion"} <= columnas
    sin_metrica = con.execute(text("SELECT count(*) FROM ejecucion_ag WHERE metrica IS NULL")).scalar()
    assert sin_metrica == 0
