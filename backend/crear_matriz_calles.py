"""Pide (una sola vez) la matriz de distancias por calles del análisis vigente y la guarda (etapa 7).

Uso, desde la carpeta backend con (.venv) y con internet:
    python crear_matriz_calles.py               -> análisis vigente
    python crear_matriz_calles.py --analisis 13 -> otro análisis

Si ya estaba guardada, no consulta a OSRM: solo muestra el resumen. No es obligatorio correrlo:
al generar agentes la matriz se pide sola. Sirve para comprobar que OSRM responde y para dejarla
lista antes de una presentación sin internet.
"""
import sys

from sqlalchemy import text

from app.servicios import matriz_calles as M
from app.servicios import ruteo
from db import get_engine

engine = get_engine()
id_analisis = int(sys.argv[sys.argv.index("--analisis") + 1]) if "--analisis" in sys.argv else None

with engine.begin() as con:
    if id_analisis is None:
        id_analisis = con.execute(text("SELECT id_analisis FROM analisis_hdbscan WHERE vigente")).scalar()
        if id_analisis is None:
            raise SystemExit("No hay análisis vigente: corre primero python crear_analisis.py")
    print(f"Análisis {id_analisis}…")
    try:
        m = M.obtener(con, id_analisis)
    except M.SinHotspots as error:
        raise SystemExit(str(error))
    except ruteo.RuteoNoDisponible as error:
        raise SystemExit(f"OSRM no respondió: {error}\nRevisa tu conexión a internet e inténtalo de nuevo.")
    fila = con.execute(text("SELECT duracion_consulta_s, fecha FROM matriz_calles WHERE id_analisis = :a"),
                       {"a": id_analisis}).mappings().one()

r = M.rodeo(m)
n = len(m.ids)
print(f"""
Matriz por calles {n} × {n} del análisis {id_analisis}: {'PEDIDA A OSRM AHORA' if m.nueva else 'ya estaba guardada'}
  Proveedor:    {m.proveedor} · perfil {m.perfil}
  Consulta:     {fila['duracion_consulta_s']} s · guardada el {fila['fecha']:%d/%m/%Y %H:%M}
  Sin camino:   {m.sin_camino} pares (se penalizan con {M.PENALIZACION:g} × la línea recta)
  Rodeo:        calles / línea recta mediana {r.get('mediana')} (10 % ≤ {r.get('p10')}, 10 % ≥ {r.get('p90')}),
                variación {r.get('variacion_pct')} % en {r.get('pares'):,} pares
  Ida ≠ vuelta: diferencia mediana {r.get('asimetria_mediana_pct')} %
""")
