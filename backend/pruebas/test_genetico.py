"""Algoritmo genético (etapa 5). No usa la base: grafos inventados con distancias haversine."""
import itertools

import numpy as np
import pytest

from app.servicios import genetico as AG
from app.servicios.particion import haversine


def grafo(n, semilla=1):
    """n hotspots al azar dentro de GAM; ids a partir de 500 para no confundirlos con posiciones."""
    rng = np.random.default_rng(semilla)
    lat = 19.45 + rng.random(n) * 0.12
    lon = -99.17 + rng.random(n) * 0.12
    D = haversine(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    return [500 + i for i in range(n)], D


def longitud(ruta_ids, ids, D, cerrada=True):
    pos = {h: i for i, h in enumerate(ids)}
    r = [pos[h] for h in ruta_ids]
    d = sum(D[r[i], r[i + 1]] for i in range(len(r) - 1))
    return d + (D[r[-1], r[0]] if cerrada and len(r) > 1 else 0)


def optimo(ids, D):
    n = len(ids)
    return min(longitud([ids[0], *p], ids, D) for p in itertools.permutations(ids[1:]))


RAPIDO = AG.Parametros(tam_poblacion=30, n_generaciones=60)


# ------------------------------------------------------------------ operadores
def test_ox_ejemplo_de_la_guia():
    assert AG.cruce_ox([1, 2, 3, 4, 5, 6, 7, 8], [3, 7, 5, 1, 6, 8, 2, 4], 3, 6) == [7, 1, 8, 4, 5, 6, 2, 3]


def test_pmx_ejemplo_de_la_guia():
    assert AG.cruce_pmx([1, 2, 3, 4, 5, 6, 7, 8], [3, 7, 5, 1, 6, 8, 2, 4], 3, 6) == [3, 7, 8, 4, 5, 6, 2, 1]


@pytest.mark.parametrize("cruce", [AG.cruce_ox, AG.cruce_pmx])
def test_cruces_siempre_dan_permutaciones_y_conservan_el_segmento(cruce):
    rng = np.random.default_rng(0)
    for _ in range(3000):
        n = int(rng.integers(3, 20))
        a, b = rng.permutation(n).tolist(), rng.permutation(n).tolist()
        c1, c2 = AG._puntos_de_corte(n, rng)
        h = cruce(a, b, c1, c2)
        assert sorted(h) == list(range(n))
        assert h[c1:c2] == a[c1:c2]


def test_inversion_e_intercambio():
    assert AG.invertir([1, 2, 3, 4, 5, 6], 1, 4) == [1, 5, 4, 3, 2, 6]
    assert AG.intercambiar([1, 2, 3, 4, 5, 6], 1, 4) == [1, 5, 3, 4, 2, 6]


# ------------------------------------------------------------------ contrato con la vista Rutas
def test_contrato_generacion_por_generacion():
    ids, D = grafo(12)
    p = AG.Parametros(tam_poblacion=20, n_generaciones=40, tam_torneo=5)
    r = AG.ejecutar_ag(ids, D, p)
    H = p.tam_poblacion - p.n_elite
    assert len(r.generaciones) == len(r.resumen) == p.n_generaciones + 1
    assert r.operaciones(0) is None
    for g in range(1, p.n_generaciones + 1):
        previa, actual, ops = r.individuos(g - 1), r.individuos(g), r.operaciones(g)
        assert [x["posicion"] for x in actual] == list(range(p.tam_poblacion))
        assert len(ops["torneos"]) == 2 * H and len(ops["cruces"]) == H
        assert ops["seleccion_azar"] == [x for t in ops["torneos"] for x in t["participantes"]]
        for t in ops["torneos"]:
            assert len(t["participantes"]) == p.tam_torneo
            assert previa[t["ganador"]]["distancia"] == min(previa[x]["distancia"] for x in t["participantes"])
        muts = {m["individuo"]: m for m in ops["mutaciones"]}
        for c in ops["cruces"]:
            h = c["hijo"]
            A, B = previa[c["padres"][0]]["permutacion"], previa[c["padres"][1]]["permutacion"]
            esperado = AG.cruce_ox(A, B, *c["puntos_corte"]) if c["aplicado"] else A
            hijo = actual[h]["permutacion"]
            if h in muts:          # la vista Rutas deshace la mutación así
                a, b = muts[h]["posiciones"]
                hijo = AG.invertir(hijo, a, b)
                assert actual[h]["origen"] == "mutacion"
            else:
                assert actual[h]["origen"] == "cruce"
            assert hijo == esperado
            assert [actual[h]["padre_1"], actual[h]["padre_2"]] == c["padres"]
        elite = actual[-1]      # copia intacta de la (o una de las) más cortas de la generación anterior
        assert elite["origen"] == "elite" and elite["padre_2"] is None
        assert elite["permutacion"] == previa[elite["padre_1"]]["permutacion"]
        assert elite["distancia"] == min(x["distancia"] for x in previa)
        assert all(m["individuo"] < H for m in ops["mutaciones"])
        for x in actual:
            assert sorted(x["permutacion"]) == ids
            assert x["distancia"] == pytest.approx(longitud(x["permutacion"], ids, D), abs=0.1)


def test_con_elite_la_mejor_nunca_empeora():
    ids, D = grafo(25)
    r = AG.ejecutar_ag(ids, D, AG.Parametros(tam_poblacion=50, n_generaciones=150), registro=False)
    mejores = [g["mejor_fitness"] for g in r.resumen]
    assert all(b <= a for a, b in zip(mejores, mejores[1:]))
    assert r.mejor_distancia == min(mejores)
    assert r.resumen[r.generacion_mejor]["mejor_fitness"] == r.mejor_distancia
    assert r.mejor_distancia == pytest.approx(longitud(r.ruta_optima, ids, D), abs=0.1)


def test_resumen_coherente():
    ids, D = grafo(10)
    r = AG.ejecutar_ag(ids, D, RAPIDO)
    for g, s in enumerate(r.resumen):
        ds = [x["distancia"] for x in r.individuos(g)]
        assert s["mejor_fitness"] <= s["fitness_promedio"] <= s["peor_fitness"]
        assert s["mejor_fitness"] == pytest.approx(min(ds), abs=0.1)
        assert s["mejor_permutacion"] in [x["permutacion"] for x in r.individuos(g)]


def test_misma_semilla_mismo_resultado_y_otra_semilla_otro_camino():
    ids, D = grafo(15)
    a = AG.ejecutar_ag(ids, D, RAPIDO)
    b = AG.ejecutar_ag(ids, D, RAPIDO)
    c = AG.ejecutar_ag(ids, D, AG.Parametros(tam_poblacion=30, n_generaciones=60, semilla=7))
    assert a.ruta_optima == b.ruta_optima and a.individuos(60) == b.individuos(60)
    assert a.individuos(0) != c.individuos(0)


def test_sin_registro_da_la_misma_ruta():
    ids, D = grafo(15)
    con = AG.ejecutar_ag(ids, D, RAPIDO)
    sin = AG.ejecutar_ag(ids, D, RAPIDO, registro=False)
    assert sin.generaciones is None and sin.ruta_optima == con.ruta_optima and sin.resumen == con.resumen


def test_encuentra_el_optimo_en_un_grafo_de_8():
    ids, D = grafo(8, semilla=4)
    r = AG.ejecutar_ag(ids, D, AG.Parametros(n_generaciones=200), registro=False)
    assert r.mejor_distancia == pytest.approx(optimo(ids, D), abs=0.2)


def test_pmx_y_swap_tambien_funcionan():
    ids, D = grafo(10)
    r = AG.ejecutar_ag(ids, D, AG.Parametros(tam_poblacion=20, n_generaciones=20, op_cruce="PMX", op_mutacion="swap"))
    assert r.operaciones(5)["mutaciones"] == [] or r.operaciones(5)["mutaciones"][0]["tipo"] == "swap"
    assert sorted(r.ruta_optima) == ids


def test_ruta_abierta_no_suma_el_regreso():
    ids, D = grafo(9)
    r = AG.ejecutar_ag(ids, D, AG.Parametros(tam_poblacion=20, n_generaciones=30, ruta_cerrada=False))
    assert r.mejor_distancia == pytest.approx(longitud(r.ruta_optima, ids, D, cerrada=False), abs=0.1)


# ------------------------------------------------------------------ grafos chicos
@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_grafos_chicos_corren_y_dan_el_optimo(n):
    ids, D = grafo(n)
    r = AG.ejecutar_ag(ids, D, AG.Parametros(tam_poblacion=100, n_generaciones=20))
    assert sorted(r.ruta_optima) == ids
    assert r.mejor_distancia == pytest.approx(optimo(ids, D) if n > 1 else 0, abs=0.2)
    if n <= 2:
        assert all(not c["aplicado"] for c in r.operaciones(1)["cruces"])


# ------------------------------------------------------------------ parámetros
@pytest.mark.parametrize("cambio, texto", [
    ({"tam_poblacion": 500, "n_generaciones": 2000}, "100,000"),
    ({"tam_torneo": 1}, "torneo"),
    ({"tam_poblacion": 4, "tam_torneo": 5, "n_generaciones": 10}, "torneo"),
    ({"prob_cruce": 1.5}, "cruce"),
    ({"prob_mutacion": -0.1}, "mutación"),
    ({"op_cruce": "XYZ"}, "OX o PMX"),
    ({"n_generaciones": 0}, "generaciones"),
])
def test_parametros_invalidos(cambio, texto):
    with pytest.raises(AG.ParametrosInvalidos, match=texto):
        AG.Parametros(**cambio).validar()


def test_valores_por_omision_acordados():
    p = AG.Parametros()
    assert (p.tam_poblacion, p.n_generaciones, p.tam_torneo, p.prob_cruce, p.prob_mutacion,
            p.op_cruce, p.op_mutacion, p.n_elite, p.ruta_cerrada) == (100, 1000, 5, 0.9, 0.5, "OX", "inversion", 1, True)
    assert AG.Parametros.desde({"tam_poblacion": 80, "otra_cosa": 1}).tam_poblacion == 80


# ------------------------------------------------------------------ presentación
def test_presentar_ruta_empieza_en_la_mayor_carga_sin_cambiar_la_distancia():
    ids, D = grafo(6)
    hotspots = [{"id_hotspot": h, "n_puntos": 100 + i, "indice_gravedad": 2.0, "etiqueta": i + 1} for i, h in enumerate(ids)]
    hotspots[3]["n_puntos"] = 900
    ruta = [ids[2], ids[0], ids[3], ids[5], ids[1], ids[4]]
    r = AG.presentar_ruta(ruta, AG.prioridad_hotspots(hotspots))
    assert r[0] == ids[3] and r == ruta[2:] + ruta[:2]
    assert longitud(r, ids, D) == pytest.approx(longitud(ruta, ids, D))