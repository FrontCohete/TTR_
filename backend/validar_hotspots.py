"""Brecha G2: ¿los hotspots son producto del azar? Prueba estadística contra aleatoriedad espacial completa.

Hipótesis nula (H0): los delitos del análisis vigente ocurren en cualquier punto de la GAM con la misma
probabilidad (proceso de Poisson homogéneo, «aleatoriedad espacial completa»). Bajo H0 se simulan S
conjuntos con el MISMO número de puntos, uniformes dentro del polígono de la GAM (rasterizado a 25 m:
se elige una celda interior al azar y un punto uniforme dentro de ella; NumPy con semilla), y se
compara contra los datos reales. (No se usa ST_GeneratePoints de PostGIS: reparte los puntos por
celdas y quedan más regulares que el azar puro, lo que haría la prueba demasiado fácil.)

  1. Clark–Evans (agrupamiento global): R = distancia media al vecino más cercano observada ÷ esperada
     bajo H0. R < 1 indica agrupamiento. Se reporta el valor z clásico y el valor p de Monte Carlo
     (el de Monte Carlo no depende del efecto de borde). Se repite con ubicaciones únicas, porque la FGJ
     registra varias víctimas en el mismo domicilio y eso por sí solo acerca puntos.
  2. Cada hotspot (estadístico de barrido, tipo Kulldorff): c = delitos dentro de un radio alrededor de su
     medoide, con DOS radios: p90 (el 90 % de sus miembros, el de la base) y p50 (su núcleo: el 50 %).
     El círculo p90 describe mal a los hotspots alargados (corredores): abarca terreno vacío; el p50 prueba
     el núcleo. En cada simulación se busca el MÁXIMO de delitos que junta un
     círculo de ese radio en CUALQUIER lugar de la GAM. p = (1 + #simulaciones con máximo ≥ c) / (S + 1).
     Como se compara con el máximo de todo el territorio, ya considera que el hotspot se eligió por ser
     denso. Conteos en una rejilla de 25 m (histograma + convolución con un disco); el radio se redondea
     hacia arriba al múltiplo de 25 m (conservador).
  3. HDBSCAN sobre datos al azar: con los mismos parámetros (min_cluster_size, min_samples), ¿cuántos
     «hotspots» encuentra en cada simulación y con qué tamaño?

NO modifica la base. Escribe resultados/validacion/hotspots_<fecha>.csv, .json y .md.

Uso, desde la carpeta backend con (.venv):
    python validar_hotspots.py                                (99 simulaciones + 19 con HDBSCAN, ≈ 15 min)
    python validar_hotspots.py --sim-hdbscan 0                (sin HDBSCAN al azar, ≈ 4 min)
    python validar_hotspots.py --simulaciones 19 --sim-hdbscan 3   (prueba rápida)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics as st
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve
from scipy.spatial import cKDTree
from sqlalchemy import text

from app.basedatos import engine
from app.servicios import clustering as C
from app.servicios import particion as P

CARPETA = Path("resultados") / "validacion"
CELDA = 25.0                     # m, rejilla para contar delitos en círculos


# ------------------------------------------------------------------ datos
def poligono_gam(con) -> dict:
    fila = con.execute(text("""
        SELECT id_alcaldia, nombre, ST_Area(g) AS area_m2, ST_AsGeoJSON(g) AS geojson,
               ST_XMin(g) AS x0, ST_YMin(g) AS y0, ST_XMax(g) AS x1, ST_YMax(g) AS y1
        FROM alcaldia, LATERAL (SELECT ST_SimplifyPreserveTopology(ST_Transform(geom, 32614), 5) AS g) t
        ORDER BY (nombre ILIKE '%madero%') DESC, id_alcaldia LIMIT 1
    """)).mappings().one()
    gam = dict(fila)
    forma = json.loads(gam.pop("geojson"))
    poligonos = forma["coordinates"] if forma["type"] == "MultiPolygon" else [forma["coordinates"]]
    gam["anillos"] = [np.array(anillo, dtype=float) for pol in poligonos for anillo in pol]
    return gam


def dentro(px: np.ndarray, py: np.ndarray, anillos: list[np.ndarray]) -> np.ndarray:
    """Regla par-impar (rayo horizontal): True si el punto está dentro (los huecos quedan fuera)."""
    adentro = np.zeros(len(px), dtype=bool)
    for a in anillos:
        x1, y1, x2, y2 = a[:-1, 0], a[:-1, 1], a[1:, 0], a[1:, 1]
        for k in range(len(x1)):
            cruza = (y1[k] > py) != (y2[k] > py)
            if cruza.any():
                xc = x1[k] + (py - y1[k]) * (x2[k] - x1[k]) / (y2[k] - y1[k])
                adentro ^= cruza & (px < xc)
    return adentro


def puntos_al_azar(celdas: np.ndarray, rejilla: "Rejilla", n: int, semilla: int) -> np.ndarray:
    """n puntos uniformes dentro de la GAM (metros, UTM 14N). Misma semilla → mismos puntos."""
    rng = np.random.default_rng(semilla)
    elegidas = celdas[rng.integers(len(celdas), size=n)]
    x = rejilla.x0 + (elegidas[:, 1] + rng.random(n)) * CELDA
    y = rejilla.y0 + (elegidas[:, 0] + rng.random(n)) * CELDA
    return np.c_[x, y]


def hotspots(con, id_analisis: int) -> list[dict]:
    """Cada hotspot con su medoide en metros, su radio p90 (el de la base) y el radio p50 de sus miembros."""
    return [dict(h) for h in con.execute(text("""
        SELECT h.etiqueta, h.codigo, h.n_puntos, h.radio_m, coalesce(h.colonia, '') AS colonia,
               ST_X(c.g) AS x, ST_Y(c.g) AS y,
               (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY ST_Distance(ST_Transform(p.geom, 32614), c.g))
                FROM membresia_hotspot m JOIN punto_delictivo p USING (id_punto)
                WHERE m.id_analisis = h.id_analisis AND m.id_hotspot = h.id_hotspot) AS radio_p50
        FROM hotspot h, LATERAL (SELECT ST_Transform(h.geom, 32614) AS g) c
        WHERE h.id_analisis = :a ORDER BY h.etiqueta
    """), {"a": id_analisis}).mappings()]


# ------------------------------------------------------------------ 1 · Clark–Evans
def clark_evans(xy: np.ndarray, area: float) -> dict:
    n = len(xy)
    d, _ = cKDTree(xy).query(xy, k=2)
    r_obs = float(d[:, 1].mean())
    densidad = n / area
    r_esp = 0.5 / math.sqrt(densidad)
    ee = 0.26136 / math.sqrt(n * densidad)
    return {"n": n, "r_obs_m": r_obs, "r_esp_m": r_esp, "R": r_obs / r_esp, "z": (r_obs - r_esp) / ee,
            "duplicados_pct": 100 * float((d[:, 1] == 0).mean())}


# ------------------------------------------------------------------ 2 · barrido con círculos
class Rejilla:
    def __init__(self, gam: dict):
        self.x0, self.y0 = gam["x0"], gam["y0"]
        self.nx = int(math.ceil((gam["x1"] - self.x0) / CELDA)) + 1
        self.ny = int(math.ceil((gam["y1"] - self.y0) / CELDA)) + 1

    def histograma(self, xy: np.ndarray) -> np.ndarray:
        h, _, _ = np.histogram2d(xy[:, 1], xy[:, 0], bins=[self.ny, self.nx],
                                 range=[[self.y0, self.y0 + self.ny * CELDA], [self.x0, self.x0 + self.nx * CELDA]])
        return h

    def celda(self, x: float, y: float) -> tuple[int, int]:
        return (min(self.ny - 1, max(0, int((y - self.y0) // CELDA))),
                min(self.nx - 1, max(0, int((x - self.x0) // CELDA))))


def disco(radio: float) -> np.ndarray:
    k = int(math.ceil(radio / CELDA))
    i, j = np.mgrid[-k:k + 1, -k:k + 1]
    return ((i * CELDA) ** 2 + (j * CELDA) ** 2 <= radio ** 2).astype(float)


def conteos(hist: np.ndarray, radios: list[float]) -> dict[float, np.ndarray]:
    """Delitos dentro de un círculo de cada radio, centrado en cada celda."""
    return {r: np.rint(fftconvolve(hist, disco(r), mode="same")) for r in radios}


# ------------------------------------------------------------------ principal
def main():
    ap = argparse.ArgumentParser(description="¿Los hotspots son producto del azar? (brecha G2)")
    ap.add_argument("--simulaciones", type=int, default=99, help="simulaciones para Clark–Evans y el barrido")
    ap.add_argument("--sim-hdbscan", type=int, default=19, help="simulaciones en las que se corre HDBSCAN")
    a = ap.parse_args()
    S = a.simulaciones
    t0 = time.perf_counter()

    with engine.connect() as con:
        id_analisis = P.analisis_vigente(con)
        params = con.execute(text("SELECT min_cluster_size, min_samples FROM analisis_hdbscan WHERE id_analisis = :a"),
                             {"a": id_analisis}).mappings().one()
        reales = C.leer_puntos(con)
        gam = poligono_gam(con)
        hs = hotspots(con, id_analisis)
    xy = reales[["x", "y"]].to_numpy(dtype=float)
    n, area = len(xy), float(gam["area_m2"])
    print(f"Análisis {id_analisis}: {n:,} delitos y {len(hs)} hotspots en {gam['nombre']} ({area / 1e6:.1f} km²)")
    print(f"H0: los delitos ocurren al azar en la alcaldía · {S} simulaciones con {n:,} puntos cada una\n")

    # ---- observados
    ce = clark_evans(xy, area)
    unicos = np.unique(xy, axis=0)
    ce_u = clark_evans(unicos, area)
    rejilla = Rejilla(gam)
    fil, col = np.mgrid[0:rejilla.ny, 0:rejilla.nx]
    centros_x = (rejilla.x0 + (col.ravel() + 0.5) * CELDA)
    centros_y = (rejilla.y0 + (fil.ravel() + 0.5) * CELDA)
    interior = dentro(centros_x, centros_y, gam["anillos"])
    celdas = np.c_[fil.ravel()[interior], col.ravel()[interior]]
    print(f"Rejilla de {CELDA:.0f} m: {len(celdas):,} celdas dentro de la alcaldía "
          f"({len(celdas) * CELDA ** 2 / 1e6:.1f} km² frente a {area / 1e6:.1f} km² del polígono)\n")
    PRUEBAS = (("p90", "radio_m", "90 % de sus delitos"), ("p50", "radio_p50", "núcleo: 50 % de sus delitos"))
    for h in hs:
        for k, campo, _ in PRUEBAS:
            h[f"radio_{k}_prueba_m"] = max(CELDA, math.ceil(float(h[campo] or 0) / CELDA) * CELDA)
    radios = sorted({h[f"radio_{k}_prueba_m"] for h in hs for k, _, _ in PRUEBAS})
    obs = conteos(rejilla.histograma(xy), radios)
    for h in hs:
        for k, _, _ in PRUEBAS:
            r = h[f"radio_{k}_prueba_m"]
            h[f"conteo_{k}"] = int(obs[r][rejilla.celda(h["x"], h["y"])])
            h[f"esperado_{k}"] = n / area * math.pi * r ** 2
            h[f"maximos_{k}"] = []

    # ---- simulaciones bajo H0
    R_sim, R_sim_u, hdb = [], [], []
    for s in range(1, S + 1):
        sim = puntos_al_azar(celdas, rejilla, n, s)
        R_sim.append(clark_evans(sim, area)["R"])
        R_sim_u.append(clark_evans(sim[: len(unicos)], area)["R"])
        maxs = {r: float(c.max()) for r, c in conteos(rejilla.histograma(sim), radios).items()}
        for h in hs:
            for k, _, _ in PRUEBAS:
                h[f"maximos_{k}"].append(maxs[h[f"radio_{k}_prueba_m"]])
        if s <= a.sim_hdbscan:
            etiquetas, _ = C.agrupar(sim, params["min_cluster_size"], params["min_samples"])
            kk = C.contar(etiquetas)
            tamanos = np.bincount(etiquetas[etiquetas >= 0]) if kk else np.array([0])
            hdb.append({"semilla": s, "hotspots": kk, "ruido_pct": 100 * float((etiquetas < 0).mean()),
                        "mayor": int(tamanos.max())})
        if s % 10 == 0 or s == S:
            print(f"  simulación {s}/{S} · {time.perf_counter() - t0:.0f} s", flush=True)

    p_ce = (1 + sum(r <= ce["R"] for r in R_sim)) / (S + 1)
    p_ce_u = (1 + sum(r <= ce_u["R"] for r in R_sim_u)) / (S + 1)
    p_min = 1 / (S + 1)
    resumen_pruebas = {}
    for h in hs:
        for k, _, _ in PRUEBAS:
            mx = h.pop(f"maximos_{k}")
            h[f"p_{k}"] = (1 + sum(m >= h[f"conteo_{k}"] for m in mx)) / (S + 1)
            h[f"max_azar_{k}"] = max(mx)
            h[f"veces_esperado_{k}"] = h[f"conteo_{k}"] / h[f"esperado_{k}"] if h[f"esperado_{k}"] else None
            h[f"veces_max_azar_{k}"] = h[f"conteo_{k}"] / max(mx) if max(mx) else None
        h["p_alguno"] = min(h["p_p90"], h["p_p50"])
    for k, _, nombre in PRUEBAS:
        vec = [h[f"veces_esperado_{k}"] for h in hs]
        vmx = [h[f"veces_max_azar_{k}"] for h in hs]
        resumen_pruebas[k] = {
            "nombre": nombre, "significativos_p_minimo": sum(h[f"p_{k}"] <= p_min + 1e-12 for h in hs),
            "significativos_05": sum(h[f"p_{k}"] <= 0.05 for h in hs),
            "veces_esperado_mediana": st.median(vec), "veces_esperado_min": min(vec), "veces_esperado_max": max(vec),
            "veces_max_azar_mediana": st.median(vmx), "veces_max_azar_min": min(vmx),
            "radio_mediana_m": st.median(h[f"radio_{k}_prueba_m"] for h in hs)}
    sig_alguno = sum(h["p_alguno"] <= 0.05 for h in hs)
    no_sig = [h for h in hs if h["p_alguno"] > 0.05]

    # ---- reporte
    print("\n1 · Clark–Evans (vecino más cercano)")
    for nombre, c, rs, p in (("todos los delitos", ce, R_sim, p_ce), ("ubicaciones únicas", ce_u, R_sim_u, p_ce_u)):
        print(f"  {nombre:<20} R = {c['R']:.3f} (azar: {min(rs):.3f}–{max(rs):.3f}) · z = {c['z']:.1f} · "
              f"p Monte Carlo = {p:.3f} · n = {c['n']:,}")
    print(f"  {ce['duplicados_pct']:.1f} % de los delitos comparten coordenadas con otro (mismo domicilio).")
    print(f"\n2 · Barrido por hotspot ({S} simulaciones; el menor p posible es {p_min:.3f})")
    for k, _, nombre in PRUEBAS:
        r = resumen_pruebas[k]
        print(f"  radio {k} ({nombre}; mediana {r['radio_mediana_m']:.0f} m): {r['significativos_p_minimo']} de {len(hs)} "
              f"con p = {p_min:.3f} · {r['significativos_05']} con p ≤ 0.05 · delitos ÷ esperados al azar: mediana "
              f"{r['veces_esperado_mediana']:.1f}× (mín {r['veces_esperado_min']:.1f}×) · ÷ máximo al azar: mediana "
              f"{r['veces_max_azar_mediana']:.2f}×")
    print(f"  significativos con al menos uno de los dos radios (p ≤ 0.05): {sig_alguno} de {len(hs)}")
    for h in no_sig:
        print(f"  no significativo: {h['codigo']} ({h['n_puntos']} miembros, radio p90 {h['radio_m']:.0f} m / "
              f"p50 {h['radio_p50']:.0f} m, p = {h['p_p90']:.3f} / {h['p_p50']:.3f}, "
              f"{h['veces_esperado_p50']:.1f}× lo esperado en el núcleo)")
    if hdb:
        ks = [x["hotspots"] for x in hdb]
        print(f"\n3 · HDBSCAN con los mismos parámetros ({params['min_cluster_size']} / {params['min_samples']}) "
              f"sobre datos al azar ({len(hdb)} simulaciones)")
        print(f"  hotspots encontrados: {min(ks)}–{max(ks)} (promedio {st.mean(ks):.1f}) frente a {len(hs)} reales · "
              f"ruido {st.mean(x['ruido_pct'] for x in hdb):.1f} % · p = {(1 + sum(k >= len(hs) for k in ks)) / (len(hdb) + 1):.3f}")

    CARPETA.mkdir(parents=True, exist_ok=True)
    base = CARPETA / f"hotspots_{datetime.now().strftime('%Y-%m-%d_%H%M')}"
    campos = ["etiqueta", "codigo", "colonia", "n_puntos", "radio_m", "radio_p50"]
    for k, _, _ in PRUEBAS:
        campos += [f"radio_{k}_prueba_m", f"conteo_{k}", f"esperado_{k}", f"veces_esperado_{k}", f"max_azar_{k}",
                   f"veces_max_azar_{k}", f"p_{k}"]
    campos.append("p_alguno")
    with open(base.with_suffix(".csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(hs)
    resumen = {
        "analisis": id_analisis, "delitos": n, "hotspots": len(hs), "area_km2": area / 1e6, "simulaciones": S,
        "clark_evans": {**ce, "p_monte_carlo": p_ce, "R_azar_min": min(R_sim), "R_azar_max": max(R_sim)},
        "clark_evans_unicos": {**ce_u, "p_monte_carlo": p_ce_u, "R_azar_min": min(R_sim_u), "R_azar_max": max(R_sim_u)},
        "barrido": {"p_minimo": p_min, **resumen_pruebas, "significativos_alguno_05": sig_alguno,
                    "no_significativos": [h["codigo"] for h in no_sig]},
        "hdbscan_azar": hdb, "parametros_hdbscan": dict(params),
    }
    base.with_suffix(".json").write_text(json.dumps(resumen, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    md = [f"# G2 · ¿Los hotspots son producto del azar? · análisis {id_analisis} · {S} simulaciones", "",
          f"H0: los {n:,} delitos ocurren al azar dentro de {gam['nombre']} ({area / 1e6:.1f} km²).", "",
          "| Prueba | Resultado real | Bajo H0 (simulaciones) | p |", "|---|---|---|---|",
          f"| Clark–Evans, todos los delitos | R = {ce['R']:.3f} (z = {ce['z']:.1f}) | R = {min(R_sim):.3f}–{max(R_sim):.3f} | {p_ce:.3f} |",
          f"| Clark–Evans, ubicaciones únicas | R = {ce_u['R']:.3f} (z = {ce_u['z']:.1f}) | R = {min(R_sim_u):.3f}–{max(R_sim_u):.3f} | {p_ce_u:.3f} |"]
    for k, _, nombre in PRUEBAS:
        r = resumen_pruebas[k]
        md.append(f"| Barrido, radio {k} ({nombre}) | {r['significativos_p_minimo']} de {len(hs)} superan el máximo de "
                  f"todas las simulaciones | — | {p_min:.3f} cada uno |")
    md.append(f"| Barrido, cualquiera de los dos radios | {sig_alguno} de {len(hs)} con p ≤ 0.05 | — | — |")
    if hdb:
        md.append(f"| HDBSCAN ({params['min_cluster_size']} / {params['min_samples']}) | {len(hs)} hotspots | "
                  f"{min(ks)}–{max(ks)} hotspots (promedio {st.mean(ks):.1f}) | {(1 + sum(k >= len(hs) for k in ks)) / (len(hdb) + 1):.3f} |")
    md += ["", "| Hotspot | Colonia | Miembros | Radio p90 (m) | Veces lo esperado | p | Radio p50 (m) | Veces lo esperado | p |",
           "|---|---|---|---|---|---|---|---|---|"]
    for h in hs:
        md.append(f"| {h['codigo']} | {h['colonia']} | {h['n_puntos']} | {h['radio_m']:.0f} | {h['veces_esperado_p90']:.1f}× | "
                  f"{h['p_p90']:.3f} | {h['radio_p50']:.0f} | {h['veces_esperado_p50']:.1f}× | {h['p_p50']:.3f} |")
    base.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nTiempo total {time.perf_counter() - t0:.0f} s · resultados en {base}.csv, .json y .md")


if __name__ == "__main__":
    main()