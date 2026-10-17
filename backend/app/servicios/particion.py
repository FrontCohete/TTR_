"""Louvain: repartir los hotspots vigentes en N grafos (etapa 4).

Decisiones (ver claude/DECISIONES_BACKEND.md, etapa 4):
  * distancias haversine entre medoides (radio 6,371,008.8 m), igual que la vista Rutas;
  * grafo para Louvain: cada hotspot se une con sus 4 vecinos más cercanos, peso 1000 / distancia;
  * se busca una «resolución» que dé exactamente N comunidades (semilla fija 42) y, de preferencia,
    todas con al menos MIN_NODOS = 5 hotspots (etapa 5: un agente con 2 o 3 hotspots no tiene ruta
    que buscar); si ninguna resolución cumple el mínimo, se usa la primera que da N; si ninguna da N,
    se fusiona la comunidad más chica con la más cercana hasta llegar a N;
  * los grafos se numeran de norte a sur y llevan los colores fijos del frontend;
  * se guardan TODAS las parejas de hotspots dentro de cada grafo (las necesita el genético);
  * mismo análisis + mismo N → se reutiliza la partición que ya existe.

La parte de cálculo no toca la base; la parte de guardado recibe una conexión con transacción.
"""
import json
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import pandas as pd
from sqlalchemy import text

RADIO_TIERRA_M = 6_371_008.8
VECINOS = 4
SEMILLA = 42
MIN_NODOS = 5                                   # preferencia de tamaño mínimo por grafo (etapa 5)
COLORES = ["#1F5FD0", "#B87A00", "#13907A", "#8E3B9E", "#4E6B1F"]      # grafo 1…5
RESOLUCIONES = np.geomspace(0.002, 20, 500)    # de menos a más comunidades


class SinAnalisis(LookupError):
    """No hay análisis vigente. La ruta responde 404."""


class HotspotsInsuficientes(ValueError):
    """Hay menos hotspots que grafos pedidos. La ruta responde 409."""


# ------------------------------------------------------------------ distancias
def haversine(lat1, lon1, lat2, lon2):
    """Distancia en metros sobre la esfera (funciona con números o arreglos)."""
    f1, f2 = np.radians(lat1), np.radians(lat2)
    df, dl = f2 - f1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(df / 2) ** 2 + np.cos(f1) * np.cos(f2) * np.sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA_M * np.arcsin(np.sqrt(a))


def matriz_distancias(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Matriz n × n de distancias haversine (metros) entre todos los medoides."""
    return haversine(lat[:, None], lon[:, None], lat[None, :], lon[None, :])


# ------------------------------------------------------------------ grafo y Louvain
def grafo_vecinos(ids: list[int], D: np.ndarray, k: int = VECINOS) -> nx.Graph:
    """Une cada hotspot con sus k vecinos más cercanos (peso = 1000 / distancia en m)."""
    G = nx.Graph()
    G.add_nodes_from(ids)
    for i in range(len(ids)):
        orden = [j for j in np.argsort(D[i]) if j != i][:k]
        for j in orden:
            G.add_edge(ids[i], ids[j], weight=1000.0 / max(float(D[i, j]), 1.0))
    return G


def fusionar(comunidades: list[set], posicion: dict, n: int) -> list[set]:
    """Junta la comunidad más chica con la más cercana (enlace simple) hasta que queden n."""
    comunidades = [set(c) for c in comunidades]
    while len(comunidades) > n:
        comunidades.sort(key=len)
        chica, resto = comunidades[0], comunidades[1:]

        def separacion(otra):
            return min(haversine(*posicion[a], *posicion[b]) for a in chica for b in otra)

        destino = min(range(len(resto)), key=lambda i: separacion(resto[i]))
        resto[destino] |= chica
        comunidades = resto
    return comunidades


def louvain_n(G: nx.Graph, n: int, posicion: dict, semilla: int = SEMILLA, minimo: int = MIN_NODOS):
    """Exactamente n comunidades, de preferencia todas con ≥ `minimo` nodos.

    Devuelve (comunidades, resolución, se_fusionó, mínimo_cumplido).
      1. la primera resolución que da n comunidades y todas cumplen el mínimo;
      2. si ninguna cumple, la primera que da n (lo que se elegía antes de la etapa 5);
      3. si ninguna da n, la fusión de respaldo.
    """
    cumple = lambda cs: min(len(c) for c in cs) >= minimo       # noqa: E731
    if n == 1:
        return [set(G.nodes)], None, False, G.number_of_nodes() >= minimo
    respaldo = None                             # la primera que da n aunque no cumpla el mínimo
    mas_cercana = None                          # la primera resolución que dé MÁS de n
    for r in RESOLUCIONES:
        comunidades = nx.community.louvain_communities(G, weight="weight", resolution=float(r), seed=semilla)
        if len(comunidades) == n:
            if cumple(comunidades):
                return comunidades, float(r), False, True
            if respaldo is None:
                respaldo = (comunidades, float(r))
        if len(comunidades) > n and mas_cercana is None:
            mas_cercana = (comunidades, float(r))
    if respaldo is not None:
        return respaldo[0], respaldo[1], False, False
    if mas_cercana is None:                     # ni con resolución 20 hubo suficientes
        mas_cercana = ([{v} for v in G.nodes], None)
    comunidades, r = mas_cercana
    comunidades = fusionar(comunidades, posicion, n)
    return comunidades, r, True, cumple(comunidades)


# ------------------------------------------------------------------ cálculo completo
@dataclass
class Resultado:
    n_grafos: int
    resolucion: float | None
    modularidad: float
    fusion: bool
    grafos: list[dict] = field(repr=False)      # numero, color, hotspots, aristas
    minimo_cumplido: bool = True                # todos los grafos tienen ≥ MIN_NODOS hotspots


def particionar(hotspots: pd.DataFrame, n: int, semilla: int = SEMILLA) -> Resultado:
    """hotspots: columnas id_hotspot, etiqueta, lat, lon. No toca la base."""
    if len(hotspots) < n:
        raise HotspotsInsuficientes(
            f"El análisis vigente solo tiene {len(hotspots)} hotspots: no alcanzan para {n} grafos.")
    h = hotspots.sort_values("etiqueta").reset_index(drop=True)
    ids = [int(i) for i in h.id_hotspot]
    lat, lon = h.lat.to_numpy(float), h.lon.to_numpy(float)
    D = matriz_distancias(lat, lon)
    posicion = {ids[i]: (lat[i], lon[i]) for i in range(len(ids))}
    indice = {ids[i]: i for i in range(len(ids))}

    G = grafo_vecinos(ids, D)
    comunidades, resolucion, fusion, minimo_cumplido = louvain_n(G, n, posicion, semilla)
    modularidad = float(nx.community.modularity(G, comunidades, weight="weight")) if n > 1 else 0.0

    # de norte a sur: la latitud promedio más alta es el grafo 1
    comunidades = sorted(comunidades, key=lambda c: -np.mean([posicion[v][0] for v in c]))
    grafos = []
    for numero, c in enumerate(comunidades, start=1):
        miembros = sorted(c, key=lambda v: indice[v])                      # H-01 primero
        aristas = [(a, b, round(float(D[indice[a], indice[b]]), 1))
                   for x, a in enumerate(miembros) for b in miembros[x + 1:]]
        aristas = [(min(a, b), max(a, b), d) for a, b, d in aristas]       # id_origen < id_destino
        grafos.append({"numero": numero, "color": COLORES[numero - 1],
                       "hotspots": miembros, "aristas": aristas})
    return Resultado(n, resolucion, round(modularidad, 4), fusion, grafos, minimo_cumplido)


# ------------------------------------------------------------------ base de datos
def analisis_vigente(con) -> int:
    id_analisis = con.execute(text("SELECT id_analisis FROM analisis_hdbscan WHERE vigente")).scalar()
    if id_analisis is None:
        raise SinAnalisis("Todavía no hay un análisis: carga un dataset para generar los hotspots.")
    return id_analisis


def leer_hotspots(con, id_analisis: int) -> pd.DataFrame:
    return pd.DataFrame(con.execute(text("""
        SELECT id_hotspot, etiqueta, lat_centroide AS lat, lon_centroide AS lon
        FROM hotspot WHERE id_analisis = :a ORDER BY etiqueta
    """), {"a": id_analisis}).mappings().all(), columns=["id_hotspot", "etiqueta", "lat", "lon"])


def particion_existente(con, id_analisis: int, n: int, semilla: int = SEMILLA) -> int | None:
    return con.execute(text("""
        SELECT max(id_particion) FROM particion_louvain
        WHERE id_analisis = :a AND n_grafos = :n AND semilla = :s
    """), {"a": id_analisis, "n": n, "s": semilla}).scalar()


def marcar_vigente(con, id_analisis: int, id_particion: int) -> None:
    """Una partición vigente por análisis (índice ux_particion_una_vigente)."""
    con.execute(text("UPDATE particion_louvain SET vigente = false WHERE id_analisis = :a AND vigente"),
                {"a": id_analisis})
    con.execute(text("UPDATE particion_louvain SET vigente = true WHERE id_particion = :p"),
                {"p": id_particion})


def guardar(con, id_analisis: int, r: Resultado, semilla: int = SEMILLA) -> int:
    """particion_louvain → grafo → nodo_grafo → arista. No hace commit."""
    id_particion = con.execute(text("""
        INSERT INTO particion_louvain (id_analisis, n_grafos, resolucion, modularidad, semilla, vigente)
        VALUES (:a, :n, :r, :m, :s, false) RETURNING id_particion
    """), {"a": id_analisis, "n": r.n_grafos, "r": r.resolucion, "m": r.modularidad, "s": semilla}).scalar_one()

    for g in r.grafos:
        id_grafo = con.execute(text("""
            INSERT INTO grafo (id_particion, numero, n_nodos, n_aristas, color)
            VALUES (:p, :num, :nodos, :aristas, :color) RETURNING id_grafo
        """), {"p": id_particion, "num": g["numero"], "nodos": len(g["hotspots"]),
               "aristas": len(g["aristas"]), "color": g["color"]}).scalar_one()
        con.execute(text("INSERT INTO nodo_grafo (id_particion, id_hotspot, id_grafo) VALUES (:p, :h, :g)"),
                    [{"p": id_particion, "h": h, "g": id_grafo} for h in g["hotspots"]])
        if g["aristas"]:
            con.execute(text("""
                INSERT INTO arista (id_grafo, id_origen, id_destino, distancia_m) VALUES (:g, :o, :d, :m)
            """), [{"g": id_grafo, "o": a, "d": b, "m": m} for a, b, m in g["aristas"]])
    return id_particion


def respuesta(con, id_particion: int) -> dict:
    """La partición con el formato de README_INTEGRACION §4.10."""
    p = con.execute(text("""
        SELECT id_particion, id_analisis, n_grafos, resolucion, modularidad, semilla
        FROM particion_louvain WHERE id_particion = :p
    """), {"p": id_particion}).mappings().first()
    if p is None:
        raise LookupError(f"No existe la partición {id_particion}.")
    grafos = con.execute(text("""
        SELECT g.id_grafo, g.numero, g.color, g.n_nodos, g.n_aristas,
               array_agg(n.id_hotspot ORDER BY h.etiqueta) AS hotspots
        FROM grafo g
        JOIN nodo_grafo n USING (id_grafo, id_particion)
        JOIN hotspot h USING (id_hotspot)
        WHERE g.id_particion = :p
        GROUP BY g.id_grafo ORDER BY g.numero
    """), {"p": id_particion}).mappings().all()
    return {
        "id_particion": p["id_particion"], "id_analisis": p["id_analisis"],
        "n_grafos": p["n_grafos"], "modularidad": p["modularidad"], "resolucion": p["resolucion"],
        "grafos": [{"id_grafo": g["id_grafo"], "numero": g["numero"], "color": g["color"],
                    "n_nodos": g["n_nodos"], "n_aristas": g["n_aristas"],
                    "hotspots": [int(h) for h in g["hotspots"]]} for g in grafos],
    }


def nueva_particion(con, n: int, semilla: int = SEMILLA) -> dict:
    """POST /api/particiones: reutiliza o crea la partición del análisis vigente y la deja vigente.

    Corre dentro de la transacción de `con` (quien llama hace commit).
    """
    con.execute(text("SELECT pg_advisory_xact_lock(4004)"))        # una partición a la vez
    id_analisis = analisis_vigente(con)
    id_particion = particion_existente(con, id_analisis, n, semilla)
    if id_particion is None:
        r = particionar(leer_hotspots(con, id_analisis), n, semilla)
        id_particion = guardar(con, id_analisis, r, semilla)
        datos = respuesta(con, id_particion)
        datos["fusion"] = r.fusion
        datos["minimo_nodos"] = MIN_NODOS
        datos["minimo_cumplido"] = r.minimo_cumplido
        con.execute(text("UPDATE particion_louvain SET grafos_json = CAST(:j AS jsonb) WHERE id_particion = :p"),
                    {"j": json.dumps(datos), "p": id_particion})
    marcar_vigente(con, id_analisis, id_particion)
    return respuesta(con, id_particion)