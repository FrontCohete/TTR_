"""Agentes (etapa 5): crear, ejecutar, guardar y consultar, contra la base real.

Todo corre dentro de una transacción que se deshace al final (fixture `con`): no queda ninguna
ejecución guardada. Se usan parámetros chicos (20 rutas × 15 generaciones) para que sea rápido.
"""
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.rutas import agentes as R
from app.servicios import agentes as S
from app.servicios import genetico as AG
from app.servicios import particion as P
from app.servicios.particion import haversine
from pruebas.test_insercion import con  # noqa: F401  (fixture: conexión que se deshace)

CHICO = AG.Parametros(tam_poblacion=20, n_generaciones=15)


class MotorDePrueba:
    """Hace las veces del engine: cada begin() es un punto de guardado dentro de la transacción de la prueba."""
    def __init__(self, con):
        self.con = con

    @contextmanager
    def begin(self):
        with self.con.begin_nested():
            yield self.con


@pytest.fixture
def particion(con):
    if con.execute(text("SELECT count(*) FROM analisis_hdbscan WHERE vigente")).scalar() == 0:
        pytest.skip("no hay análisis vigente: corre primero python crear_analisis.py")
    con.execute(text("UPDATE ejecucion_ag SET estado = 'error' WHERE estado IN ('pendiente', 'ejecutando')"))
    # los agentes reales se dan por liberados (solo en esta transacción): así las pruebas no
    # borran cientos de miles de rutas cada vez y siguen siendo rápidas
    con.execute(text("UPDATE ejecucion_ag SET rutas_borradas = true WHERE NOT rutas_borradas"))
    return P.nueva_particion(con, 2)


@pytest.fixture
def corridos(con, particion):
    creadas = S.crear_ejecuciones(con, particion["id_particion"], CHICO)
    S.ejecutar_agentes([c["id_ejecucion"] for c in creadas], motor=MotorDePrueba(con))
    return creadas


# ------------------------------------------------------------------ servicio
def test_una_ejecucion_por_grafo_en_pendiente(con, particion):
    creadas = S.crear_ejecuciones(con, particion["id_particion"], CHICO)
    assert [c["numero"] for c in creadas] == [1, 2]
    assert {c["id_grafo"] for c in creadas} == {g["id_grafo"] for g in particion["grafos"]}
    assert all(S.agente(con, c["id_ejecucion"])["estado"] == "pendiente" for c in creadas)


def test_no_se_lanzan_dos_tandas_a_la_vez(con, particion):
    S.crear_ejecuciones(con, particion["id_particion"], CHICO)
    with pytest.raises(S.Ocupado):
        S.crear_ejecuciones(con, particion["id_particion"], CHICO)


def test_particion_inexistente_y_parametros_invalidos(con, particion):
    with pytest.raises(S.NoEncontrado):
        S.crear_ejecuciones(con, 999_999_999, CHICO)
    with pytest.raises(AG.ParametrosInvalidos):
        S.crear_ejecuciones(con, particion["id_particion"], AG.Parametros(tam_poblacion=500, n_generaciones=2000))


def test_ejecutar_guarda_todo(con, corridos):
    for c in corridos:
        a = S.agente(con, c["id_ejecucion"])
        assert a["estado"] == "terminado" and a["avance"] == 100
        assert a["parametros"]["n_elite"] == 1 and a["parametros"]["tam_poblacion"] == 20
        gens = S.generaciones(con, c["id_ejecucion"])
        assert [g["numero"] for g in gens] == list(range(16))
        assert min(g["mejor_fitness"] for g in gens) == pytest.approx(a["mejor_distancia"], abs=0.2)
        filas = con.execute(text("""
            SELECT count(*) FROM individuo JOIN generacion USING (id_generacion) WHERE id_ejecucion = :e
        """), {"e": c["id_ejecucion"]}).scalar()
        assert filas == 20 * 16


def test_individuos_cumplen_el_contrato(con, corridos):
    gens = S.generaciones(con, corridos[0]["id_ejecucion"])
    g0 = S.individuos(con, gens[0]["id_generacion"])
    assert g0["numero"] == 0 and g0["operaciones"] is None
    assert all(i["origen"] == "aleatorio" and i["padre_1"] is None for i in g0["individuos"])
    for k in (1, 15):
        g = S.individuos(con, gens[k]["id_generacion"])
        previa = S.individuos(con, gens[k - 1]["id_generacion"])
        assert g["numero"] == k and [i["posicion"] for i in g["individuos"]] == list(range(20))
        ops = g["operaciones"]
        assert len(ops["torneos"]) == 2 * 19 and len(ops["cruces"]) == 19
        elite = g["individuos"][-1]
        assert elite["origen"] == "elite" and elite["padre_2"] is None
        assert elite["permutacion"] == previa["individuos"][elite["padre_1"]]["permutacion"]
        for c in ops["cruces"]:                         # padres en posiciones, iguales a las del cruce
            i = g["individuos"][c["hijo"]]
            assert [i["padre_1"], i["padre_2"]] == c["padres"]
        assert all(isinstance(h, int) for i in g["individuos"] for h in i["permutacion"])


def test_ruta_cerrada_empieza_en_la_mayor_carga_y_mide_lo_reportado(con, corridos):
    for c in corridos:
        r = S.ruta(con, c["id_ejecucion"])
        coords, hs = r["geometry"]["coordinates"], r["properties"]["hotspots"]
        assert coords[0] == coords[-1] and len(hs) == len(coords) - 1
        info = con.execute(text("""
            SELECT id_hotspot, n_puntos * indice_gravedad AS carga FROM hotspot WHERE id_hotspot = ANY(:h)
        """), {"h": hs}).all()
        assert hs[0] == max(info, key=lambda x: x.carga).id_hotspot
        largo = sum(haversine(coords[i][1], coords[i][0], coords[i + 1][1], coords[i + 1][0]) for i in range(len(coords) - 1))
        assert largo == pytest.approx(r["properties"]["distancia_m"], abs=5)       # coordenadas redondeadas a 6 decimales
        assert r["properties"]["orden"][0].startswith("H-")


def operaciones_guardadas(con, id_ejecucion):
    return con.execute(text(
        "SELECT count(*) FROM generacion WHERE id_ejecucion = :e AND operaciones IS NOT NULL"
    ), {"e": id_ejecucion}).scalar()


def test_una_tanda_nueva_libera_el_detalle_de_todas_las_anteriores(con, particion, corridos):
    con.execute(text("UPDATE ejecucion_ag SET estado = 'terminado' WHERE estado IN ('pendiente', 'ejecutando')"))
    nuevas = S.crear_ejecuciones(con, particion["id_particion"], CHICO)
    S.ejecutar_agentes([nuevas[0]["id_ejecucion"]], motor=MotorDePrueba(con))
    for vieja in (c["id_ejecucion"] for c in corridos):                 # mismo grafo y el otro grafo
        a = S.agente(con, vieja)
        assert a["estado"] == "terminado" and a["mejor_distancia"] > 0 and a["ruta_optima"]   # el resumen se conserva
        assert len(S.generaciones(con, vieja)) == 16                    # la curva de aptitud también
        assert operaciones_guardadas(con, vieja) == 0
        with pytest.raises(S.NoEncontrado, match="más nueva"):
            S.individuos(con, S.generaciones(con, vieja)[3]["id_generacion"])
        assert S.ruta(con, vieja)["geometry"]["type"] == "LineString"   # Simular sigue funcionando
    nueva = nuevas[0]["id_ejecucion"]                                   # la tanda actual: completa
    assert S.individuos(con, S.generaciones(con, nueva)[3]["id_generacion"])["numero"] == 3
    assert operaciones_guardadas(con, nueva) == 15


def test_liberar_no_toca_la_tanda_actual_y_limpia_operaciones_sueltas(con, corridos):
    uno, dos = (c["id_ejecucion"] for c in corridos)
    # una corrida limpiada con la regla anterior: sin rutas pero con operaciones
    con.execute(text("UPDATE ejecucion_ag SET rutas_borradas = true WHERE id_ejecucion = :e"), {"e": uno})
    r = S.liberar_tandas_anteriores(con, [dos])
    assert r["individuos"] == 0                                          # «uno» ya estaba marcado: no se repite
    assert operaciones_guardadas(con, uno) == 0 and operaciones_guardadas(con, dos) == 15
    assert S.individuos(con, S.generaciones(con, dos)[1]["id_generacion"])["numero"] == 1
    assert S.liberar_tandas_anteriores(con, [dos])["generaciones"] == 0   # una segunda vez no hace nada


def test_un_agente_con_error_no_detiene_a_los_demas(con, particion, monkeypatch):
    creadas = S.crear_ejecuciones(con, particion["id_particion"], CHICO)
    original = S.datos_grafo

    def falla_el_primero(c, id_grafo):
        if id_grafo == creadas[0]["id_grafo"]:
            raise RuntimeError("grafo dañado")
        return original(c, id_grafo)

    monkeypatch.setattr(S, "datos_grafo", falla_el_primero)
    S.ejecutar_agentes([c["id_ejecucion"] for c in creadas], motor=MotorDePrueba(con))
    uno, dos = (S.agente(con, c["id_ejecucion"]) for c in creadas)
    assert uno["estado"] == "error" and "grafo dañado" in uno["mensaje_error"]
    assert dos["estado"] == "terminado"
    with pytest.raises(S.NoTerminado):
        S.ruta(con, creadas[0]["id_ejecucion"])


def test_recuperar_interrumpidos(con, particion):
    creadas = S.crear_ejecuciones(con, particion["id_particion"], CHICO)
    assert S.recuperar_interrumpidos(MotorDePrueba(con)) >= len(creadas)
    assert S.agente(con, creadas[0]["id_ejecucion"])["estado"] == "error"


# ------------------------------------------------------------------ API
@pytest.fixture
def cliente(con, monkeypatch):
    app.dependency_overrides[R.conexion] = lambda: con
    monkeypatch.setattr(R, "lanzar", lambda ids: S.ejecutar_agentes(ids, motor=MotorDePrueba(con)))
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_de_punta_a_punta(cliente, particion):
    r = cliente.post("/api/agentes", json={"id_particion": particion["id_particion"],
                                            "parametros": {"tam_poblacion": 20, "n_generaciones": 10, "tam_torneo": 3,
                                                           "prob_cruce": 0.9, "prob_mutacion": 0.5, "op_cruce": "OX",
                                                           "op_mutacion": "inversion", "semilla": 7, "ruta_cerrada": True}})
    assert r.status_code == 202
    ej = r.json()["ejecuciones"]
    assert set(ej[0]) >= {"id_ejecucion", "id_grafo", "numero", "estado"}
    a = cliente.get(f"/api/agentes/{ej[0]['id_ejecucion']}").json()
    assert a["estado"] == "terminado" and a["parametros"]["tam_torneo"] == 3 and a["parametros"]["ruta_cerrada"] is True
    gens = cliente.get(f"/api/agentes/{ej[0]['id_ejecucion']}/generaciones").json()
    assert len(gens) == 11 and gens[4]["numero"] == 4
    ind = cliente.get(f"/api/generaciones/{gens[4]['id_generacion']}/individuos").json()
    assert ind["numero"] == 4 and len(ind["operaciones"]["cruces"]) == 19
    ruta = cliente.get(f"/api/agentes/{ej[0]['id_ejecucion']}/ruta").json()
    assert ruta["geometry"]["type"] == "LineString"
    s = cliente.post("/api/simulaciones", json={"id_ejecucion": ej[0]["id_ejecucion"], "distancia_total": 1234.5, "duracion_s": 9.5})
    assert s.status_code == 201 and s.json()["id_ejecucion"] == ej[0]["id_ejecucion"]


@pytest.mark.parametrize("parametros", [
    {"tam_poblacion": 500, "n_generaciones": 2000},
    {"tam_poblacion": ""},
    {"op_cruce": "XYZ"},
])
def test_api_parametros_invalidos_dan_422(cliente, particion, parametros):
    r = cliente.post("/api/agentes", json={"id_particion": particion["id_particion"], "parametros": parametros})
    assert r.status_code == 422


def test_api_404_y_409(cliente, particion):
    assert cliente.get("/api/agentes/999999999").status_code == 404
    assert cliente.get("/api/generaciones/999999999/individuos").status_code == 404
    assert cliente.post("/api/agentes", json={"id_particion": 999_999_999}).status_code == 404
    creadas = S.crear_ejecuciones(cliente.app.dependency_overrides[R.conexion](), particion["id_particion"], CHICO)
    r = cliente.get(f"/api/agentes/{creadas[0]['id_ejecucion']}/ruta")
    assert r.status_code == 409 and isinstance(r.json()["detail"], str)
    assert cliente.post("/api/agentes", json={"id_particion": particion["id_particion"]}).status_code == 409
