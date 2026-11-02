"""Experimento 2 (versión solo-calles, 1 nov 2026): sectores grandes con calles CON SENTIDO.

En experimento_mutacion.py la mutación «mixta» (inversión o inserción) ganó entre las que respetan
sentidos, pero en los sectores gigantes (N = 1: 93 hotspots; N = 2: 75) quedó 6–8 % más larga que la
referencia (promedio de ida y vuelta). Aquí se prueban dos ayudas que usan SOLO calles con sentido:

  siembra     5 de las 100 rutas iniciales se construyen «yendo siempre al hotspot más cercano por
              calles con sentido» (cada una desde otro hotspot); las otras 95, al azar como siempre
  búsqueda    cada vez que aparece una mejor ruta, se le aplica una búsqueda local que mueve 1, 2 o 3
  local       hotspots seguidos a otra posición SIN voltearlos (or-opt), mientras acorte por calles
  pulido      la misma búsqueda local, pero solo UNA vez al final, sobre la mejor ruta del genético
  final       (no puede empeorar la ruta y no altera la evolución que se ve en Rutas)

Variantes:
  Ref.               promedio de ida y vuelta + inversión (la antigua C; no respeta sentidos al optimizar)
  Mixta              calles con sentido + mutación mixta (la ganadora del experimento 1)
  Mixta+siembra
  Mixta+búsqueda
  Mixta+pulido       pulido final
  Siembra+pulido     siembra + pulido final

No modifica genetico.py ni la base: arma en memoria una copia del genético con dos «ganchos»
(población inicial y después de cada generación). Necesita experimento_mutacion.py en la misma carpeta.

Uso, desde la carpeta backend con (.venv):
    python experimento_grandes.py                         (N = 1 y 2, 10 semillas, ≈ 10–15 min)
    python experimento_grandes.py --n 1 2 3 4 5           (todas, para ver que no empeora los chicos)
"""
from __future__ import annotations

import argparse
import csv
import inspect
import json
import statistics as st
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from app.basedatos import engine
from app.servicios import genetico as AG
from app.servicios import matriz_calles as M
from app.servicios import particion as P
from experimento_mutacion import leer_grafos, mixta, restaurar, usar_como_swap

CARPETA = Path("resultados") / "experimento"
VARIANTES = ("ref", "mixta", "siembra", "busqueda", "pulido", "siembra_pulido")
NOMBRE = {"ref": "Ref. (promedio)", "mixta": "Mixta", "siembra": "Mixta+siembra",
          "busqueda": "Mixta+búsqueda", "pulido": "Mixta+pulido", "siembra_pulido": "Siembra+pulido"}
N_SIEMBRA = 5

# ------------------------------------------------------------------ genético con ganchos (copia en memoria)
_FUENTE = inspect.getsource(AG.ejecutar_ag)
_INICIO = "    dist = distancias(pob, D, p.ruta_cerrada)\n"
_GENERACION = "        pob, dist = nueva, nueva_dist\n"
if _FUENTE.count(_INICIO) != 1 or _FUENTE.count(_GENERACION) != 1:
    raise SystemExit("genetico.py no es la versión esperada: manda app\\servicios\\genetico.py al chat.")
_FUENTE = (_FUENTE.replace(_INICIO, "    pob = _GANCHO_INICIO(pob, D)\n" + _INICIO
                                     + "    pob, dist = _GANCHO_GENERACION(pob, dist, D)\n")
                  .replace(_GENERACION, _GENERACION + "        pob, dist = _GANCHO_GENERACION(pob, dist, D)\n"))


def ag_con_ganchos(inicio, generacion):
    espacio = dict(vars(AG))
    espacio["_GANCHO_INICIO"] = inicio
    espacio["_GANCHO_GENERACION"] = generacion
    exec(_FUENTE, espacio)                                 # noqa: S102 (experimento local)
    return espacio["ejecutar_ag"]


def vecino_mas_cercano(D: list[list[float]], inicio: int) -> list[int]:
    """Ruta que desde `inicio` va siempre al hotspot sin visitar más cercano por calles con sentido."""
    n = len(D)
    ruta, libres = [inicio], set(range(n)) - {inicio}
    while libres:
        actual = D[ruta[-1]]
        siguiente = min(libres, key=actual.__getitem__)
        ruta.append(siguiente)
        libres.remove(siguiente)
    return ruta


def largo_cerrado(t: list[int], D: list[list[float]]) -> float:
    return sum(D[a][b] for a, b in zip(t, t[1:])) + D[t[-1]][t[0]]


def or_opt(t: list[int], D: list[list[float]], max_pasadas: int = 60) -> list[int]:
    """Búsqueda local con sentido: mueve 1–3 hotspots seguidos a otra posición sin voltearlos."""
    t = list(t)
    n = len(t)
    for _ in range(max_pasadas):
        mejoro = False
        for L in (1, 2, 3):
            if L >= n - 1:
                break
            i = 0
            while i < n:
                seg = [t[(i + k) % n] for k in range(L)]
                prev, nxt = t[(i - 1) % n], t[(i + L) % n]
                quita = D[prev][seg[0]] + D[seg[-1]][nxt] - D[prev][nxt]
                resto = [t[(i + L + k) % n] for k in range(n - L)]     # empieza en nxt, termina en prev
                mejor_j, mejor_d = -1, -1e-7
                for j in range(n - L - 1):                             # entre resto[j] y resto[j+1]
                    u, v = resto[j], resto[j + 1]
                    d = D[u][seg[0]] + D[seg[-1]][v] - D[u][v] - quita
                    if d < mejor_d:
                        mejor_j, mejor_d = j, d
                if mejor_j >= 0:
                    t = resto[:mejor_j + 1] + seg + resto[mejor_j + 1:]
                    mejoro = True
                i += 1
        if not mejoro:
            break
    return t


def correr(D: np.ndarray, semilla: int, variante: str):
    Dl = D.tolist()
    sembrar = variante in ("siembra", "siembra_pulido")
    buscar = variante == "busqueda"
    estado = {"mejor": float("inf")}

    def inicio(pob, _D):
        if not sembrar:
            return pob
        pob = pob.copy()
        for i in range(min(N_SIEMBRA, len(pob))):
            pob[i] = vecino_mas_cercano(Dl, int(pob[i, 0]))        # desde un hotspot distinto (al azar)
        return pob

    def generacion(pob, dist, _D):
        if not buscar:
            return pob, dist
        i = int(np.argmin(dist))
        if dist[i] < estado["mejor"] - 1e-6:
            ruta = or_opt(pob[i].tolist(), Dl)
            pob, dist = pob.copy(), dist.copy()
            pob[i] = ruta
            dist[i] = largo_cerrado(ruta, Dl)
            estado["mejor"] = dist[i]
        return pob, dist

    p = AG.Parametros(semilla=semilla, op_mutacion="inversion" if variante == "ref" else "swap")
    antes = usar_como_swap(mixta if variante != "ref" else AG.intercambiar)
    try:
        ejecutar = ag_con_ganchos(inicio, generacion)
        return ejecutar(list(range(len(D))), D, p, registro=False)
    finally:
        restaurar(antes)


def comparar(Dc: np.ndarray, semillas: list[int]) -> list[dict]:
    Ds = (Dc + Dc.T) / 2
    Dl = Dc.tolist()
    filas = []
    for s in semillas:
        f = {"semilla": s}
        for v in VARIANTES:
            t0 = time.perf_counter()
            r = correr(Ds if v == "ref" else Dc, s, v)
            ruta = r.ruta_optima
            if v in ("pulido", "siembra_pulido"):
                ruta = or_opt(ruta, Dl)                    # pulido final: solo puede acortar
            f[f"{v}_m"] = M.mejor_sentido(ruta, Dc)[0]
            f[f"{v}_gen"] = r.generacion_mejor
            f[f"{v}_s"] = round(time.perf_counter() - t0, 2)
        filas.append(f)
    return filas


def main():
    ap = argparse.ArgumentParser(description="Siembra y búsqueda local con calles de un sentido.")
    ap.add_argument("--n", type=int, nargs="+", default=[1, 2], help="particiones a probar (1 a 5)")
    ap.add_argument("--semillas", type=int, default=10, help="corridas por sector con semillas 1, 2, …")
    a = ap.parse_args()
    semillas = list(range(1, a.semillas + 1))

    with engine.connect() as con:
        id_analisis = P.analisis_vigente(con)
        m = M.obtener(con, id_analisis, pedir=False)
        if m is None:
            raise SystemExit("La matriz por calles no está guardada: corre primero python crear_matriz_calles.py")
        particiones = {}
        for n in a.n:
            idp = P.particion_existente(con, id_analisis, n)
            if idp is None:
                raise SystemExit(f"No hay partición de {n} grafos: créala con python exportar_grafos.py.")
            particiones[n] = leer_grafos(con, idp)
    print(f"Análisis vigente {id_analisis}: {len(m.ids)} hotspots · {len(semillas)} semillas · 100 × 1000")
    print("Todas optimizan con calles CON SENTIDO y mutación mixta, salvo la referencia.")
    print("Todas se miden por calles con sentido. Diferencia = contra la referencia (negativo = más corta).\n")

    t0 = time.perf_counter()
    detalle, resumen, ya = [], [], {}
    print(f"{'N':>2} {'sector':>6} {'nodos':>5} │ " + " │ ".join(f"{NOMBRE[v]:>19}" for v in VARIANTES) + " │ seg/corrida")
    for n, grafos in particiones.items():
        tot = dict.fromkeys(VARIANTES, 0.0)
        for g in grafos:
            clave = tuple(sorted(g["hotspots"]))
            if clave not in ya:
                ya[clave] = comparar(m.submatrices(g["hotspots"])["calles"], semillas)
            filas = ya[clave]
            for f in filas:
                detalle.append({"analisis": id_analisis, "N": n, "sector": g["numero"], "nodos": len(g["hotspots"]), **f})
            media = {v: st.mean(f[f"{v}_m"] for f in filas) for v in VARIANTES}
            seg = {v: st.mean(f[f"{v}_s"] for f in filas) for v in VARIANTES}
            for v in VARIANTES:
                tot[v] += media[v]
            ref = media["ref"]
            celdas = [f"{ref / 1000:8.2f} km{'':>8}"]
            celdas += [f"{media[v] / 1000:8.2f} km {round(100 * (media[v] / ref - 1), 1) + 0.0:+5.1f} %"
                       for v in VARIANTES[1:]]
            tiempos = " / ".join(f"{seg[v]:.1f}" for v in VARIANTES)
            print(f"{n:>2} {g['numero']:>6} {len(g['hotspots']):>5} │ " + " │ ".join(celdas) + f" │ {tiempos}")
            resumen.append({"N": n, "sector": g["numero"], "nodos": len(g["hotspots"]),
                            **{f"{v}_km": media[v] / 1000 for v in VARIANTES},
                            **{f"{v}_seg": seg[v] for v in VARIANTES}})
        ref = tot["ref"]
        celdas = [f"{ref / 1000:8.2f} km{'':>8}"]
        celdas += [f"{tot[v] / 1000:8.2f} km {round(100 * (tot[v] / ref - 1), 1) + 0.0:+5.1f} %" for v in VARIANTES[1:]]
        print(f"{n:>2} {'total':>6} {'':>5} │ " + " │ ".join(celdas) + "\n")

    CARPETA.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y-%m-%d_%H%M")
    with open(CARPETA / f"experimento_grandes_{marca}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(detalle[0]))
        w.writeheader()
        w.writerows(detalle)
    (CARPETA / f"experimento_grandes_{marca}.json").write_text(json.dumps(
        {"analisis": id_analisis, "semillas": semillas, "resumen": resumen}, indent=1), encoding="utf-8")
    print(f"Tiempo total {time.perf_counter() - t0:.0f} s · detalle en "
          f"{CARPETA}\\experimento_grandes_{marca}.csv y .json")


if __name__ == "__main__":
    main()
