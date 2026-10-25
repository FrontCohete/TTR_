"""Trazo por calles (etapa 6), SIN internet: el servidor OSRM se reemplaza por uno falso.

El falso responde como OSRM: cada tramo va «en escuadra» (primero este–oeste y luego norte–sur),
así que por calles siempre mide más que en línea recta, igual que en la ciudad real.
Las pruebas con base de datos corren dentro de la transacción que se deshace (fixture `con`).
"""
import math
import re

import httpx
import pytest
from sqlalchemy import text

from app.servicios import ruteo
from app.servicios import agentes as S
from pruebas.test_agentes import cliente, con, corridos, particion  # noqa: F401  (fixtures)


def _m(a, b):
    return ruteo._metros(a, b)


class OSRMFalso:
    def __init__(self, codigo="Ok"):
        self.consultas = []
        self.codigo = codigo

    def __call__(self, url):
        self.consultas.append(url)
        if self.codigo != "Ok":
            return {"code": self.codigo, "message": "sin camino"}
        puntos = re.search(r"/route/v1/\w+/([^?]+)", url).group(1)
        coords = [[float(x) for x in p.split(",")] for p in puntos.split(";")]
        geometria, legs = [coords[0]], []
        for a, b in zip(coords, coords[1:]):
            esquina = [b[0], a[1]]
            geometria += [esquina, b]
            d = _m(a, esquina) + _m(esquina, b)
            legs.append({"distance": d, "duration": d / 8.0})
        return {"code": "Ok", "routes": [{"geometry": {"coordinates": geometria}, "legs": legs}],
                "waypoints": [{"location": c} for c in coords]}


@pytest.fixture
def osrm(monkeypatch):
    falso = OSRMFalso()
    monkeypatch.setattr(ruteo, "_consultar", falso)
    monkeypatch.setattr(ruteo, "PAUSA_ENTRE_CONSULTAS_S", 0)
    return falso


def puntos(n, cerrar=True):
    c = [[round(-99.12 + 0.01 * math.cos(i), 6), round(19.48 + 0.01 * math.sin(i * 1.7), 6)] for i in range(n)]
    return c + [c[0]] if cerrar else c


# ------------------------------------------------------------------ cliente
def test_un_bloque_pasa_por_todas_las_paradas(osrm):
    c = puntos(5)
    t = ruteo.trazar(c)
    assert len(osrm.consultas) == 1 and "/route/v1/driving/" in osrm.consultas[0]
    assert len(t["indices_paradas"]) == len(c) and len(t["tramos"]) == len(c) - 1
    assert t["indices_paradas"] == sorted(t["indices_paradas"])
    assert all(t["geometria"][i] == p for i, p in zip(t["indices_paradas"], c))
    recta = sum(_m(a, b) for a, b in zip(c, c[1:]))
    assert t["distancia_m"] > recta                                   # por calles mide más
    assert t["distancia_m"] == pytest.approx(sum(x["distancia_m"] for x in t["tramos"]), abs=0.1)


def test_rutas_largas_se_piden_en_bloques_sin_huecos(osrm):
    c = puntos(93)                                                    # el grafo completo: 94 paradas
    t = ruteo.trazar(c)
    assert len(osrm.consultas) == math.ceil((len(c) - 1) / (ruteo.MAX_PARADAS_POR_CONSULTA - 1))
    assert all(len(u.split(";")) <= ruteo.MAX_PARADAS_POR_CONSULTA for u in osrm.consultas)
    assert len(t["indices_paradas"]) == len(c) and len(t["tramos"]) == len(c) - 1
    assert all(t["geometria"][i] == p for i, p in zip(t["indices_paradas"], c))
    assert all(a != b for a, b in zip(t["geometria"], t["geometria"][1:]))   # sin vértices repetidos en las uniones
    largo = sum(_m(a, b) for a, b in zip(t["geometria"], t["geometria"][1:]))
    assert largo == pytest.approx(t["distancia_m"], rel=1e-6)


def test_un_solo_hotspot_no_consulta(osrm):
    t = ruteo.trazar([[-99.1, 19.5], [-99.1, 19.5]])
    assert osrm.consultas == [] and t["distancia_m"] == 0 and t["indices_paradas"] == [0, 1]


def test_sin_camino_es_ruteo_no_disponible(monkeypatch):
    monkeypatch.setattr(ruteo, "_consultar", OSRMFalso("NoRoute"))
    with pytest.raises(ruteo.RuteoNoDisponible, match="NoRoute"):
        ruteo.trazar(puntos(3))


def test_errores_de_red_son_ruteo_no_disponible(monkeypatch):
    def caida(*a, **k):
        raise httpx.ConnectError("sin internet")
    monkeypatch.setattr(httpx, "get", caida)
    with pytest.raises(ruteo.RuteoNoDisponible, match="No se pudo contactar"):
        ruteo._consultar("https://ejemplo/route")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(429, json={}))
    with pytest.raises(ruteo.RuteoNoDisponible, match="esperar"):
        ruteo._consultar("https://ejemplo/route")


# ------------------------------------------------------------------ base de datos
@pytest.fixture
def con_tabla(con):
    if con.execute(text("SELECT to_regclass('ruta_calles')")).scalar() is None:
        pytest.skip("falta la tabla ruta_calles: aplica database/06_ruta_calles.sql")
    return con


def test_se_pide_una_vez_y_se_guarda(con_tabla, corridos, osrm):
    e = corridos[0]["id_ejecucion"]
    r = ruteo.ruta_calles(con_tabla, e)
    n = len(osrm.consultas)
    assert n >= 1
    assert ruteo.ruta_calles(con_tabla, e) == r and len(osrm.consultas) == n      # la segunda vez sale de la base
    p = r["properties"]
    a = S.agente(con_tabla, e)
    assert p["distancia_recta_m"] == pytest.approx(a["mejor_distancia"])
    assert p["distancia_m"] > p["distancia_recta_m"] and p["diferencia_pct"] > 0
    assert len(p["indices_paradas"]) == len(p["hotspots"]) + 1                   # ruta cerrada: regresa
    assert p["tramos"][0]["desde"] == p["hotspots"][0] and p["tramos"][-1]["hasta"] == p["hotspots"][0]
    assert "OpenStreetMap" in p["atribucion"]


def test_api_ruta_calles(cliente, corridos, con_tabla, osrm, monkeypatch):
    e = corridos[0]["id_ejecucion"]
    r = cliente.get(f"/api/agentes/{e}/ruta-calles")
    assert r.status_code == 200 and r.json()["geometry"]["type"] == "LineString"
    assert cliente.get("/api/agentes/999999999/ruta-calles").status_code == 404
    otra = corridos[1]["id_ejecucion"]                                          # aún sin trazo guardado
    monkeypatch.setattr(ruteo, "_consultar", OSRMFalso("NoRoute"))
    r = cliente.get(f"/api/agentes/{otra}/ruta-calles")
    assert r.status_code == 503 and "línea recta" in r.json()["detail"]
