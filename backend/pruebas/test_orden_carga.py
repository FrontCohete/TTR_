"""Etapa 6.5: el análisis no depende del orden en que se cargaron los datasets.

Hallazgo del 30 de octubre de 2026: los mismos 54,045 puntos dieron 93 hotspots cargados
2024 → 2022 y 94 cargados 2022 → 2024, porque los puntos llegaban a HDBSCAN en orden de carga.
"""
import numpy as np
import pandas as pd
from sqlalchemy import text

from app.servicios import clustering as C
from pruebas.test_clustering import PRUEBA, nubes
from pruebas.test_insercion import con  # noqa: F401  (fixture: conexión que se deshace)


def con_repetidos(semilla=7) -> pd.DataFrame:
    """Nubes con muchas coordenadas repetidas (varias víctimas en el mismo lugar), como en la FGJ."""
    p = nubes(semilla=semilla)
    rng = np.random.default_rng(semilla)
    copias = p.sample(400, random_state=semilla, replace=True).copy()
    copias["id_punto"] = np.arange(len(p) + 1, len(p) + len(copias) + 1)
    copias["peso"] = rng.choice([2, 3, 4], len(copias))
    todo = pd.concat([p, copias], ignore_index=True)
    todo["huella"] = [f"{i:064x}" for i in rng.permutation(len(todo))]      # huella fija por registro
    return todo


def resumen(r):
    hot = [(h["n_puntos"], h["lat_centroide"], h["lon_centroide"], h["radio_m"]) for h in r.hotspots]
    etiquetas = r.membresia.etiqueta.fillna(0).astype(int)          # 0 = ruido
    miembros = dict(zip(r.membresia.id_punto, etiquetas))
    return r.n_hotspots, r.n_ruido, hot, miembros


def test_mismo_resultado_con_los_puntos_en_otro_orden():
    puntos = con_repetidos()
    base = resumen(C.ejecutar(puntos, PRUEBA))
    assert base[0] >= 3
    for semilla in (1, 2, 3):
        revuelto = puntos.sample(frac=1, random_state=semilla).reset_index(drop=True)
        assert resumen(C.ejecutar(revuelto, PRUEBA)) == base


def test_orden_estable_no_pierde_ni_duplica_puntos():
    puntos = con_repetidos()
    o = C.orden_estable(puntos.sample(frac=1, random_state=4))
    assert sorted(o.id_punto) == sorted(puntos.id_punto)
    assert list(o.index) == list(range(len(o)))


def test_leer_puntos_trae_la_huella_y_ordena_por_ella(con):
    puntos = C.leer_puntos(con)
    if puntos.empty:
        return
    assert "huella" in puntos.columns
    assert list(puntos.huella) == sorted(puntos.huella)
    total = con.execute(text("SELECT count(*) FROM punto_delictivo")).scalar()
    assert len(puntos) <= total