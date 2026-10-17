"""Corre el algoritmo genético sobre los grafos reales exportados, sin tocar la base.

Uso, desde la carpeta backend con (.venv):
    python probar_genetico.py              # partición de 3 grafos, valores acordados
    python probar_genetico.py --n 5
    python probar_genetico.py --n 1 --poblacion 50 --generaciones 2000

Lee resultados/grafos/particion_N<n>.json (lo escribe `python exportar_grafos.py`).
"""
import argparse
import json
from pathlib import Path

import numpy as np

from app.servicios import genetico as AG


def main():
    ap = argparse.ArgumentParser(description="Prueba el genético con los grafos reales.")
    ap.add_argument("--n", type=int, default=3, help="número de grafos de la partición (1 a 5)")
    ap.add_argument("--poblacion", type=int, default=100)
    ap.add_argument("--generaciones", type=int, default=1000)
    ap.add_argument("--semilla", type=int, default=42)
    a = ap.parse_args()

    archivo = Path("resultados") / "grafos" / f"particion_N{a.n}.json"
    if not archivo.exists():
        raise SystemExit(f"No encuentro {archivo}. Corre primero: python exportar_grafos.py")
    particion = json.loads(archivo.read_text(encoding="utf-8"))
    p = AG.Parametros(tam_poblacion=a.poblacion, n_generaciones=a.generaciones, semilla=a.semilla)
    try:
        p.validar()
    except AG.ParametrosInvalidos as e:
        raise SystemExit(f"Parámetros no válidos: {e}")

    print(f"Partición {particion['id_particion']} (análisis {particion['id_analisis']}), {a.n} grafos")
    print(f"Parámetros: {p.tam_poblacion} rutas × {p.n_generaciones} generaciones, torneo {p.tam_torneo}, "
          f"{p.op_cruce} {p.prob_cruce}, {p.op_mutacion} {p.prob_mutacion}, élite {p.n_elite}, semilla {p.semilla}\n")
    print(f"{'Grafo':>5}  {'nodos':>5}  {'inicial':>9}  {'final':>9}  {'mejora':>6}  {'gen. mejor':>10}  {'tiempo':>7}  {'filas':>8}")
    total_filas = 0
    for g in particion["grafos"]:
        ids, D = g["orden_ids"], np.array(g["distancias_m"])
        r = AG.ejecutar_ag(ids, D, p)
        filas = sum(len(gen.distancia) for gen in r.generaciones)
        total_filas += filas
        inicial = r.resumen[0]["mejor_fitness"]
        print(f"{g['numero']:>5}  {len(ids):>5}  {inicial / 1000:>7.2f} km  {r.mejor_distancia / 1000:>6.2f} km  "
              f"{100 * (1 - r.mejor_distancia / inicial):>5.1f}%  {r.generacion_mejor:>10}  {r.duracion_s:>6.2f}s  {filas:>8,}")
        info = {n["id_hotspot"]: n for n in g["nodos"]}
        ruta = AG.presentar_ruta(r.ruta_optima, AG.prioridad_hotspots(g["nodos"]))
        print(f"       ruta: {' → '.join(info[h]['codigo'] for h in ruta)} → {info[ruta[0]]['codigo']}\n")
    print(f"Filas que se guardarían en la tabla individuo: {total_filas:,}")


if __name__ == "__main__":
    main()