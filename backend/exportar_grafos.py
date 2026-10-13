"""Exporta a JSON los grafos de las particiones N = 1…5 del análisis vigente.

Sirve como insumo del chat «PruebasGen» (pruebas del algoritmo genético en consola):
cada grafo trae sus hotspots (nodos) y la matriz de distancias haversine en metros
leída de la tabla `arista`, es decir, exactamente lo que usará el genético.

Uso, desde la carpeta backend con (.venv):
    python exportar_grafos.py

Crea (o reutiliza) las particiones N = 1…5 y al final deja vigente la que ya lo era.
Archivos que escribe en resultados/grafos/:
    particion_N1.json … particion_N5.json   una partición por archivo
    grafos_todos.json                        las cinco juntas
"""
import json
from pathlib import Path

from sqlalchemy import text

from app.basedatos import engine
from app.servicios import particion as P

CARPETA = Path("resultados") / "grafos"


def hotspots_del_grafo(con, id_grafo: int) -> list[dict]:
    return [dict(h) for h in con.execute(text("""
        SELECT h.id_hotspot, h.etiqueta, h.codigo,
               round(h.lat_centroide::numeric, 6)::float8 AS lat,
               round(h.lon_centroide::numeric, 6)::float8 AS lon,
               h.n_puntos, h.indice_gravedad, h.radio_m, h.colonia, h.delito_predominante
        FROM nodo_grafo n JOIN hotspot h USING (id_hotspot)
        WHERE n.id_grafo = :g ORDER BY h.etiqueta
    """), {"g": id_grafo}).mappings()]


def matriz_del_grafo(con, id_grafo: int, ids: list[int]) -> list[list[float]]:
    """Matriz simétrica n × n en metros, en el orden de `ids` (diagonal = 0)."""
    pos = {h: i for i, h in enumerate(ids)}
    M = [[0.0] * len(ids) for _ in ids]
    for o, d, m in con.execute(text(
            "SELECT id_origen, id_destino, distancia_m FROM arista WHERE id_grafo = :g"), {"g": id_grafo}):
        M[pos[o]][pos[d]] = M[pos[d]][pos[o]] = float(m)
    return M


def exportar(con, id_particion: int) -> dict:
    base = P.respuesta(con, id_particion)
    grafos = []
    for g in base["grafos"]:
        nodos = hotspots_del_grafo(con, g["id_grafo"])
        ids = [h["id_hotspot"] for h in nodos]
        grafos.append({
            "id_grafo": g["id_grafo"], "numero": g["numero"], "color": g["color"],
            "n_nodos": len(nodos), "n_aristas": g["n_aristas"],
            "orden_ids": ids,                       # filas/columnas de la matriz
            "nodos": nodos,
            "distancias_m": matriz_del_grafo(con, g["id_grafo"], ids),
        })
    return {
        "id_particion": base["id_particion"], "id_analisis": base["id_analisis"],
        "n_grafos": base["n_grafos"], "modularidad": base["modularidad"],
        "resolucion": base["resolucion"],
        "distancia": "haversine entre medoides, radio 6,371,008.8 m",
        "grafos": grafos,
    }


def main():
    CARPETA.mkdir(parents=True, exist_ok=True)
    with engine.begin() as con:
        id_analisis = P.analisis_vigente(con)
        antes = con.execute(text(
            "SELECT id_particion FROM particion_louvain WHERE id_analisis = :a AND vigente"), {"a": id_analisis}).scalar()
        todas = {}
        print(f"Análisis vigente: {id_analisis}\n")
        print(f"{'N':>2}  {'partición':>9}  {'modularidad':>11}  {'resolución':>10}  nodos por grafo (norte → sur)")
        for n in range(1, 6):
            datos = P.nueva_particion(con, n)                  # crea o reutiliza
            exp = exportar(con, datos["id_particion"])
            todas[f"N{n}"] = exp
            (CARPETA / f"particion_N{n}.json").write_text(json.dumps(exp, ensure_ascii=False, indent=1), encoding="utf-8")
            tam = " / ".join(str(g["n_nodos"]) for g in exp["grafos"])
            res = f"{exp['resolucion']:.3f}" if exp["resolucion"] else "—"
            print(f"{n:>2}  {exp['id_particion']:>9}  {exp['modularidad']:>11.3f}  {res:>10}  {tam}")
        if antes is not None:                                   # deja vigente la que ya lo era
            P.marcar_vigente(con, id_analisis, antes)
    (CARPETA / "grafos_todos.json").write_text(json.dumps(todas, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nArchivos en {CARPETA}\\  (particion_N1.json … particion_N5.json y grafos_todos.json)")


if __name__ == "__main__":
    main()