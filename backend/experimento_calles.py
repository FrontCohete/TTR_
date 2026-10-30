"""Experimento: ¿cambia la ruta si el genético optimiza con distancias POR CALLES en vez de línea recta?

Hoy el genético optimiza con distancias en línea recta (haversine) y OSRM solo DIBUJA la ruta.
Este script compara, para cada grafo de las particiones pedidas:

  A · «como hoy»: el genético optimiza en línea recta; la ruta se mide después por calles.
  B · «por calles»: el genético optimiza con las distancias por calles de OSRM tal cual (ida ≠ vuelta).
  C · «por calles, simétrica»: optimiza con el promedio de ida y vuelta (versión 2, 29 oct: B salió peor
      que A en los grafos grandes porque la mutación por inversión pierde su efecto con ida ≠ vuelta).

Las tres rutas se miden con la MISMA vara (distancia por calles, en automóvil, respetando sentidos)
y se reporta cuánto mejora B frente a A. Además mide qué tan parejo es el rodeo por calles
(si el rodeo fuera igual en todas partes, A y B darían el mismo orden).

NO modifica la base ni la aplicación: solo lee hotspots y particiones. La matriz por calles se pide
a OSRM UNA vez (servicio «table», hasta 100 hotspots en una consulta) y se guarda en
resultados/experimento/ para no volver a pedirla.

Uso, desde la carpeta backend con (.venv):
    python experimento_calles.py                    # partición de 3 grafos, 5 semillas
    python experimento_calles.py --n 1 2 3 4 5 --semillas 10
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from sqlalchemy import text

from app.basedatos import engine
from app.servicios import genetico as AG
from app.servicios import particion as P
from app.servicios import ruteo

CARPETA = Path("resultados") / "experimento"
MAX_TABLA = 100           # coordenadas por consulta «table» en el servidor público de OSRM
PENALIZACION = 10.0       # si OSRM no encuentra camino entre dos hotspots: 10 × la distancia en línea recta


# ------------------------------------------------------------------ datos de la base
def leer_hotspots(con, id_analisis: int) -> list[dict]:
    return [dict(h) for h in con.execute(text("""
        SELECT id_hotspot, etiqueta, codigo, lat_centroide AS lat, lon_centroide AS lon
        FROM hotspot WHERE id_analisis = :a ORDER BY etiqueta
    """), {"a": id_analisis}).mappings()]


def leer_grafos(con, id_particion: int) -> list[dict]:
    filas = con.execute(text("""
        SELECT g.numero, g.id_grafo, n.id_hotspot
        FROM grafo g JOIN nodo_grafo n USING (id_grafo)
        JOIN hotspot h ON h.id_hotspot = n.id_hotspot
        WHERE g.id_particion = :p ORDER BY g.numero, h.etiqueta
    """), {"p": id_particion}).all()
    grafos: dict[int, dict] = {}
    for numero, id_grafo, h in filas:
        grafos.setdefault(numero, {"numero": numero, "id_grafo": id_grafo, "hotspots": []})["hotspots"].append(h)
    return [grafos[k] for k in sorted(grafos)]


# ------------------------------------------------------------------ matriz por calles (OSRM «table»)
def matriz_calles(coords: list[list[float]], consultar=None) -> tuple[np.ndarray, np.ndarray]:
    """Distancias (m) y duraciones (s) por calles entre todos los puntos [lon, lat]. Asimétricas."""
    if len(coords) > MAX_TABLA:
        raise SystemExit(f"Hay {len(coords)} hotspots y el servidor público acepta {MAX_TABLA} por consulta.")
    consultar = consultar or ruteo._consultar
    puntos = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords)
    datos = consultar(f"{ruteo.RUTEO_URL}/table/v1/{ruteo.RUTEO_PERFIL}/{puntos}?annotations=distance,duration")
    if datos.get("code") != "Ok" or "distances" not in datos:
        raise ruteo.RuteoNoDisponible(f"OSRM no devolvió la matriz ({datos.get('code')}: {datos.get('message', '')}).")
    a_num = lambda m: np.array([[np.nan if x is None else float(x) for x in fila] for fila in m])  # noqa: E731
    return a_num(datos["distances"]), a_num(datos.get("durations") or datos["distances"])


def matriz_guardada(id_analisis: int, hotspots: list[dict], consultar=None) -> tuple[np.ndarray, np.ndarray, bool]:
    """La matriz por calles del análisis: de resultados/experimento/ si ya existe, si no se pide a OSRM."""
    CARPETA.mkdir(parents=True, exist_ok=True)
    archivo = CARPETA / f"matriz_calles_analisis{id_analisis}.json"
    ids = [h["id_hotspot"] for h in hotspots]
    if archivo.exists():
        g = json.loads(archivo.read_text(encoding="utf-8"))
        if g["ids"] == ids:
            return np.array(g["distancias_m"], dtype=float), np.array(g["duraciones_s"], dtype=float), True
    dist, dur = matriz_calles([[float(h["lon"]), float(h["lat"])] for h in hotspots], consultar)
    archivo.write_text(json.dumps({
        "id_analisis": id_analisis, "ids": ids, "proveedor": f"osrm:{ruteo.RUTEO_URL}", "perfil": ruteo.RUTEO_PERFIL,
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "distancias_m": np.where(np.isnan(dist), None, dist).tolist(),
        "duraciones_s": np.where(np.isnan(dur), None, dur).tolist(),
    }), encoding="utf-8")
    return dist, dur, False


# ------------------------------------------------------------------ medir y comparar
def largo(orden: list[int], D: np.ndarray, cerrada: bool = True) -> float:
    """Distancia de recorrer `orden` (índices) con la matriz D, respetando la dirección."""
    d = sum(D[a, b] for a, b in zip(orden, orden[1:]))
    if cerrada and len(orden) > 1:
        d += D[orden[-1], orden[0]]
    return float(d)


def rodeo(Dh: np.ndarray, Dc: np.ndarray, minimo_m: float = 300) -> dict:
    """Qué tan parejo es el factor calles / línea recta entre pares de hotspots (sin los muy cercanos)."""
    i, j = np.where((Dh >= minimo_m) & ~np.eye(len(Dh), dtype=bool) & np.isfinite(Dc))
    f = Dc[i, j] / Dh[i, j]
    asim = np.abs(Dc - Dc.T)[i, j] / np.maximum(Dc[i, j], 1)
    return {"pares": int(len(f)), "p10": float(np.percentile(f, 10)), "mediana": float(np.median(f)),
            "p90": float(np.percentile(f, 90)), "cv": float(np.std(f) / np.mean(f)),
            "asimetria_mediana": float(np.median(asim))}


def mejor_sentido(orden: list[int], D: np.ndarray) -> float:
    """Un circuito se puede recorrer en los dos sentidos: con calles de un sentido, se toma el más corto."""
    return min(largo(orden, D), largo(orden[::-1], D))


def comparar_grafo(ids: list[int], Dh: np.ndarray, Dc: np.ndarray, semillas: list[int]) -> list[dict]:
    """Tres formas de optimizar; las tres rutas se miden por calles (en su mejor sentido).

    A · línea recta (como hoy) · B · calles tal cual (asimétrica: ida ≠ vuelta)
    C · calles simétrica (promedio de ida y vuelta): el genético conserva su mutación por inversión
        intacta, porque voltear un tramo no cambia su costo; luego se elige el mejor sentido.
    """
    Ds = (Dc + Dc.T) / 2
    nodos = list(range(len(ids)))
    filas = []
    for s in semillas:
        p = AG.Parametros(semilla=s)
        a = AG.ejecutar_ag(nodos, Dh, p, registro=False)
        b = AG.ejecutar_ag(nodos, Dc, p, registro=False)
        c = AG.ejecutar_ag(nodos, Ds, p, registro=False)
        filas.append({
            "semilla": s,
            "A_recta_m": largo(a.ruta_optima, Dh),
            "A_calles_m": mejor_sentido(a.ruta_optima, Dc),
            "B_calles_m": mejor_sentido(b.ruta_optima, Dc),
            "C_calles_m": mejor_sentido(c.ruta_optima, Dc),
            "gen_mejor_A": a.generacion_mejor, "gen_mejor_B": b.generacion_mejor, "gen_mejor_C": c.generacion_mejor,
            "segundos": a.duracion_s + b.duracion_s + c.duracion_s,
        })
    return filas


def _mismo_ciclo(x: list[int], y: list[int]) -> bool:
    """El mismo circuito aunque empiece en otro hotspot (no cuenta el sentido inverso: las calles tienen sentido)."""
    if len(x) != len(y) or not x:
        return False
    k = y.index(x[0])
    return x == y[k:] + y[:k]


def km(m: float) -> str:
    return f"{m / 1000:6.2f}"


def main():
    ap = argparse.ArgumentParser(description="Línea recta frente a calles como función objetivo del genético.")
    ap.add_argument("--n", type=int, nargs="+", default=[3], help="particiones a probar (1 a 5)")
    ap.add_argument("--semillas", type=int, default=5, help="corridas por grafo con semillas 1, 2, …")
    a = ap.parse_args()
    semillas = list(range(1, a.semillas + 1))

    with engine.connect() as con:
        id_analisis = P.analisis_vigente(con)
        hotspots = leer_hotspots(con, id_analisis)
        particiones = {}
        for n in a.n:
            idp = P.particion_existente(con, id_analisis, n)
            if idp is None:
                raise SystemExit(f"No hay partición de {n} grafos del análisis {id_analisis}: créala en Analizar "
                                 "(Repartir) o con python exportar_grafos.py.")
            particiones[n] = (idp, leer_grafos(con, idp))
    print(f"Análisis vigente {id_analisis}: {len(hotspots)} hotspots")

    t0 = time.perf_counter()
    try:
        Dc_todo, _, guardada = matriz_guardada(id_analisis, hotspots)
    except ruteo.RuteoNoDisponible as error:
        raise SystemExit(f"No se pudo obtener la matriz por calles: {error}")
    print(f"Matriz por calles {len(hotspots)} × {len(hotspots)} "
          f"{'leída de resultados/experimento' if guardada else f'pedida a OSRM ({time.perf_counter() - t0:.1f} s)'}")
    lat = np.array([float(h["lat"]) for h in hotspots])
    lon = np.array([float(h["lon"]) for h in hotspots])
    Dh_todo = P.matriz_distancias(lat, lon)
    huecos = int(np.isnan(Dc_todo).sum())
    if huecos:
        print(f"  Aviso: {huecos} pares sin camino por calles; se penalizan con {PENALIZACION:.0f} × la línea recta.")
        Dc_todo = np.where(np.isnan(Dc_todo), Dh_todo * PENALIZACION, Dc_todo)
    np.fill_diagonal(Dc_todo, 0)

    r = rodeo(Dh_todo, Dc_todo)
    print(f"\nRodeo por calles entre {r['pares']:,} pares de hotspots (a más de 300 m):")
    print(f"  calles / línea recta: 10 % de los pares ≤ {r['p10']:.2f} · mediana {r['mediana']:.2f} · "
          f"10 % de los pares ≥ {r['p90']:.2f}   (variación {100 * r['cv']:.0f} %)")
    print(f"  ida y vuelta distintas (calles de un sentido): diferencia mediana {100 * r['asimetria_mediana']:.1f} %")
    print("  → si el rodeo fuera igual en todas partes, optimizar en línea recta bastaría.\n")

    pos = {h["id_hotspot"]: i for i, h in enumerate(hotspots)}
    detalle, resumen, ya = [], [], {}
    print(f"Semillas por grafo: {len(semillas)} · ruta cerrada · {ruteo.RUTEO_PERFIL} · 100 × 1000, K 5, OX, inversión")
    print("Las tres rutas se miden por calles, en su mejor sentido. Mejora = cuánto más corta que A.\n")
    print(f"{'N':>2} {'grafo':>5} {'nodos':>5} │ {'A recta':>9} │ {'B calles':>9} {'mejora':>7} {'(mín–máx)':>15} │ "
          f"{'C calles sim.':>13} {'mejora':>7} {'(mín–máx)':>15}")
    for n, (idp, grafos) in particiones.items():
        tot = {"A": 0.0, "B": 0.0, "C": 0.0}
        for g in grafos:
            idx = [pos[h] for h in g["hotspots"]]
            clave = tuple(sorted(g["hotspots"]))
            if clave not in ya:                       # el mismo grafo aparece en varias particiones
                Dh, Dc = Dh_todo[np.ix_(idx, idx)], Dc_todo[np.ix_(idx, idx)]
                ya[clave] = comparar_grafo(g["hotspots"], Dh, Dc, semillas)
            filas = ya[clave]
            for f in filas:
                detalle.append({"analisis": id_analisis, "particion": idp, "N": n, "grafo": g["numero"],
                                "nodos": len(idx), **f})
            m = {k: st.mean(f[f"{k}_calles_m"] for f in filas) for k in "ABC"}
            mej = {k: [100 * (1 - f[f"{k}_calles_m"] / f["A_calles_m"]) for f in filas] for k in "BC"}
            for k in tot:
                tot[k] += m[k]
            resumen.append({"N": n, "grafo": g["numero"], "nodos": len(idx),
                            **{f"{k}_calles_km": m[k] / 1000 for k in "ABC"},
                            **{f"mejora_{k}_pct": st.mean(mej[k]) for k in "BC"},
                            **{f"mejora_{k}_min": min(mej[k]) for k in "BC"},
                            **{f"mejora_{k}_max": max(mej[k]) for k in "BC"}})
            txt = lambda k: f"{km(m[k])} km {st.mean(mej[k]):>6.1f} % ({min(mej[k]):>5.1f}–{max(mej[k]):>5.1f} %)"  # noqa: E731
            print(f"{n:>2} {g['numero']:>5} {len(idx):>5} │ {km(m['A'])} km │ {txt('B')} │ {'':>4}{txt('C')}")
        print(f"{n:>2} {'total':>5} {'':>5} │ {km(tot['A'])} km │ {km(tot['B'])} km "
              f"{100 * (1 - tot['B'] / tot['A']):>6.1f} %{'':>16} │ {'':>4}{km(tot['C'])} km "
              f"{100 * (1 - tot['C'] / tot['A']):>6.1f} %\n")

    CARPETA.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y-%m-%d_%H%M")
    with open(CARPETA / f"experimento_calles_{marca}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(detalle[0]))
        w.writeheader()
        w.writerows(detalle)
    (CARPETA / f"experimento_calles_{marca}.json").write_text(json.dumps(
        {"analisis": id_analisis, "semillas": semillas, "rodeo": r, "resumen": resumen}, indent=1), encoding="utf-8")
    print("A = optimiza en línea recta (como hoy) · B = optimiza por calles con ida ≠ vuelta ·")
    print("C = optimiza por calles con el promedio de ida y vuelta. Todas medidas por calles.")
    print(f"Tiempo total {time.perf_counter() - t0:.0f} s · detalle en {CARPETA}\\experimento_calles_{marca}.csv y .json")


if __name__ == "__main__":
    main()