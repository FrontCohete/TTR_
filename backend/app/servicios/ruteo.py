"""Trazo por calles para la vista Simular (etapa 6).

El genético decide el ORDEN de visita con distancias en línea recta (haversine). Aquí solo se
DIBUJA ese orden por calles reales, pidiéndole el trazo a un servidor OSRM:

  * Proveedor: OSRM (Open Source Routing Machine) con datos de OpenStreetMap. Por defecto el servidor
    público de demostración (router.project-osrm.org): gratis, sin clave y sin garantías, con uso
    moderado. Se cambia con RUTEO_URL en backend/.env (por ejemplo, un OSRM propio).
  * Perfil: driving (una patrulla en automóvil). Se cambia con RUTEO_PERFIL.
  * Cada agente se pide UNA vez y se guarda en la tabla ruta_calles (database/06_ruta_calles.sql):
    repetir la simulación no vuelve a consultar el servidor, y la presentación no depende de internet
    una vez calculado.
  * Para ser amables con el servidor público, las paradas se mandan en bloques de hasta
    MAX_PARADAS_POR_CONSULTA, con una pausa entre bloques.
  * Si el servidor no responde: RuteoNoDisponible (503) y el frontend muestra la ruta en línea recta.

Lo que se guarda por agente:
  geometria         [[lon, lat], …] del recorrido completo por calles
  indices_paradas   para cada parada (incluido el regreso al inicio), el índice de su vértice en
                    geometria: así el frontend sabe qué hotspot alcanzó el agente
  tramos            distancia y duración por calles de cada tramo entre paradas consecutivas
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time

import httpx
from sqlalchemy import text

from app.servicios import agentes as A

log = logging.getLogger("uvicorn.error")

RUTEO_URL = os.getenv("RUTEO_URL", "https://router.project-osrm.org").rstrip("/")
RUTEO_PERFIL = os.getenv("RUTEO_PERFIL", "driving")
MAX_PARADAS_POR_CONSULTA = 25
PAUSA_ENTRE_CONSULTAS_S = 1.0
TIEMPO_MAXIMO_S = 20.0
AGENTE_HTTP = "TTR_ClusterAgent/0.5 (tesis IPN; simulacion de rutas)"
ATRIBUCION = "Trazo por calles: OSRM · datos © colaboradores de OpenStreetMap (ODbL)"


# Simular pide las rutas de todos sus agentes a la vez: se mandan a OSRM de una en una
_candado = threading.Lock()


class RuteoNoDisponible(RuntimeError):
    """El servidor de ruteo no respondió o no encontró ruta. La ruta responde 503."""


# ------------------------------------------------------------------ cliente OSRM
def _consultar(url: str) -> dict:
    """Una petición HTTP al servidor OSRM (las pruebas la reemplazan por una falsa)."""
    try:
        r = httpx.get(url, timeout=TIEMPO_MAXIMO_S, headers={"User-Agent": AGENTE_HTTP})
    except httpx.HTTPError as error:
        raise RuteoNoDisponible(f"No se pudo contactar al servidor de ruteo ({type(error).__name__}).") from error
    if r.status_code == 429:
        raise RuteoNoDisponible("El servidor de ruteo pidió esperar (demasiadas consultas). Intenta en un minuto.")
    try:
        datos = r.json()
    except ValueError as error:
        raise RuteoNoDisponible(f"El servidor de ruteo respondió algo inesperado (HTTP {r.status_code}).") from error
    return datos


def _metros(a, b) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def _indices(geometria: list, ubicaciones: list) -> list[int]:
    """Índice del vértice de cada parada, avanzando siempre hacia adelante sobre el trazo."""
    indices, desde = [], 0
    for u in ubicaciones:
        mejor, d_mejor = desde, math.inf
        for i in range(desde, len(geometria)):
            d = _metros(geometria[i], u)
            if d < d_mejor:
                mejor, d_mejor = i, d
            if d < 0.5:                       # OSRM pasa exactamente por la parada ajustada a la calle
                break
        indices.append(mejor)
        desde = mejor
    return indices


def _bloque(coords: list) -> dict:
    """Una consulta /route con 2 a MAX_PARADAS_POR_CONSULTA paradas."""
    puntos = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords)
    url = (f"{RUTEO_URL}/route/v1/{RUTEO_PERFIL}/{puntos}"
           "?overview=full&geometries=geojson&steps=false&continue_straight=false")
    datos = _consultar(url)
    if datos.get("code") != "Ok" or not datos.get("routes"):
        raise RuteoNoDisponible("El servidor de ruteo no encontró un camino por calles "
                                f"({datos.get('code', 'sin código')}: {datos.get('message', '')}).".replace(": )", ")"))
    ruta = datos["routes"][0]
    geometria = ruta["geometry"]["coordinates"]
    ubicaciones = [w["location"] for w in datos.get("waypoints", [])] or coords
    return {
        "geometria": geometria,
        "indices": _indices(geometria, ubicaciones),
        "tramos": [{"distancia_m": float(l["distance"]), "duracion_s": float(l["duration"])} for l in ruta["legs"]],
    }


def trazar(coords: list) -> dict:
    """Recorrido por calles que pasa por `coords` ([[lon, lat], …]) en ese orden.

    Devuelve geometria, indices_paradas (uno por coordenada), tramos (len(coords) − 1),
    distancia_m y duracion_s. Lanza RuteoNoDisponible si el servidor falla.
    """
    if len(coords) < 2:
        raise ValueError("Se necesitan al menos 2 paradas.")
    if all(c == coords[0] for c in coords):  # un solo hotspot: no hay nada que trazar
        return {"geometria": [coords[0], coords[0]], "indices_paradas": [0] * (len(coords) - 1) + [1],
                "tramos": [{"distancia_m": 0.0, "duracion_s": 0.0} for _ in coords[1:]],
                "distancia_m": 0.0, "duracion_s": 0.0, "proveedor": "sin_ruteo"}
    paso = MAX_PARADAS_POR_CONSULTA - 1
    geometria, indices, tramos = [], [], []
    for k, inicio in enumerate(range(0, len(coords) - 1, paso)):
        if k:
            time.sleep(PAUSA_ENTRE_CONSULTAS_S)
        b = _bloque(coords[inicio:inicio + paso + 1])
        desfase = len(geometria) - 1 if geometria else 0
        g = b["geometria"][1:] if geometria else b["geometria"]   # el primer vértice ya está (fin del bloque anterior)
        idx = [desfase + i for i in b["indices"]]
        if indices:
            idx = idx[1:]                                          # la primera parada ya se contó
        geometria.extend(g)
        indices.extend(idx)
        tramos.extend(b["tramos"])
    return {
        "geometria": geometria, "indices_paradas": indices, "tramos": tramos,
        "distancia_m": round(sum(t["distancia_m"] for t in tramos), 1),
        "duracion_s": round(sum(t["duracion_s"] for t in tramos), 1),
        "proveedor": f"osrm:{RUTEO_URL.split('//')[-1]}",
    }


# ------------------------------------------------------------------ caché en la base
def ruta_calles(con, id_ejecucion: int, trazar_fn=None) -> dict:
    """GET /api/agentes/{id}/ruta-calles: la ruta del agente por calles (la pide una vez y la guarda).

    No hace commit: la ruta (endpoint) abre su propia transacción.
    """
    recta = A.ruta(con, id_ejecucion)                 # 404 / 409 igual que /ruta
    fila = con.execute(text("SELECT * FROM ruta_calles WHERE id_ejecucion = :e"),
                       {"e": id_ejecucion}).mappings().first()
    if fila is None:
        with _candado:                                 # una consulta a OSRM a la vez (uso moderado)
            t = (trazar_fn or trazar)(recta["geometry"]["coordinates"])
        con.execute(text("""
            INSERT INTO ruta_calles (id_ejecucion, proveedor, perfil, distancia_m, duracion_s,
                                     geometria, tramos, indices_paradas)
            VALUES (:e, :p, :perfil, :d, :t, CAST(:g AS jsonb), CAST(:tr AS jsonb), CAST(:i AS jsonb))
            ON CONFLICT (id_ejecucion) DO NOTHING
        """), {"e": id_ejecucion, "p": t["proveedor"], "perfil": RUTEO_PERFIL, "d": t["distancia_m"],
               "t": t["duracion_s"], "g": json.dumps(t["geometria"]), "tr": json.dumps(t["tramos"]),
               "i": json.dumps(t["indices_paradas"])})
        fila = con.execute(text("SELECT * FROM ruta_calles WHERE id_ejecucion = :e"),
                           {"e": id_ejecucion}).mappings().one()
        log.info("Agente %s: trazo por calles de %.1f km (%s)", id_ejecucion, fila["distancia_m"] / 1000,
                 fila["proveedor"])

    p = recta["properties"]
    orden = p["hotspots"]
    paradas = orden + [orden[0]] if p["ruta_cerrada"] and len(orden) > 1 else list(orden)
    if len(orden) == 1:
        paradas = [orden[0], orden[0]]
    tramos = [{"desde": paradas[i], "hasta": paradas[i + 1], **t} for i, t in enumerate(fila["tramos"])]
    recta_m = float(p["distancia_m"] or 0)
    calles_m = float(fila["distancia_m"])
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": fila["geometria"]},
        "properties": {
            **p,
            "distancia_recta_m": recta_m,
            "distancia_m": calles_m,
            "duracion_s": fila["duracion_s"],
            "diferencia_pct": round((calles_m / recta_m - 1) * 100, 1) if recta_m > 0 else None,
            "indices_paradas": fila["indices_paradas"],
            "tramos": tramos,
            "proveedor": fila["proveedor"],
            "perfil": fila["perfil"],
            "atribucion": ATRIBUCION,
        },
    }
