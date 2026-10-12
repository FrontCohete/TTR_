"""HDBSCAN (pieza 3.3): con nubes de puntos inventadas y, al final, con la base real."""
import numpy as np
import pandas as pd

from app.servicios import clustering as C
from pruebas.test_insercion import con  # noqa: F401  (fixture: conexión que se deshace)

PRUEBA = C.Parametros(min_cluster_size=100, min_samples=10)


def nubes(tamanos=(600, 400, 250), ruido=150, semilla=7) -> pd.DataFrame:
    """Nubes de puntos separadas ~2 km entre sí, más puntos sueltos, alrededor de GAM."""
    rng = np.random.default_rng(semilla)
    centros = [(0, 0), (2500, 0), (0, 2500), (2500, 2500)]
    partes = [rng.normal(centros[i], 120, (n, 2)) for i, n in enumerate(tamanos)]
    partes.append(rng.uniform(-1500, 4000, (ruido, 2)))
    xy = np.vstack(partes)
    n = len(xy)
    return pd.DataFrame({
        "id_punto": np.arange(1, n + 1),
        "x": xy[:, 0], "y": xy[:, 1],
        "lat": 19.48 + xy[:, 1] / 110_540,                 # metros -> grados (aprox.)
        "lon": -99.11 + xy[:, 0] / 104_900,
        "peso": rng.choice([2, 3, 4], n),
        "delito": rng.choice(["AMENAZAS", "FRAUDE"], n),
        "colonia": "Lindavista",
    })


def test_tres_nubes_dan_tres_hotspots():
    r = C.ejecutar(nubes(), PRUEBA)
    assert r.n_hotspots == 3
    assert r.n_ruido + sum(h["n_puntos"] for h in r.hotspots) == r.n_puntos


def test_se_numeran_del_mas_grande_al_mas_chico():
    r = C.ejecutar(nubes(), PRUEBA)
    assert [h["codigo"] for h in r.hotspots] == ["H-01", "H-02", "H-03"]
    tamanos = [h["n_puntos"] for h in r.hotspots]
    assert tamanos == sorted(tamanos, reverse=True)


def test_el_nodo_es_una_victima_real():
    puntos = nubes()
    reales = set(zip(puntos.lat, puntos.lon))
    for h in C.ejecutar(puntos, PRUEBA).hotspots:
        assert (h["lat_centroide"], h["lon_centroide"]) in reales


def test_medoide_no_cae_en_el_hueco_de_una_u():
    # Puntos en forma de "U": el promedio cae en el hueco; el medoide, sobre la U
    t = np.linspace(0, np.pi, 300)
    xy = np.c_[1000 * np.cos(t), -1000 * np.sin(t)]
    i = C.medoide(xy)
    promedio = xy.mean(axis=0)
    assert np.hypot(*(xy - promedio).T).min() > 300      # el promedio está lejos de todo punto
    assert np.hypot(*xy[i]) > 900                        # el medoide está sobre la U (radio 1000)


def test_membresia_con_ruido_y_probabilidades():
    r = C.ejecutar(nubes(), PRUEBA)
    m = r.membresia
    assert len(m) == r.n_puntos
    assert m.etiqueta.isna().sum() == r.n_ruido
    assert set(m.etiqueta.dropna().astype(int)) == {1, 2, 3}
    assert m.probabilidad.between(0, 1).all()


def test_cada_hotspot_trae_lo_que_pide_la_base():
    h = C.ejecutar(nubes(), PRUEBA).hotspots[0]
    assert h["area"]["type"] == "Polygon"
    anillo = h["area"]["coordinates"][0]
    assert anillo[0] == anillo[-1]                       # anillo cerrado
    assert 2 <= h["indice_gravedad"] <= 4
    assert h["radio_m"] > 0 and h["delito_predominante"] in {"AMENAZAS", "FRAUDE"}


def test_configuracion_decidida_para_la_tesis():
    assert (C.PARAMETROS.min_cluster_size, C.PARAMETROS.min_samples) == (100, 10)
    assert not hasattr(C.PARAMETROS, "hotspots_minimos")      # sin mínimo ni máximo


def test_el_area_solo_usa_el_90_por_ciento_mas_cercano():
    puntos = nubes()
    for h in C.ejecutar(puntos, PRUEBA).hotspots:
        # mismos factores que nubes() para pasar de grados a metros
        x0, y0 = (h["lon_centroide"] + 99.11) * 104_900, (h["lat_centroide"] - 19.48) * 110_540
        for lon, lat in h["area"]["coordinates"][0]:
            x, y = (lon + 99.11) * 104_900, (lat - 19.48) * 110_540
            assert np.hypot(x - x0, y - y0) <= h["radio_m"] + 1   # ningún vértice más allá del radio


def test_muy_pocos_puntos_no_truena():
    r = C.ejecutar(nubes(tamanos=(5,), ruido=0), PRUEBA)
    assert r.n_hotspots == 0 and r.n_ruido == 5


# ------------------------------------------------------------ base real
def test_leer_puntos_solo_trae_gravedad_media_alta_critica(con):
    puntos = C.leer_puntos(con)
    assert len(puntos) > 0
    assert puntos.peso.min() >= 2
    assert list(puntos.columns) == ["id_punto", "lat", "lon", "x", "y", "peso", "delito", "colonia"]
    # UTM 14N alrededor de GAM: x ≈ 480–500 km, y ≈ 2,150–2,170 km
    assert puntos.x.between(470_000, 510_000).all()
    assert puntos.y.between(2_140_000, 2_180_000).all()