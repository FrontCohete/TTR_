"""HDBSCAN sobre los puntos delictivos de GAM (etapa 3, pieza 3.3).

Este módulo solo CALCULA: lee los puntos, corre HDBSCAN y describe cada hotspot.
Guardar el resultado en la base es trabajo de la pieza 3.4.

Decisiones (ver claude/DECISIONES_BACKEND.md, etapa 3):
  * entran los puntos dentro de GAM con gravedad >= 2 (Media, Alta, Crítica);
  * coordenadas en metros (UTM 14N) y distancia euclidiana;
  * min_cluster_size 100, min_samples 10, selección "eom" (configuración fija:
    no hay mínimo ni máximo de hotspots; salen los que los datos den);
  * la posición de cada nodo es el MEDOIDE: la víctima real más central del hotspot;
  * el radio y el área de cada hotspot se calculan con el 90 % de sus puntos más
    cercanos al medoide, para que unas cuantas víctimas lejanas no inflen la figura.
"""
import time
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from scipy.spatial import ConvexHull, QhullError
from sklearn.cluster import HDBSCAN
from sqlalchemy import text

METRICA = "euclidiana_utm"


@dataclass(frozen=True)
class Parametros:
    """Criterios de un análisis. Los valores por omisión son los decididos para la tesis."""
    min_cluster_size: int = 100
    min_samples: int = 10
    peso_minimo: int = 2
    fecha_desde: date | None = None


PARAMETROS = Parametros()


@dataclass
class Resultado:
    parametros: Parametros
    n_puntos: int
    n_ruido: int
    hotspots: list[dict]
    membresia: pd.DataFrame = field(repr=False)   # id_punto, etiqueta (None = ruido), probabilidad
    duracion_s: float = 0.0

    @property
    def n_hotspots(self) -> int:
        return len(self.hotspots)

    @property
    def pct_ruido(self) -> float:
        return round(100 * self.n_ruido / self.n_puntos, 1) if self.n_puntos else 0.0


# ------------------------------------------------------------------ lectura
CONSULTA_PUNTOS = text("""
    SELECT p.id_punto,
           p.latitud  AS lat,
           p.longitud AS lon,
           ST_X(t.g)  AS x,
           ST_Y(t.g)  AS y,
           d.peso_gravedad AS peso,
           d.nombre AS delito,
           coalesce(c.nombre, p.colonia_texto, 'Sin colonia') AS colonia,
           p.hash_registro AS huella
    FROM punto_delictivo p
    JOIN cat_delito d USING (id_delito)
    LEFT JOIN colonia c USING (id_colonia)
    CROSS JOIN LATERAL (
        SELECT ST_Transform(ST_SetSRID(ST_MakePoint(p.longitud, p.latitud), 4326), 32614) AS g
    ) t
    WHERE p.dentro_gam
      AND d.peso_gravedad >= :peso_minimo
      AND (CAST(:desde AS date) IS NULL OR p.fecha_hecho >= CAST(:desde AS date))
    ORDER BY p.hash_registro
""")

# Mismo filtro que CONSULTA_PUNTOS, pero solo cuenta (rápido): sirve para saber si
# el análisis vigente ya usa todos los puntos o si llegaron puntos nuevos.
CONSULTA_CONTEO = text("""
    SELECT count(*)
    FROM punto_delictivo p
    JOIN cat_delito d USING (id_delito)
    WHERE p.dentro_gam
      AND d.peso_gravedad >= :peso_minimo
      AND (CAST(:desde AS date) IS NULL OR p.fecha_hecho >= CAST(:desde AS date))
""")


def leer_puntos(con, parametros: Parametros = PARAMETROS) -> pd.DataFrame:
    """Los puntos que entran al análisis, con coordenadas en grados (lat, lon) y en metros (x, y).

    Se ordenan por la huella de cada registro (hash_registro), que depende solo de su contenido:
    el resultado es el mismo sin importar en qué orden se cargaron los datasets (etapa 6.5).
    """
    return pd.read_sql(CONSULTA_PUNTOS, con, params={
        "peso_minimo": max(parametros.peso_minimo, 1),     # el peso 0 nunca entra
        "desde": parametros.fecha_desde,
    })


def contar_puntos(con, parametros: Parametros = PARAMETROS) -> int:
    """Cuántos puntos entrarían hoy al análisis (sin leerlos)."""
    return con.execute(CONSULTA_CONTEO, {
        "peso_minimo": max(parametros.peso_minimo, 1),
        "desde": parametros.fecha_desde,
    }).scalar_one()


# ------------------------------------------------------------------ HDBSCAN
def agrupar(xy: np.ndarray, min_cluster_size: int, min_samples: int):
    """Corre HDBSCAN. Devuelve (etiquetas, probabilidades); etiqueta -1 = ruido."""
    if len(xy) <= max(min_samples, 2):                     # muy pocos puntos para agrupar
        return np.full(len(xy), -1), np.zeros(len(xy))
    modelo = HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples,
                     cluster_selection_method="eom", copy=True).fit(xy)
    return modelo.labels_, modelo.probabilities_


def contar(etiquetas: np.ndarray) -> int:
    """Cuántos hotspots hay (las etiquetas van de 0 a k-1; -1 es ruido)."""
    return int(etiquetas.max()) + 1 if len(etiquetas) else 0


# --------------------------------------------------------------- hotspots
def medoide(xy: np.ndarray, max_candidatos: int = 2000) -> int:
    """Índice del punto con la menor suma de distancias a todos los demás.

    Exacto hasta 2,000 puntos; en hotspots más grandes se elige entre 2,000
    candidatos al azar (semilla fija, así que el resultado no cambia entre corridas).
    """
    k = len(xy)
    if k <= max_candidatos:
        candidatos = np.arange(k)
    else:
        candidatos = np.sort(np.random.default_rng(0).choice(k, max_candidatos, replace=False))
    mejor, mejor_suma = int(candidatos[0]), np.inf
    for inicio in range(0, len(candidatos), 256):           # por bloques: poca memoria
        bloque = candidatos[inicio:inicio + 256]
        distancias = np.hypot(xy[bloque, None, 0] - xy[None, :, 0],
                              xy[bloque, None, 1] - xy[None, :, 1])
        sumas = distancias.sum(axis=1)
        j = int(sumas.argmin())
        if sumas[j] < mejor_suma:
            mejor, mejor_suma = int(bloque[j]), sumas[j]
    return mejor


def area(lat: np.ndarray, lon: np.ndarray):
    """Polígono GeoJSON que encierra los puntos (envolvente convexa), o None."""
    unicos = np.unique(np.c_[lon, lat], axis=0)
    if len(unicos) < 3:
        return None
    try:
        casco = ConvexHull(unicos)
    except QhullError:                                       # puntos alineados
        return None
    anillo = [[round(float(x), 6), round(float(y), 6)] for x, y in unicos[casco.vertices]]
    anillo.append(anillo[0])                                 # GeoJSON exige cerrar el anillo
    return {"type": "Polygon", "coordinates": [anillo]}


def moda(serie: pd.Series):
    """El valor más frecuente y qué porcentaje representa."""
    conteo = serie.value_counts()
    return conteo.index[0], round(100 * conteo.iloc[0] / len(serie))


def describir(puntos: pd.DataFrame, etiquetas: np.ndarray, prob: np.ndarray):
    """Describe cada hotspot y numera del más grande (H-01) al más chico.

    Devuelve (hotspots, nueva_etiqueta): nueva_etiqueta traduce la etiqueta de
    HDBSCAN (0, 1, 2…) a la etiqueta final (1 = el más grande).
    """
    datos = puntos.assign(_etiqueta=etiquetas, _prob=prob)
    hotspots = []
    for etiqueta, grupo in datos[datos._etiqueta >= 0].groupby("_etiqueta"):
        xy = grupo[["x", "y"]].to_numpy()
        centro = medoide(xy)
        distancias = np.hypot(xy[:, 0] - xy[centro, 0], xy[:, 1] - xy[centro, 1])
        p90 = float(np.percentile(distancias, 90))
        cerca = distancias <= p90                                    # el 90 % más cercano
        radio = max(p90, 10.0)
        delito, pct_delito = moda(grupo.delito)
        colonia, _ = moda(grupo.colonia)
        hotspots.append({
            "_hdbscan": int(etiqueta),
            "n_puntos": len(grupo),
            "lat_centroide": float(grupo.lat.iloc[centro]),          # medoide
            "lon_centroide": float(grupo.lon.iloc[centro]),
            "area": area(grupo.lat.to_numpy()[cerca], grupo.lon.to_numpy()[cerca]),
            "radio_m": round(radio, 1),
            "delito_predominante": delito,
            "pct_delito": pct_delito,
            "colonia": colonia,
            "indice_gravedad": round(float(grupo.peso.mean()), 2),
            "confianza": round(float(grupo._prob.mean()), 2),
            "densidad": round(len(grupo) / (np.pi * radio ** 2 / 1e6)),   # víctimas por km²
        })
    hotspots.sort(key=lambda h: (-h["n_puntos"], h["lat_centroide"], h["lon_centroide"]))
    nueva_etiqueta = {}
    for numero, h in enumerate(hotspots, start=1):
        nueva_etiqueta[h.pop("_hdbscan")] = numero
        h["etiqueta"] = numero
        h["codigo"] = f"H-{numero:02d}"
    return hotspots, nueva_etiqueta


# --------------------------------------------------------------- principal
def orden_estable(puntos: pd.DataFrame) -> pd.DataFrame:
    """Los mismos puntos siempre en el mismo orden, sin importar el orden de carga (etapa 6.5).

    HDBSCAN puede dar resultados ligeramente distintos con los mismos puntos en otro orden cuando
    hay coordenadas repetidas (muy común: varias víctimas en el mismo domicilio). Se ordena por
    coordenadas en metros y, para desempatar, por la huella del registro (si viene en los datos).
    """
    claves = ["x", "y"] + (["huella"] if "huella" in puntos.columns else [])
    return puntos.sort_values(claves, kind="mergesort").reset_index(drop=True)


def ejecutar(puntos: pd.DataFrame, parametros: Parametros = PARAMETROS) -> Resultado:
    """Corre el análisis completo sobre los puntos ya leídos."""
    inicio = time.perf_counter()
    puntos = orden_estable(puntos)
    xy = puntos[["x", "y"]].to_numpy()
    etiquetas, prob = agrupar(xy, parametros.min_cluster_size, parametros.min_samples)
    hotspots, nueva_etiqueta = describir(puntos, etiquetas, prob)

    membresia = pd.DataFrame({
        "id_punto": puntos["id_punto"].to_numpy(),
        "etiqueta": [nueva_etiqueta.get(int(e)) for e in etiquetas],   # None = ruido
        "probabilidad": np.round(prob, 4),
    })
    return Resultado(
        parametros=parametros,
        n_puntos=len(puntos),
        n_ruido=int((etiquetas == -1).sum()),
        hotspots=hotspots,
        membresia=membresia,
        duracion_s=round(time.perf_counter() - inicio, 1),
    )