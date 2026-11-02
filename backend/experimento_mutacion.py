"""Experimento (versión solo-calles, 1 nov 2026): ¿qué mutación funciona con calles de un sentido?

El genético optimiza SOLO con distancias por calles respetando sentidos (matriz asimétrica de
matriz_calles: de X a Y ≠ de Y a X). En el experimento anterior, con la mutación por INVERSIÓN el
genético rindió mal en sectores grandes: voltear un pedazo de ruta cambia el costo de todos sus
tramos cuando las calles tienen sentido, y deja de ser un ajuste fino. Aquí se comparan mutaciones
que NO voltean tramos:

  inversión     voltea un pedazo de la ruta (la de hoy)            38 61 75 48 72 → 38 72 48 75 61
  intercambio   cambia de lugar dos hotspots (ya existe: «swap»)   38 61 75 48 72 → 38 72 75 48 61
  inserción     saca un hotspot y lo mete más adelante             38 61 75 48 72 → 38 75 48 72 61
  mixta         inversión o inserción, alternando (según las posiciones sorteadas)
                (inserción y mixta se prueban sin tocar genetico.py; si ganan, se agregan a la aplicación)

Referencia: «promedio» = el genético con inversión sobre el promedio de ida y vuelta (la opción C
del experimento anterior, la mejor en sectores grandes). No es solo-calles con sentido: sirve para
saber si alguna mutación alcanza su calidad respetando los sentidos.

Todas las rutas se miden igual: por calles, con sentido, en el sentido de recorrido más corto.
Mismos parámetros que la aplicación (100 × 1000, torneo 5, OX 0.9, mutación 0.5, élite 1).
NO modifica la base: lee la matriz guardada (python crear_matriz_calles.py) y las particiones.

Uso, desde la carpeta backend con (.venv):
    python experimento_mutacion.py --n 1 2 3 4 5 --semillas 10      (≈ 15–20 min)
    python experimento_mutacion.py --n 3 --semillas 3               (prueba rápida)
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
from app.servicios import matriz_calles as M
from app.servicios import particion as P

CARPETA = Path("resultados") / "experimento"
VARIANTES = ("promedio", "inversion", "intercambio", "insercion", "mixta")
NOMBRE = {"promedio": "Promedio+inv (ref.)", "inversion": "Inversión", "intercambio": "Intercambio",
          "insercion": "Inserción", "mixta": "Mixta"}


def insertar(p: list, a: int, b: int) -> list:
    """Saca el hotspot de la posición a y lo mete en la posición b (a < b). No voltea nada."""
    r = list(p)
    r.insert(b, r.pop(a))
    return r


def mixta(p: list, a: int, b: int) -> list:
    """Inversión o inserción según las posiciones sorteadas (determinista con la misma semilla)."""
    return AG.invertir(p, a, b) if (a + b) % 2 == 0 else insertar(p, a, b)


def usar_como_swap(funcion):
    """Pone `funcion` donde el genético busca la mutación «swap». Sirve con el genetico.py anterior
    (usa AG.intercambiar) y con el de la versión solo-calles (usa AG.OPERADOR_MUTACION).
    Devuelve lo necesario para restaurar."""
    tabla = getattr(AG, "OPERADOR_MUTACION", None)
    antes = (AG.intercambiar, None if tabla is None else tabla["swap"])
    AG.intercambiar = funcion
    if tabla is not None:
        tabla["swap"] = funcion
    return antes


def restaurar(antes):
    AG.intercambiar = antes[0]
    if antes[1] is not None:
        AG.OPERADOR_MUTACION["swap"] = antes[1]


def correr(nodos: list[int], D: np.ndarray, semilla: int, mutacion: str):
    """El genético de la aplicación con la mutación pedida (inserción y mixta, sin tocar genetico.py)."""
    p = AG.Parametros(semilla=semilla, op_mutacion="inversion" if mutacion in ("inversion", "promedio") else "swap")
    antes = usar_como_swap({"insercion": insertar, "mixta": mixta}.get(mutacion, AG.intercambiar))
    try:
        return AG.ejecutar_ag(nodos, D, p, registro=False)
    finally:
        restaurar(antes)


def leer_grafos(con, id_particion: int) -> list[dict]:
    filas = con.execute(text("""
        SELECT g.numero, n.id_hotspot
        FROM grafo g JOIN nodo_grafo n USING (id_grafo) JOIN hotspot h ON h.id_hotspot = n.id_hotspot
        WHERE g.id_particion = :p ORDER BY g.numero, h.etiqueta
    """), {"p": id_particion}).all()
    grafos: dict[int, list] = {}
    for numero, h in filas:
        grafos.setdefault(numero, []).append(int(h))
    return [{"numero": k, "hotspots": grafos[k]} for k in sorted(grafos)]


def comparar(Dc: np.ndarray, semillas: list[int]) -> list[dict]:
    Ds = (Dc + Dc.T) / 2
    nodos = list(range(len(Dc)))
    filas = []
    for s in semillas:
        f = {"semilla": s}
        for v in VARIANTES:
            r = correr(nodos, Ds if v == "promedio" else Dc, s, v)
            f[f"{v}_m"] = M.mejor_sentido(r.ruta_optima, Dc)[0]
            f[f"{v}_gen"] = r.generacion_mejor
            f[f"{v}_s"] = r.duracion_s
        filas.append(f)
    return filas


def main():
    ap = argparse.ArgumentParser(description="Mutación por inversión, intercambio e inserción con calles de un sentido.")
    ap.add_argument("--n", type=int, nargs="+", default=[3], help="particiones a probar (1 a 5)")
    ap.add_argument("--semillas", type=int, default=10, help="corridas por sector con semillas 1, 2, …")
    a = ap.parse_args()
    semillas = list(range(1, a.semillas + 1))

    with engine.connect() as con:
        id_analisis = P.analisis_vigente(con)
        m = M.obtener(con, id_analisis, pedir=False)
        if m is None:
            raise SystemExit("La matriz por calles de este análisis no está guardada: corre primero "
                             "python crear_matriz_calles.py (con internet).")
        particiones = {}
        for n in a.n:
            idp = P.particion_existente(con, id_analisis, n)
            if idp is None:
                raise SystemExit(f"No hay partición de {n} grafos del análisis {id_analisis}: "
                                 "créala con python exportar_grafos.py.")
            particiones[n] = (idp, leer_grafos(con, idp))
    print(f"Análisis vigente {id_analisis}: {len(m.ids)} hotspots · matriz por calles guardada ({m.proveedor})")
    print(f"Semillas por sector: {len(semillas)} · 100 × 1000, torneo 5, OX 0.9, mutación 0.5, élite 1, ruta cerrada")
    print("Todas optimizan con calles CON SENTIDO, salvo la referencia (promedio de ida y vuelta).")
    print("Todas se miden por calles con sentido. Diferencia = contra la referencia (negativo = más corta).\n")

    t0 = time.perf_counter()
    detalle, resumen, ya = [], [], {}
    cab = " │ ".join(f"{NOMBRE[v]:>19}" for v in VARIANTES)
    print(f"{'N':>2} {'sector':>6} {'nodos':>5} │ {cab}")
    for n, (idp, grafos) in particiones.items():
        tot = dict.fromkeys(VARIANTES, 0.0)
        for g in grafos:
            clave = tuple(sorted(g["hotspots"]))
            if clave not in ya:                        # el mismo sector aparece en varias particiones
                ya[clave] = comparar(m.submatrices(g["hotspots"])["calles"], semillas)
            filas = ya[clave]
            for f in filas:
                detalle.append({"analisis": id_analisis, "N": n, "sector": g["numero"],
                                "nodos": len(g["hotspots"]), **f})
            media = {v: st.mean(f[f"{v}_m"] for f in filas) for v in VARIANTES}
            for v in VARIANTES:
                tot[v] += media[v]
            ref = media["promedio"]
            celdas = [f"{media['promedio'] / 1000:8.2f} km{'':>8}"]
            celdas += [f"{media[v] / 1000:8.2f} km {round(100 * (media[v] / ref - 1), 1) + 0.0:+5.1f} %" for v in VARIANTES[1:]]
            print(f"{n:>2} {g['numero']:>6} {len(g['hotspots']):>5} │ " + " │ ".join(celdas))
            resumen.append({"N": n, "sector": g["numero"], "nodos": len(g["hotspots"]),
                            **{f"{v}_km": media[v] / 1000 for v in VARIANTES},
                            **{f"{v}_mejor_semilla_km": min(f[f"{v}_m"] for f in filas) / 1000 for v in VARIANTES}})
        ref = tot["promedio"]
        celdas = [f"{tot['promedio'] / 1000:8.2f} km{'':>8}"]
        celdas += [f"{tot[v] / 1000:8.2f} km {round(100 * (tot[v] / ref - 1), 1) + 0.0:+5.1f} %" for v in VARIANTES[1:]]
        print(f"{n:>2} {'total':>6} {'':>5} │ " + " │ ".join(celdas) + "\n")

    gana = {}
    for r in resumen:
        km = {v: r[f"{v}_km"] for v in VARIANTES[1:]}
        mejor = min(km, key=km.get)
        empate = sum(1 for v in km if km[v] <= km[mejor] * 1.001) > 1      # a menos de 0.1 %
        clave = "empate" if empate else mejor
        gana[clave] = gana.get(clave, 0) + 1
    print("Sectores donde cada mutación (solo-calles) fue la más corta: "
          + ", ".join(f"{NOMBRE[v]} {gana.get(v, 0)}" for v in VARIANTES[1:])
          + f", empate (< 0.1 %) {gana.get('empate', 0)}")

    CARPETA.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y-%m-%d_%H%M")
    with open(CARPETA / f"experimento_mutacion_{marca}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(detalle[0]))
        w.writeheader()
        w.writerows(detalle)
    (CARPETA / f"experimento_mutacion_{marca}.json").write_text(json.dumps(
        {"analisis": id_analisis, "semillas": semillas, "resumen": resumen}, indent=1), encoding="utf-8")
    print(f"Tiempo total {time.perf_counter() - t0:.0f} s · detalle en "
          f"{CARPETA}\\experimento_mutacion_{marca}.csv y .json")


if __name__ == "__main__":
    main()
