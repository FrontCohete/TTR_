"""Guardado del análisis (pieza 3.4), contra la base real.

Cada prueba usa la conexión 'con', que se DESHACE al terminar: no queda nada guardado
y el análisis vigente real no cambia. Para que sean rápidas, analizan solo una parte
de los puntos y con un min_cluster_size más chico que el de la tesis.
"""
import pytest
from sqlalchemy import text

from app.servicios import analisis as A
from app.servicios import clustering as C
from pruebas.test_insercion import con  # noqa: F401  (fixture: conexión que se deshace)

PRUEBA = C.Parametros(min_cluster_size=30, min_samples=10)


@pytest.fixture
def guardado(con):
    """Corre un análisis chico, lo guarda y devuelve (con, id_analisis, resultado, previo)."""
    previo = A.analisis_vigente(con)
    puntos = C.leer_puntos(con, PRUEBA).head(5000)
    r = C.ejecutar(puntos, PRUEBA)
    assert r.n_hotspots > 0, "la muestra no dio hotspots; revisa los datos de prueba"
    id_analisis = A.guardar(con, r, A.ultima_carga_completada(con))
    return con, id_analisis, r, previo


def uno(con, sql, **params):
    return con.execute(text(sql), params).scalar()


def test_queda_un_solo_vigente_y_es_el_nuevo(guardado):
    con, id_analisis, _, previo = guardado
    assert uno(con, "SELECT count(*) FROM analisis_hdbscan WHERE vigente") == 1
    assert A.analisis_vigente(con) == id_analisis
    assert uno(con, "SELECT id_analisis_previo FROM analisis_hdbscan WHERE id_analisis = :i",
               i=id_analisis) == previo


def test_cifras_y_criterios_del_analisis(guardado):
    con, id_analisis, r, _ = guardado
    a = con.execute(text("SELECT * FROM analisis_hdbscan WHERE id_analisis = :i"),
                    {"i": id_analisis}).mappings().one()
    assert (a["n_puntos"], a["n_hotspots"], a["n_ruido"]) == (r.n_puntos, r.n_hotspots, r.n_ruido)
    assert (a["min_cluster_size"], a["min_samples"], a["peso_minimo"]) == (30, 10, 2)
    assert a["min_cluster_size_base"] == 30 and a["hotspots_minimos"] is None
    assert a["metrica"] == "euclidiana_utm"


def test_hotspots_con_area_y_numerados(guardado):
    con, id_analisis, r, _ = guardado
    filas = con.execute(text("""
        SELECT etiqueta, codigo, n_puntos, ST_GeometryType(geom_area) AS tipo,
               ST_SRID(geom_area) AS srid, ST_IsValid(geom_area) AS valida
        FROM hotspot WHERE id_analisis = :i ORDER BY etiqueta
    """), {"i": id_analisis}).mappings().all()
    assert len(filas) == r.n_hotspots
    assert [f["etiqueta"] for f in filas] == list(range(1, r.n_hotspots + 1))
    assert filas[0]["codigo"] == "H-01"
    assert all(f["tipo"] == "ST_Polygon" and f["srid"] == 4326 and f["valida"] for f in filas)


def test_membresia_cubre_todos_los_puntos(guardado):
    con, id_analisis, r, _ = guardado
    total, ruido = con.execute(text("""
        SELECT count(*), count(*) FILTER (WHERE id_hotspot IS NULL)
        FROM membresia_hotspot WHERE id_analisis = :i
    """), {"i": id_analisis}).one()
    assert (total, ruido) == (r.n_puntos, r.n_ruido)
    # el n_puntos de cada hotspot coincide con los puntos que le apuntan
    assert uno(con, """
        SELECT count(*) FROM hotspot h
        WHERE h.id_analisis = :i
          AND h.n_puntos <> (SELECT count(*) FROM membresia_hotspot m WHERE m.id_hotspot = h.id_hotspot)
    """, i=id_analisis) == 0


def test_registra_las_cargas_que_aportaron_puntos(guardado):
    con, id_analisis, _, _ = guardado
    assert uno(con, "SELECT count(*) FROM analisis_carga WHERE id_analisis = :i", i=id_analisis) >= 1


def test_resultado_json_trae_los_hotspots_como_geojson(guardado):
    con, id_analisis, r, _ = guardado
    j = uno(con, "SELECT resultado_json FROM analisis_hdbscan WHERE id_analisis = :i", i=id_analisis)
    assert j["id_analisis"] == id_analisis and j["n_hotspots"] == r.n_hotspots
    assert j["parametros"]["min_cluster_size"] == 30
    fc = j["hotspots"]
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == r.n_hotspots
    props = fc["features"][0]["properties"]
    assert isinstance(props["id_hotspot"], int)                     # el frontend exige enteros
    assert len(props["centroide"]) == 2 and props["centroide"][0] < 0   # [lon, lat]
    assert props["indice_gravedad"] is not None
    ids_tabla = set(con.execute(text("SELECT id_hotspot FROM hotspot WHERE id_analisis = :i"),
                                {"i": id_analisis}).scalars())
    assert {f["properties"]["id_hotspot"] for f in fc["features"]} == ids_tabla


def test_un_segundo_analisis_reemplaza_al_vigente(guardado):
    con, primero, r, _ = guardado
    segundo = A.guardar(con, r, A.ultima_carga_completada(con))
    assert A.analisis_vigente(con) == segundo
    assert uno(con, "SELECT id_analisis_previo FROM analisis_hdbscan WHERE id_analisis = :i",
               i=segundo) == primero
    assert uno(con, "SELECT vigente FROM analisis_hdbscan WHERE id_analisis = :i", i=primero) is False


# ------------------------------------------- ¿hace falta un análisis nuevo? (pieza 3.5)
def test_contar_puntos_coincide_con_leer_puntos(con):
    assert C.contar_puntos(con) == len(C.leer_puntos(con))


def test_al_dia_solo_si_el_vigente_usa_todos_los_puntos(guardado):
    con, id_analisis, _, _ = guardado
    n = C.contar_puntos(con, PRUEBA)

    def vigente_con(n_puntos):
        con.execute(text("UPDATE analisis_hdbscan SET n_puntos = :n WHERE id_analisis = :i"),
                    {"n": n_puntos, "i": id_analisis})

    vigente_con(n)
    assert A.esta_al_dia(con, PRUEBA)                # mismos puntos y criterios: no se repite
    vigente_con(n - 1)
    assert not A.esta_al_dia(con, PRUEBA)            # llegó al menos un punto nuevo
    vigente_con(n)
    assert not A.esta_al_dia(con, C.Parametros(min_cluster_size=40, min_samples=10))  # otro criterio