"""Genera el análisis HDBSCAN con los puntos que ya están en la base y lo GUARDA (pieza 3.6).

Hace lo mismo que probar_clustering.py, pero además:
  * guarda el análisis, sus hotspots y la membresía de cada punto en la base;
  * lo deja como el análisis VIGENTE (el que mostrará la vista Analizar);
  * escribe una copia del JSON en resultados/analisis_<id>.json.

Uso, desde la carpeta backend con (.venv):
    python crear_analisis.py            -> crea el análisis (si los datos cambiaron)
    python crear_analisis.py --forzar   -> lo crea aunque el vigente ya use los mismos datos
"""
import json
import sys
from pathlib import Path

from sqlalchemy import text

from app.servicios import analisis as A
from app.servicios import clustering as C
from db import get_engine

CARPETA = Path("resultados")
engine = get_engine()
p = C.PARAMETROS

# ¿El análisis vigente ya usa todos los puntos con los mismos criterios? Entonces no se repite.
with engine.connect() as con:
    al_dia = A.esta_al_dia(con)
    n_actual = C.contar_puntos(con)
    vigente = A.analisis_vigente(con)
if al_dia and "--forzar" not in sys.argv:
    print(f"El análisis vigente ({vigente}) ya usa estos {n_actual:,} puntos "
          f"y los mismos parámetros. No se creó otro.\n"
          f"Si de verdad quieres repetirlo: python crear_analisis.py --forzar")
    sys.exit(0)

print(f"Analizando {n_actual:,} puntos con min_cluster_size {p.min_cluster_size} "
      f"y min_samples {p.min_samples}… (tarda ~1 minuto)")
id_analisis, r = A.nuevo_analisis(engine)

with engine.connect() as con:
    fila = con.execute(text("""
        SELECT a.id_analisis, a.id_analisis_previo, a.id_carga_origen, a.resultado_json,
               (SELECT count(*) FROM hotspot h WHERE h.id_analisis = a.id_analisis) AS hotspots,
               (SELECT count(*) FROM membresia_hotspot m WHERE m.id_analisis = a.id_analisis) AS membresia,
               (SELECT string_agg(id_carga::text, ', ' ORDER BY id_carga)
                  FROM analisis_carga c WHERE c.id_analisis = a.id_analisis) AS cargas
        FROM analisis_hdbscan a WHERE a.vigente
    """)).mappings().one()

CARPETA.mkdir(exist_ok=True)
archivo = CARPETA / f"analisis_{id_analisis}.json"
archivo.write_text(json.dumps(fila["resultado_json"], ensure_ascii=False, indent=1), encoding="utf-8")

print(f"""
Análisis guardado y vigente: {fila['id_analisis']}  (anterior: {fila['id_analisis_previo']})
  Hotspots:   {r.n_hotspots}  (filas en hotspot: {fila['hotspots']})
  Ruido:      {r.n_ruido:,} ({r.pct_ruido} %)
  Membresía:  {fila['membresia']:,} filas  (= puntos analizados: {r.n_puntos:,})
  Cargas:     {fila['cargas']}  ·  carga de origen: {fila['id_carga_origen']}
  HDBSCAN:    {r.duracion_s} s
  JSON:       {archivo}""")