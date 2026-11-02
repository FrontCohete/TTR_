"""Versión solo-calles (1 nov 2026): mutación mixta, pulido final y agentes que solo usan calles con sentido.

Sin internet: la matriz por calles es la inventada de test_agentes (fixture `particion`).
Las pruebas con base de datos corren dentro de la transacción que se deshace (fixture `con`).
"""
import numpy as np
import pytest
from sqlalchemy import text

from app.servicios import agentes as S
from app.servicios import genetico as AG
from app.servicios import matriz_calles as M
from app.servicios import ruteo
from pruebas.test_agentes import CHICO, MotorDePrueba, cliente, con, corridos, particion  # noqa: F401
from pruebas.test_matriz_calles import TablaFalsa


def asimetrica(n, semilla):
    """Distancias «por calles» inventadas: rodeo distinto por par y calles de un sentido."""
    rng = np.random.default_rng(semilla)
    xy = rng.random((n, 2)) * 5000
    recta = np.hypot(*(xy[:, None, :] - xy[None, :, :]).transpose(2, 0, 1))
    D = recta * rng.uniform(1.2, 1.7, (n, n)) * (1 + rng.choice([0, 0.1, 0.3], size=(n, n)))
    np.fill_diagonal(D, 0)
    return D


# ------------------------------------------------------------------ operadores
def test_insercion_y_mixta():
    p = [10, 11, 12, 13, 14, 15]
    assert AG.insertar(p, 1, 4) == [10, 12, 13, 14, 11, 15]                 # 11 se mueve, nada se voltea
    assert AG.tipo_mixta(1, 3) == "inversion" and AG.tipo_mixta(1, 4) == "insercion"
    assert AG.mixta(p, 1, 3) == AG.invertir(p, 1, 3) and AG.mixta(p, 1, 4) == AG.insertar(p, 1, 4)


@pytest.mark.parametrize("op", AG.MUTACIONES)
def test_las_cuatro_mutaciones_son_validas_y_dan_permutaciones(op):
    D = asimetrica(12, 1)
    r = AG.ejecutar_ag(list(range(12)), D, AG.Parametros(tam_poblacion=20, n_generaciones=30, op_mutacion=op))
    assert sorted(r.ruta_optima) == list(range(12))
    assert r.mejor_distancia == pytest.approx(AG.largo(r.ruta_optima, D), abs=0.1)
    with pytest.raises(AG.ParametrosInvalidos, match="mixta"):
        AG.Parametros(op_mutacion="otra").validar()


def test_la_mixta_anota_el_tipo_real_de_cada_mutacion():
    r = AG.ejecutar_ag(list(range(15)), asimetrica(15, 2), AG.Parametros(tam_poblacion=20, n_generaciones=10))
    tipos = set()
    for g in range(1, 11):
        for m in r.operaciones(g)["mutaciones"]:
            a, b = m["posiciones"]
            assert m["tipo"] == AG.tipo_mixta(a, b)
            tipos.add(m["tipo"])
    assert tipos == {"inversion", "insercion"}


def test_la_mixta_es_la_misma_del_experimento(monkeypatch):
    """experimento_mutacion.py probó la mixta poniéndola en lugar del intercambio: debe dar lo mismo."""
    D = asimetrica(25, 3)
    p = AG.Parametros(tam_poblacion=30, n_generaciones=80, semilla=5)
    nueva = AG.ejecutar_ag(list(range(25)), D, p, registro=False)
    monkeypatch.setattr(AG, "OPERADOR_MUTACION", {**AG.OPERADOR_MUTACION, "swap": AG.mixta})
    vieja = AG.ejecutar_ag(list(range(25)), D, AG.Parametros(tam_poblacion=30, n_generaciones=80, semilla=5,
                                                              op_mutacion="swap"), registro=False)
    assert nueva.ruta_optima == vieja.ruta_optima and nueva.mejor_distancia == vieja.mejor_distancia


# ------------------------------------------------------------------ pulido
@pytest.mark.parametrize("cerrada", [True, False])
def test_el_pulido_nunca_alarga_y_conserva_los_hotspots(cerrada):
    for semilla in range(6):
        D = asimetrica(14, semilla)
        orden = list(np.random.default_rng(semilla).permutation(14))
        pulida, movs = AG.pulir(orden, D, cerrada)
        antes, despues = AG.largo(orden, D, cerrada), AG.largo(pulida, D, cerrada)
        assert sorted(pulida) == list(range(14))
        assert despues <= antes + 1e-6
        assert sum(m["ahorro_m"] for m in movs) == pytest.approx(antes - despues, abs=0.5)
        assert all(m["ahorro_m"] > 0 and 1 <= len(m["segmento"]) <= 3 for m in movs)


def test_el_pulido_corrige_un_hotspot_fuera_de_lugar():
    D = np.abs(np.subtract.outer(np.arange(6.0), np.arange(6.0))) * 1000      # puntos en fila, 1 km entre vecinos
    pulida, movs = AG.pulir([0, 2, 1, 3, 4, 5], D, cerrada=True)
    assert AG.largo(pulida, D) == pytest.approx(10_000) and len(movs) >= 1


def test_pulido_de_ruta_abierta_puede_mover_al_inicio_o_al_final():
    D = np.abs(np.subtract.outer(np.arange(6.0), np.arange(6.0))) * 1000
    pulida, movs = AG.pulir([1, 2, 3, 4, 5, 0], D, cerrada=False)
    assert AG.largo(pulida, D, cerrada=False) == pytest.approx(5_000)
    assert any(None in m["entre"] for m in movs)


def test_pocos_hotspots_no_se_pulen():
    assert AG.pulir([2, 0, 1], asimetrica(3, 0)) == ([2, 0, 1], [])


# ------------------------------------------------------------------ agentes
def matriz_vigente(con):
    a = con.execute(text("SELECT id_analisis FROM analisis_hdbscan WHERE vigente")).scalar()
    return M.obtener(con, a, pedir=False)


def test_el_agente_optimiza_por_calles_con_sentido_y_pule(con, corridos):
    m = matriz_vigente(con)
    for c in corridos:
        a = S.agente(con, c["id_ejecucion"])
        assert a["metrica"] == "calles" and a["parametros"]["op_mutacion"] == "mixta"
        ruta = [int(h) for h in a["ruta_optima"]]
        por_calles = AG.largo(list(range(len(ruta))), m.submatrices(ruta)["calles"])        # con sentido
        assert por_calles == pytest.approx(a["mejor_distancia"], abs=1)
        ids, recta, _ = S.datos_grafo(con, a["id_grafo"])
        pos = {h: i for i, h in enumerate(ids)}
        assert AG.largo([pos[h] for h in ruta], recta) == pytest.approx(a["distancia_recta_m"], abs=1)
        pul = a["pulido"]
        assert pul["despues_m"] <= pul["antes_m"] + 0.1 and pul["despues_m"] == pytest.approx(a["mejor_distancia"], abs=0.1)
        assert sum(x["ahorro_m"] for x in pul["movimientos"]) <= pul["antes_m"] - pul["despues_m"] + 0.5
        assert all(set(x["segmento"]) <= set(ruta) for x in pul["movimientos"])


def test_distancias_es_la_vara_del_genetico(cliente, corridos):
    for c in corridos:
        d = cliente.get(f"/api/agentes/{c['id_ejecucion']}/distancias").json()
        assert d["metrica"] == "calles"
        D = np.array(d["distancias_m"])
        assert not np.allclose(D, D.T)                                                   # ida ≠ vuelta
        pos = {h: i for i, h in enumerate(d["ids"])}
        for g in cliente.get(f"/api/agentes/{c['id_ejecucion']}/generaciones").json()[::5]:
            assert AG.largo([pos[h] for h in g["mejor_permutacion"]], D) == pytest.approx(g["mejor_fitness"], abs=1)


def test_un_agente_viejo_en_linea_recta_sigue_funcionando(con, corridos):
    e = corridos[0]["id_ejecucion"]
    con.execute(text("UPDATE ejecucion_ag SET metrica = 'recta' WHERE id_ejecucion = :e"), {"e": e})
    d = S.distancias(con, e)
    assert d["metrica"] == "recta" and np.allclose(np.array(d["distancias_m"]), np.array(d["distancias_m"]).T)


def test_sin_calles_no_se_crean_agentes(cliente, con, particion, monkeypatch):
    a = con.execute(text("SELECT id_analisis FROM analisis_hdbscan WHERE vigente")).scalar()
    con.execute(text("DELETE FROM matriz_calles WHERE id_analisis = :a"), {"a": a})
    monkeypatch.setattr(ruteo, "_consultar", TablaFalsa(codigo="NoTable"))           # OSRM «no responde»
    antes = con.execute(text("SELECT count(*) FROM ejecucion_ag")).scalar()
    r = cliente.post("/api/agentes", json={"id_particion": particion["id_particion"]})
    assert r.status_code == 503 and "distancias por calles" in r.json()["detail"]
    assert con.execute(text("SELECT count(*) FROM ejecucion_ag")).scalar() == antes    # nada a medias


def test_una_tanda_sin_matriz_queda_en_error_y_nunca_en_linea_recta(con, particion, monkeypatch):
    creadas = S.crear_ejecuciones(con, particion["id_particion"], CHICO)
    a = con.execute(text("SELECT id_analisis FROM analisis_hdbscan WHERE vigente")).scalar()
    con.execute(text("DELETE FROM matriz_calles WHERE id_analisis = :a"), {"a": a})
    monkeypatch.setattr(ruteo, "_consultar", TablaFalsa(codigo="NoTable"))
    S.ejecutar_agentes([c["id_ejecucion"] for c in creadas], motor=MotorDePrueba(con))
    for c in creadas:
        x = S.agente(con, c["id_ejecucion"])
        assert x["estado"] == "error" and "distancias por calles" in x["mensaje_error"]


def test_api_mutacion_por_omision_y_las_nuevas(cliente, particion):
    for op, tipos in (("mixta", {"inversion", "insercion"}), ("insercion", {"insercion"})):
        r = cliente.post("/api/agentes", json={"id_particion": particion["id_particion"],
                                                "parametros": {"tam_poblacion": 20, "n_generaciones": 10, "tam_torneo": 3,
                                                               "op_mutacion": op}})
        assert r.status_code == 202
        e = r.json()["ejecuciones"][1]["id_ejecucion"]
        a = cliente.get(f"/api/agentes/{e}").json()
        assert a["parametros"]["op_mutacion"] == op and a["pulido"] is not None
        vistos = set()
        for g in cliente.get(f"/api/agentes/{e}/generaciones").json()[1:]:
            vistos |= {m["tipo"] for m in cliente.get(f"/api/generaciones/{g['id_generacion']}/individuos").json()
                       ["operaciones"]["mutaciones"]}
        assert vistos <= tipos and vistos
    assert cliente.post("/api/agentes", json={"id_particion": particion["id_particion"],
                                              "parametros": {"op_mutacion": "otra"}}).status_code == 422
