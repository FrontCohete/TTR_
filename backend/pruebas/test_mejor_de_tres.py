"""Etapa 7 · «la mejor de tres»: cada agente prueba A (recta), B (calles) y C (calles promedio).

Sin internet: la matriz por calles es la inventada de test_agentes (fixture `particion`).
Todo corre dentro de la transacción que se deshace (fixture `con`).
"""
import numpy as np
import pytest
from sqlalchemy import text

from app.servicios import agentes as S
from app.servicios import matriz_calles as M
from app.servicios import ruteo
from pruebas.test_agentes import CHICO, MotorDePrueba, cliente, con, corridos, particion  # noqa: F401
from pruebas.test_matriz_calles import TablaFalsa


def matriz_vigente(con):
    a = con.execute(text("SELECT id_analisis FROM analisis_hdbscan WHERE vigente")).scalar()
    return M.obtener(con, a, pedir=False)


def test_cada_agente_compara_las_tres_y_gana_la_mas_corta(con, corridos):
    for c in corridos:
        a = S.agente(con, c["id_ejecucion"])
        comp = a["comparacion"]
        vs = comp["variantes"]
        assert [v["variante"] for v in vs] == ["A", "B", "C"] and comp["aviso"] is None
        assert [v["metrica"] for v in vs] == list(M.METRICAS)
        gano = [v for v in vs if v["ganadora"]]
        assert len(gano) == 1 and gano[0]["variante"] == comp["ganadora"]
        assert gano[0]["distancia_calles_m"] == min(v["distancia_calles_m"] for v in vs)
        assert gano[0]["distancia_calles_m"] <= vs[0]["distancia_calles_m"]          # nunca peor que A
        assert a["metrica"] == gano[0]["metrica"]
        assert a["mejor_distancia"] == pytest.approx(gano[0]["distancia_calles_m"], abs=0.1)
        assert a["distancia_recta_m"] == pytest.approx(gano[0]["distancia_recta_m"], abs=0.1)
        assert a["duracion_s"] == pytest.approx(sum(v["duracion_s"] for v in vs), abs=0.01)


def test_la_ruta_guardada_mide_por_calles_lo_reportado(con, corridos):
    m = matriz_vigente(con)
    for c in corridos:
        a = S.agente(con, c["id_ejecucion"])
        ruta = [int(h) for h in a["ruta_optima"]]
        D = m.submatrices(ruta)["calles"]                       # en el orden de la ruta: 0, 1, 2…
        assert M.largo(list(range(len(ruta))), D) == pytest.approx(a["mejor_distancia"], abs=1)


def test_la_misma_semilla_da_lo_mismo(con, particion, corridos):
    con.execute(text("UPDATE ejecucion_ag SET estado = 'terminado' WHERE estado IN ('pendiente', 'ejecutando')"))
    otra = S.crear_ejecuciones(con, particion["id_particion"], CHICO)
    S.ejecutar_agentes([o["id_ejecucion"] for o in otra], motor=MotorDePrueba(con))
    for x, y in zip(corridos, otra):
        a, b = S.agente(con, x["id_ejecucion"]), S.agente(con, y["id_ejecucion"])
        assert a["ruta_optima"] == b["ruta_optima"] and a["metrica"] == b["metrica"]
        assert [v["distancia_calles_m"] for v in a["comparacion"]["variantes"]] == \
               [v["distancia_calles_m"] for v in b["comparacion"]["variantes"]]


def test_sin_matriz_corre_solo_a_y_lo_avisa(con, particion, monkeypatch):
    a = con.execute(text("SELECT id_analisis FROM analisis_hdbscan WHERE vigente")).scalar()
    con.execute(text("DELETE FROM matriz_calles WHERE id_analisis = :a"), {"a": a})
    monkeypatch.setattr(ruteo, "_consultar", TablaFalsa(codigo="NoTable"))         # OSRM «no responde»
    creadas = S.crear_ejecuciones(con, particion["id_particion"], CHICO)
    S.ejecutar_agentes([c["id_ejecucion"] for c in creadas], motor=MotorDePrueba(con))
    for c in creadas:
        x = S.agente(con, c["id_ejecucion"])
        assert x["estado"] == "terminado" and x["metrica"] == "recta"
        comp = x["comparacion"]
        assert [v["variante"] for v in comp["variantes"]] == ["A"] and "línea recta" in comp["aviso"]
        assert comp["variantes"][0]["distancia_calles_m"] is None
        assert x["mejor_distancia"] == pytest.approx(x["distancia_recta_m"], abs=0.1)
        assert S.distancias(con, c["id_ejecucion"])["metrica"] == "recta"           # Rutas sigue funcionando


@pytest.mark.parametrize("calles, gana", [
    ((1000.2, 1000.4, 1000.1), "A"),        # empate al metro: A
    ((1001, 1000.4, 1000.1), "C"),          # B y C empatan (1000): C
    ((1001, 999.4, 1000.1), "B"),           # B más corta (999 contra 1000)
    ((990, 995, 999), "A"),
])
def test_desempate(calles, gana):
    vs = [{"variante": v, "distancia_calles_m": d, "distancia_recta_m": 1} for v, d in zip("ABC", calles)]
    assert vs[S.elegir(vs)]["variante"] == gana


def test_la_matriz_de_la_tanda_se_pide_una_sola_vez(con, particion, monkeypatch):
    a = con.execute(text("SELECT id_analisis FROM analisis_hdbscan WHERE vigente")).scalar()
    con.execute(text("DELETE FROM matriz_calles WHERE id_analisis = :a"), {"a": a})
    falso = TablaFalsa()
    monkeypatch.setattr(ruteo, "_consultar", falso)
    creadas = S.crear_ejecuciones(con, particion["id_particion"], CHICO)
    S.ejecutar_agentes([c["id_ejecucion"] for c in creadas], motor=MotorDePrueba(con))
    assert len(falso.consultas) == 1                                    # ≤ 100 hotspots: una consulta
    assert all(S.agente(con, c["id_ejecucion"])["comparacion"]["aviso"] is None for c in creadas)


# ------------------------------------------------------------------ API
def test_api_agente_trae_la_comparacion(cliente, corridos):
    a = cliente.get(f"/api/agentes/{corridos[0]['id_ejecucion']}").json()
    assert {"metrica", "distancia_recta_m", "comparacion"} <= set(a)
    assert a["metrica"] in M.METRICAS and len(a["comparacion"]["variantes"]) == 3
    r = cliente.get(f"/api/agentes/{corridos[0]['id_ejecucion']}/ruta").json()["properties"]
    assert r["metrica"] == a["metrica"] and r["distancia_recta_m"] == a["distancia_recta_m"]


def test_api_distancias_es_la_vara_del_genetico(cliente, corridos):
    for c in corridos:
        e = c["id_ejecucion"]
        d = cliente.get(f"/api/agentes/{e}/distancias")
        assert d.status_code == 200
        d = d.json()
        a = cliente.get(f"/api/agentes/{e}").json()
        n = len(d["ids"])
        assert d["metrica"] == a["metrica"] and len(d["distancias_m"]) == n and all(len(f) == n for f in d["distancias_m"])
        # el mejor de cada generación mide, con esta matriz, lo que dice su aptitud
        gens = cliente.get(f"/api/agentes/{e}/generaciones").json()
        pos = {h: i for i, h in enumerate(d["ids"])}
        for g in (gens[0], gens[-1]):
            orden = [pos[h] for h in g["mejor_permutacion"]]
            assert M.largo(orden, np.array(d["distancias_m"])) == pytest.approx(g["mejor_fitness"], abs=1)


def test_api_distancias_404_y_409(cliente, con, particion):
    assert cliente.get("/api/agentes/999999999/distancias").status_code == 404
    creadas = S.crear_ejecuciones(con, particion["id_particion"], CHICO)              # todavía sin calcular
    assert cliente.get(f"/api/agentes/{creadas[0]['id_ejecucion']}/distancias").status_code == 409


# ------------------------------------------------------------------ forma de medir elegida (una sola)
@pytest.mark.parametrize("medir, letra", [("recta", "A"), ("calles", "B"), ("calles_promedio", "C")])
def test_una_sola_forma_de_medir(con, particion, medir, letra):
    creadas = S.crear_ejecuciones(con, particion["id_particion"], CHICO, medir)
    S.ejecutar_agentes([c["id_ejecucion"] for c in creadas], motor=MotorDePrueba(con))
    m = matriz_vigente(con)
    for c in creadas:
        a = S.agente(con, c["id_ejecucion"])
        assert a["estado"] == "terminado" and a["medir"] == medir and a["parametros"]["medir"] == medir
        assert a["metrica"] == medir                                   # aunque no sea la más corta
        comp = a["comparacion"]
        assert comp["medir"] == medir and comp["aviso"] is None
        assert [v["variante"] for v in comp["variantes"]] == [letra] and comp["variantes"][0]["ganadora"]
        assert a["mejor_distancia"] == pytest.approx(comp["variantes"][0]["distancia_calles_m"], abs=0.1)
        ruta = [int(h) for h in a["ruta_optima"]]
        assert M.largo(list(range(len(ruta))), m.submatrices(ruta)["calles"]) == pytest.approx(a["mejor_distancia"], abs=1)
        gens = S.generaciones(con, c["id_ejecucion"])
        assert min(g["mejor_fitness"] for g in gens) == pytest.approx(comp["variantes"][0]["fitness_m"], abs=0.2)
        assert S.distancias(con, c["id_ejecucion"])["metrica"] == medir


def test_la_misma_semilla_da_la_misma_ruta_sola_o_dentro_de_las_tres(con, particion, corridos):
    """B solo es exactamente la B que compitió en «la mejor de tres» (misma semilla)."""
    con.execute(text("UPDATE ejecucion_ag SET estado = 'terminado' WHERE estado IN ('pendiente', 'ejecutando')"))
    solas = S.crear_ejecuciones(con, particion["id_particion"], CHICO, "calles")
    S.ejecutar_agentes([x["id_ejecucion"] for x in solas], motor=MotorDePrueba(con))
    for tres, sola in zip(corridos, solas):
        b = next(v for v in S.agente(con, tres["id_ejecucion"])["comparacion"]["variantes"] if v["variante"] == "B")
        assert S.agente(con, sola["id_ejecucion"])["mejor_distancia"] == pytest.approx(b["distancia_calles_m"], abs=0.1)


def test_solo_calles_sin_matriz_cae_en_linea_recta_y_avisa(con, particion, monkeypatch):
    a = con.execute(text("SELECT id_analisis FROM analisis_hdbscan WHERE vigente")).scalar()
    con.execute(text("DELETE FROM matriz_calles WHERE id_analisis = :a"), {"a": a})
    monkeypatch.setattr(ruteo, "_consultar", TablaFalsa(codigo="NoTable"))
    creadas = S.crear_ejecuciones(con, particion["id_particion"], CHICO, "calles")
    S.ejecutar_agentes([c["id_ejecucion"] for c in creadas], motor=MotorDePrueba(con))
    x = S.agente(con, creadas[0]["id_ejecucion"])
    assert x["medir"] == "calles" and x["metrica"] == "recta" and "línea recta" in x["comparacion"]["aviso"]


def test_forma_de_medir_invalida(con, particion):
    with pytest.raises(S.AG.ParametrosInvalidos):
        S.crear_ejecuciones(con, particion["id_particion"], CHICO, "a_ojo")


def test_api_forma_de_medir(cliente, particion):
    base = {"tam_poblacion": 20, "n_generaciones": 10, "tam_torneo": 3, "semilla": 7}
    r = cliente.post("/api/agentes", json={"id_particion": particion["id_particion"],
                                            "parametros": {**base, "medir": "calles"}})
    assert r.status_code == 202
    a = cliente.get(f"/api/agentes/{r.json()['ejecuciones'][0]['id_ejecucion']}").json()
    assert a["medir"] == "calles" and a["metrica"] == "calles" and len(a["comparacion"]["variantes"]) == 1
    r = cliente.post("/api/agentes", json={"id_particion": particion["id_particion"],
                                            "parametros": {**base, "medir": "a_ojo"}})
    assert r.status_code == 422
