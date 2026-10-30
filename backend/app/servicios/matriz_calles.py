"""Matriz de distancias por calles de un análisis (etapa 7 «la mejor de tres», fase 1).

Para comparar tres formas de medir, cada agente necesita la distancia por calles entre todos los
hotspots de su sector. Se pide al servidor OSRM (servicio «table») UNA vez por análisis, con todos
sus hotspots, y se guarda en la tabla matriz_calles (database/07_matriz_calles.sql). Así:
  * todas las tandas de agentes y todas las particiones N = 1…5 la reutilizan sin internet;
  * cada sector toma su pedazo (submatriz) con los hotspots que le tocaron.

Las tres formas de medir (variantes) de un sector:
  A  «recta»            línea recta (haversine), la de siempre (tabla arista)
  B  «calles»           por calles con sentido: ir de X a Y puede medir distinto que de Y a X
  C  «calles_promedio»  por calles, con el promedio de ida y vuelta (simétrica)

Límites del servidor público: hasta MAX_COORDENADAS coordenadas por consulta. Con más hotspots
se piden bloques de BLOQUE × BLOQUE (orígenes × destinos) con una pausa entre consultas.
Si OSRM no encuentra camino entre dos hotspots, se guarda null y al usarla se penaliza con
PENALIZACION × la distancia en línea recta (el genético evita ese tramo).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import text

from app.servicios import ruteo
from app.servicios.particion import matriz_distancias

log = logging.getLogger("uvicorn.error")

MAX_COORDENADAS = 100         # «max-table-size» del servidor público de OSRM
BLOQUE = 50                   # con más de 100 hotspots: bloques de 50 orígenes × 50 destinos
PENALIZACION = 10.0
METRICAS = ("recta", "calles", "calles_promedio")     # A, B, C
VARIANTE = {"recta": "A", "calles": "B", "calles_promedio": "C"}


class SinHotspots(LookupError):
    """El análisis no existe o no tiene hotspots (404)."""


# ------------------------------------------------------------------ consulta a OSRM «table»
def _consulta_table(coords: list, fuentes=None, destinos=None) -> tuple[np.ndarray, np.ndarray]:
    puntos = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords)
    url = f"{ruteo.RUTEO_URL}/table/v1/{ruteo.RUTEO_PERFIL}/{puntos}?annotations=distance,duration"
    if fuentes is not None:
        url += "&sources=" + ";".join(map(str, fuentes)) + "&destinations=" + ";".join(map(str, destinos))
    datos = ruteo._consultar(url)
    if datos.get("code") != "Ok" or "distances" not in datos:
        raise ruteo.RuteoNoDisponible("El servidor de ruteo no devolvió la matriz por calles "
                                      f"({datos.get('code', 'sin código')}: {datos.get('message', '')}).")
    a_num = lambda m: np.array([[np.nan if x is None else float(x) for x in fila] for fila in m], dtype=float)  # noqa: E731
    dist = a_num(datos["distances"])
    dur = a_num(datos["durations"]) if datos.get("durations") else np.full_like(dist, np.nan)
    return dist, dur


def tabla(coords: list) -> tuple[np.ndarray, np.ndarray]:
    """Distancias (m) y duraciones (s) por calles entre todos los puntos [[lon, lat], …]. null → NaN."""
    n = len(coords)
    if n < 2:
        return np.zeros((n, n)), np.zeros((n, n))
    if n <= MAX_COORDENADAS:
        return _consulta_table(coords)
    dist, dur = np.full((n, n), np.nan), np.full((n, n), np.nan)
    bloques = [list(range(i, min(i + BLOQUE, n))) for i in range(0, n, BLOQUE)]
    primera = True
    for origenes in bloques:
        for destinos in bloques:
            if not primera:
                time.sleep(ruteo.PAUSA_ENTRE_CONSULTAS_S)
            primera = False
            juntos = origenes + [d for d in destinos if d not in origenes]
            pos = {k: i for i, k in enumerate(juntos)}
            d, t = _consulta_table([coords[k] for k in juntos],
                                   [pos[o] for o in origenes], [pos[x] for x in destinos])
            dist[np.ix_(origenes, destinos)] = d
            dur[np.ix_(origenes, destinos)] = t
    return dist, dur


# ------------------------------------------------------------------ la matriz de un análisis
@dataclass
class Matriz:
    id_analisis: int
    ids: list[int]
    distancias: np.ndarray            # por calles, completada (sin NaN), fila = origen
    duraciones: np.ndarray
    recta: np.ndarray                 # haversine entre los mismos hotspots
    proveedor: str
    perfil: str
    sin_camino: int
    nueva: bool = False               # True si se acaba de pedir a OSRM
    _pos: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self._pos = {h: i for i, h in enumerate(self.ids)}

    def submatrices(self, ids: list[int], recta: np.ndarray | None = None) -> dict[str, np.ndarray]:
        """Las tres formas de medir entre los hotspots `ids` (en ese orden).

        `recta`: la matriz en línea recta del sector (la de la tabla arista); si no se da, se usa haversine.
        """
        faltan = [h for h in ids if h not in self._pos]
        if faltan:
            raise SinHotspots(f"Los hotspots {faltan[:5]} no son del análisis {self.id_analisis}.")
        k = [self._pos[h] for h in ids]
        calles = self.distancias[np.ix_(k, k)]
        return {
            "recta": self.recta[np.ix_(k, k)] if recta is None else recta,
            "calles": calles,
            "calles_promedio": (calles + calles.T) / 2,
        }


def _hotspots(con, id_analisis: int) -> list[dict]:
    filas = [dict(h) for h in con.execute(text("""
        SELECT id_hotspot, lat_centroide AS lat, lon_centroide AS lon
        FROM hotspot WHERE id_analisis = :a ORDER BY etiqueta
    """), {"a": id_analisis}).mappings()]
    if not filas:
        raise SinHotspots(f"El análisis {id_analisis} no existe o no tiene hotspots.")
    return filas


def _completar(dist: np.ndarray, dur: np.ndarray, recta: np.ndarray):
    """Diagonal en 0; pares sin camino → PENALIZACION × línea recta. Devuelve (dist, dur, sin_camino)."""
    dist, dur = dist.copy(), dur.copy()
    np.fill_diagonal(dist, 0.0)
    np.fill_diagonal(dur, 0.0)
    huecos = np.isnan(dist)
    sin_camino = int(huecos.sum())
    if sin_camino:
        dist[huecos] = PENALIZACION * recta[huecos]
    ok = np.isfinite(dur) & (dur > 0) & ~huecos
    velocidad = float(np.median(dist[ok] / dur[ok])) if ok.any() else 8.0      # m/s
    dur[np.isnan(dur)] = dist[np.isnan(dur)] / velocidad
    return dist, dur, sin_camino


def _a_json(m: np.ndarray) -> str:
    return json.dumps([[None if np.isnan(x) else round(float(x), 1) for x in fila] for fila in m])


def obtener(con, id_analisis: int, pedir: bool = True, tabla_fn=None) -> Matriz | None:
    """La matriz por calles del análisis: de la base si ya está; si no, se pide a OSRM y se guarda.

    pedir=False: si no está guardada devuelve None sin consultar a nadie.
    Lanza SinHotspots (sin hotspots) o ruteo.RuteoNoDisponible (OSRM no respondió). No hace commit.
    """
    hotspots = _hotspots(con, id_analisis)
    ids = [int(h["id_hotspot"]) for h in hotspots]
    lat = np.array([float(h["lat"]) for h in hotspots])
    lon = np.array([float(h["lon"]) for h in hotspots])
    recta = matriz_distancias(lat, lon)

    fila = con.execute(text("SELECT * FROM matriz_calles WHERE id_analisis = :a"), {"a": id_analisis}).mappings().first()
    vigente = fila is not None and [int(x) for x in fila["ids"]] == ids and fila["perfil"] == ruteo.RUTEO_PERFIL
    if vigente:
        a_num = lambda m: np.array([[np.nan if x is None else float(x) for x in f] for f in m], dtype=float)  # noqa: E731
        dist, dur, sin_camino = _completar(a_num(fila["distancias_m"]), a_num(fila["duraciones_s"]), recta)
        return Matriz(id_analisis, ids, dist, dur, recta, fila["proveedor"], fila["perfil"], sin_camino)
    if not pedir:
        return None

    coords = [[round(float(h["lon"]), 6), round(float(h["lat"]), 6)] for h in hotspots]
    inicio = time.perf_counter()
    with ruteo._candado:                               # una consulta a OSRM a la vez (uso moderado)
        crudo_d, crudo_t = (tabla_fn or tabla)(coords)
    segundos = round(time.perf_counter() - inicio, 2)
    if crudo_d.shape != (len(ids), len(ids)):
        raise ruteo.RuteoNoDisponible(f"El servidor de ruteo devolvió una matriz de {crudo_d.shape} "
                                      f"para {len(ids)} hotspots.")
    dist, dur, sin_camino = _completar(crudo_d, crudo_t, recta)
    proveedor = f"osrm:{ruteo.RUTEO_URL.split('//')[-1]}"
    con.execute(text("""
        INSERT INTO matriz_calles (id_analisis, ids, distancias_m, duraciones_s, sin_camino, proveedor, perfil,
                                   duracion_consulta_s)
        VALUES (:a, CAST(:ids AS jsonb), CAST(:d AS jsonb), CAST(:t AS jsonb), :s, :p, :perfil, :seg)
        ON CONFLICT (id_analisis) DO UPDATE
        SET ids = EXCLUDED.ids, distancias_m = EXCLUDED.distancias_m, duraciones_s = EXCLUDED.duraciones_s,
            sin_camino = EXCLUDED.sin_camino, proveedor = EXCLUDED.proveedor, perfil = EXCLUDED.perfil,
            duracion_consulta_s = EXCLUDED.duracion_consulta_s, fecha = now()
    """), {"a": id_analisis, "ids": json.dumps(ids), "d": _a_json(crudo_d), "t": _a_json(crudo_t),
           "s": sin_camino, "p": proveedor, "perfil": ruteo.RUTEO_PERFIL, "seg": segundos})
    log.info("Análisis %s: matriz por calles %d × %d pedida a OSRM en %.1f s (%d pares sin camino)",
             id_analisis, len(ids), len(ids), segundos, sin_camino)
    return Matriz(id_analisis, ids, dist, dur, recta, proveedor, ruteo.RUTEO_PERFIL, sin_camino, nueva=True)


# ------------------------------------------------------------------ medir una ruta
def largo(orden: list[int], D: np.ndarray, cerrada: bool = True) -> float:
    """Metros de recorrer `orden` (índices de D) respetando la dirección de cada tramo."""
    d = sum(float(D[a, b]) for a, b in zip(orden, orden[1:]))
    if cerrada and len(orden) > 1:
        d += float(D[orden[-1], orden[0]])
    return d


def mejor_sentido(orden: list[int], D: np.ndarray, cerrada: bool = True) -> tuple[float, bool]:
    """Un circuito se puede recorrer en los dos sentidos; con calles de un sentido se toma el más corto.

    Devuelve (metros, invertir). Una ruta abierta se invierte completa (también cambia su inicio).
    """
    ida, vuelta = largo(orden, D, cerrada), largo(orden[::-1], D, cerrada)
    return (vuelta, True) if vuelta < ida else (ida, False)


def rodeo(m: Matriz, minimo_m: float = 300) -> dict:
    """Qué tanto más se recorre por calles que en línea recta (pares a más de `minimo_m`)."""
    Dh, Dc = m.recta, m.distancias
    i, j = np.where((Dh >= minimo_m) & ~np.eye(len(Dh), dtype=bool))
    if len(i) == 0:
        return {"pares": 0}
    f = Dc[i, j] / Dh[i, j]
    asim = np.abs(Dc - Dc.T)[i, j] / np.maximum(Dc[i, j], 1)
    return {"pares": int(len(f)), "p10": round(float(np.percentile(f, 10)), 2),
            "mediana": round(float(np.median(f)), 2), "p90": round(float(np.percentile(f, 90)), 2),
            "variacion_pct": round(float(np.std(f) / np.mean(f)) * 100, 1),
            "asimetria_mediana_pct": round(float(np.median(asim)) * 100, 1)}
