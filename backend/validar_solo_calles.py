"""Validación de la versión «solo calles con sentido» (cifras oficiales para la tesis, 1 nov 2026).

Para cada partición N = 1…5 del análisis vigente y cada sector, corre la MISMA receta de la aplicación
(genetico.ejecutar_ag con los parámetros por omisión: 100 × 1000, torneo 5, OX 0.9, mixta 0.5,
élite 1, ruta cerrada + agentes.pulir_ruta) con 10 semillas, y como comparación el método original:
optimizar en línea recta con inversión y medir esa ruta por calles (sin pulido).

Reporta:
  1. por sector: km por calles (genético, pulida), ahorro del pulido, km en línea recta de la misma ruta,
     mejora sobre el método original, variación entre semillas y tiempo por agente;
  2. por partición: total de km por calles (promedio de las 10 semillas ± desviación);
  3. equilibrio entre agentes (brecha G4): hotspots, carga delictiva (n_puntos × índice de gravedad) y km
     por agente, con su coeficiente de variación y la razón mayor / menor.

NO modifica la base (no crea agentes): solo lee hotspots, particiones y la matriz por calles guardada.
Escribe resultados/validacion/validacion_solo_calles_<fecha>.csv, .json y .md (tablas listas para la tesis).

Uso, desde la carpeta backend con (.venv):
    python validar_solo_calles.py                    (N = 1…5, semillas 1…10, ≈ 8–12 min)
    python validar_solo_calles.py --n 3 --semillas 2 (prueba rápida)
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
from app.servicios import agentes as S
from app.servicios import genetico as AG
from app.servicios import matriz_calles as M
from app.servicios import particion as P

CARPETA = Path("resultados") / "validacion"


def leer_sectores(con, id_particion: int) -> list[dict]:
    filas = con.execute(text("""
        SELECT g.numero, h.id_hotspot, h.n_puntos, coalesce(h.indice_gravedad, 0) AS gravedad
        FROM grafo g JOIN nodo_grafo n USING (id_grafo) JOIN hotspot h ON h.id_hotspot = n.id_hotspot
        WHERE g.id_particion = :p ORDER BY g.numero, h.etiqueta
    """), {"p": id_particion}).mappings().all()
    sectores: dict[int, dict] = {}
    for f in filas:
        s = sectores.setdefault(f["numero"], {"numero": f["numero"], "hotspots": [], "carga": 0.0})
        s["hotspots"].append(int(f["id_hotspot"]))
        s["carga"] += float(f["n_puntos"]) * float(f["gravedad"])
    return [sectores[k] for k in sorted(sectores)]


def correr_sector(ids: list[int], m: M.Matriz, semillas: list[int]) -> list[dict]:
    mats = m.submatrices(ids)
    calles, recta = mats["calles"], mats["recta"]
    pos = list(range(len(ids)))
    filas = []
    for s in semillas:
        t0 = time.perf_counter()
        r = AG.ejecutar_ag(ids, calles, AG.Parametros(semilla=s), registro=False)        # receta de la aplicación
        e = S.pulir_ruta(ids, r, calles, recta, True)
        seg = time.perf_counter() - t0
        o = AG.ejecutar_ag(pos, recta, AG.Parametros(semilla=s, op_mutacion="inversion"), registro=False)
        original = min(AG.largo(o.ruta_optima, calles), AG.largo(o.ruta_optima[::-1], calles))  # medida por calles
        filas.append({
            "semilla": s,
            "genetico_m": r.mejor_distancia,
            "pulida_m": e["mejor_distancia"],
            "recta_misma_ruta_m": e["distancia_recta_m"],
            "movimientos_pulido": len(e["pulido"]["movimientos"]),
            "invertida": e["pulido"]["invertida"],
            "generacion_mejor": r.generacion_mejor,
            "segundos": round(seg, 2),
            "original_por_calles_m": round(original, 1),
        })
    return filas


def cv(xs: list[float]) -> float:
    return st.pstdev(xs) / st.mean(xs) if len(xs) > 1 and st.mean(xs) else 0.0


def km(m: float) -> str:
    return f"{m / 1000:.2f}"


def main():
    ap = argparse.ArgumentParser(description="Cifras oficiales de la versión solo-calles.")
    ap.add_argument("--n", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    ap.add_argument("--semillas", type=int, default=10)
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
            particiones[n] = (idp, leer_sectores(con, idp))
    print(f"Análisis {id_analisis}: {len(m.ids)} hotspots · {len(semillas)} semillas · receta de la aplicación "
          f"(100 × 1000, torneo 5, OX 0.9, mixta 0.5, élite 1, pulido final)")
    print("Original = optimizar en línea recta con inversión y medir esa ruta por calles (sin pulido).\n")

    t0 = time.perf_counter()
    cache, detalle, sectores_res, particiones_res = {}, [], [], []
    for n, (idp, sectores) in particiones.items():
        print(f"N = {n} (partición {idp})")
        print(f"  {'sector':>6} {'nodos':>5} │ {'genético':>9} {'pulida':>9} {'pulido':>7} │ {'recta*':>8} │ "
              f"{'original':>9} {'mejora':>7} │ {'variación':>9} {'s/agente':>8}")
        por_semilla = {s: 0.0 for s in semillas}
        por_semilla_orig = {s: 0.0 for s in semillas}
        medias = []
        for sec in sectores:
            clave = tuple(sorted(sec["hotspots"]))
            if clave not in cache:
                cache[clave] = correr_sector(sec["hotspots"], m, semillas)
            filas = cache[clave]
            for f in filas:
                por_semilla[f["semilla"]] += f["pulida_m"]
                por_semilla_orig[f["semilla"]] += f["original_por_calles_m"]
                detalle.append({"analisis": id_analisis, "N": n, "particion": idp, "sector": sec["numero"],
                                "nodos": len(sec["hotspots"]), **f})
            g = st.mean(f["genetico_m"] for f in filas)
            p = st.mean(f["pulida_m"] for f in filas)
            rc = st.mean(f["recta_misma_ruta_m"] for f in filas)
            o = st.mean(f["original_por_calles_m"] for f in filas)
            seg = st.mean(f["segundos"] for f in filas)
            var = cv([f["pulida_m"] for f in filas])
            medias.append({"sector": sec["numero"], "nodos": len(sec["hotspots"]), "carga": sec["carga"], "km": p})
            res = {"N": n, "sector": sec["numero"], "nodos": len(sec["hotspots"]), "carga": round(sec["carga"], 1),
                   "genetico_km": g / 1000, "pulida_km": p / 1000, "ahorro_pulido_pct": 100 * (1 - p / g),
                   "recta_misma_ruta_km": rc / 1000, "rodeo": p / rc if rc else None, "original_km": o / 1000,
                   "mejora_sobre_original_pct": 100 * (1 - p / o), "cv_semillas_pct": 100 * var,
                   "min_km": min(f["pulida_m"] for f in filas) / 1000, "max_km": max(f["pulida_m"] for f in filas) / 1000,
                   "segundos_por_agente": seg}
            sectores_res.append(res)
            print(f"  {sec['numero']:>6} {len(sec['hotspots']):>5} │ {km(g):>9} {km(p):>9} {res['ahorro_pulido_pct']:>6.1f}% │"
                  f" {km(rc):>8} │ {km(o):>9} {res['mejora_sobre_original_pct']:>6.1f}% │ {100 * var:>8.1f}% {seg:>8.1f}")
        tot = list(por_semilla.values())
        tot_o = list(por_semilla_orig.values())
        n_ag = len(medias)
        bal = {
            "cv_hotspots_pct": 100 * cv([x["nodos"] for x in medias]),
            "cv_carga_pct": 100 * cv([x["carga"] for x in medias]),
            "cv_km_pct": 100 * cv([x["km"] for x in medias]),
            "razon_km_mayor_menor": max(x["km"] for x in medias) / min(x["km"] for x in medias) if n_ag > 1 else 1.0,
            "carga_pct_por_agente": [round(100 * x["carga"] / sum(y["carga"] for y in medias), 1) for x in medias],
        }
        pres = {"N": n, "particion": idp, "agentes": n_ag, "total_km": st.mean(tot) / 1000,
                "total_desv_km": st.pstdev(tot) / 1000, "original_total_km": st.mean(tot_o) / 1000,
                "mejora_sobre_original_pct": 100 * (1 - st.mean(tot) / st.mean(tot_o)),
                "km_por_agente_promedio": st.mean(tot) / 1000 / n_ag, **bal}
        particiones_res.append(pres)
        print(f"  {'total':>6} {'':>5} │ {'':>9} {km(st.mean(tot)):>9} {'':>7} │ {'':>8} │ {km(st.mean(tot_o)):>9} "
              f"{pres['mejora_sobre_original_pct']:>6.1f}% │ ± {st.pstdev(tot) / 1000:.2f} km entre semillas")
        if n_ag > 1:
            print(f"  equilibrio: hotspots CV {bal['cv_hotspots_pct']:.0f} % · carga CV {bal['cv_carga_pct']:.0f} % "
                  f"(reparto {' / '.join(f'{c:.0f}' for c in bal['carga_pct_por_agente'])} %) · km CV "
                  f"{bal['cv_km_pct']:.0f} % · el agente más largo recorre {bal['razon_km_mayor_menor']:.1f}× el más corto")
        print()

    print("* recta = la MISMA ruta medida en línea recta (comparación). Variación = coeficiente de variación entre semillas.")
    CARPETA.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y-%m-%d_%H%M")
    base = CARPETA / f"validacion_solo_calles_{marca}"
    with open(base.with_suffix(".csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(detalle[0]))
        w.writeheader()
        w.writerows(detalle)
    base.with_suffix(".json").write_text(json.dumps({
        "analisis": id_analisis, "semillas": semillas, "hotspots": len(m.ids),
        "parametros": {"tam_poblacion": 100, "n_generaciones": 1000, "tam_torneo": 5, "prob_cruce": 0.9,
                       "prob_mutacion": 0.5, "op_cruce": "OX", "op_mutacion": "mixta", "n_elite": 1, "pulido": True},
        "sectores": sectores_res, "particiones": particiones_res}, indent=1, ensure_ascii=False), encoding="utf-8")
    md = [f"# Validación solo-calles · análisis {id_analisis} · {len(semillas)} semillas · {marca}", "",
          "| N | Agentes | Total por calles (km) | ± entre semillas | Original por calles (km) | Mejora | km por agente | CV km | Mayor/menor |",
          "|---|---|---|---|---|---|---|---|---|"]
    for p in particiones_res:
        md.append(f"| {p['N']} | {p['agentes']} | {p['total_km']:.2f} | {p['total_desv_km']:.2f} | {p['original_total_km']:.2f} | "
                  f"{p['mejora_sobre_original_pct']:+.1f} % | {p['km_por_agente_promedio']:.2f} | {p['cv_km_pct']:.0f} % | "
                  f"{p['razon_km_mayor_menor']:.1f}× |")
    md += ["", "| N | Sector | Hotspots | Genético (km) | Pulida (km) | Pulido | Recta, misma ruta (km) | Rodeo | Original (km) | Mejora | CV semillas | s/agente |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in sectores_res:
        md.append(f"| {s['N']} | {s['sector']} | {s['nodos']} | {s['genetico_km']:.2f} | {s['pulida_km']:.2f} | "
                  f"{('−' if s['ahorro_pulido_pct'] >= 0.05 else '')}{s['ahorro_pulido_pct']:.1f} % | {s['recta_misma_ruta_km']:.2f} | {s['rodeo']:.2f} | {s['original_km']:.2f} | "
                  f"{s['mejora_sobre_original_pct']:+.1f} % | {s['cv_semillas_pct']:.1f} % | {s['segundos_por_agente']:.1f} |")
    base.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Tiempo total {time.perf_counter() - t0:.0f} s · resultados en {base}.csv, .json y .md")


if __name__ == "__main__":
    main()