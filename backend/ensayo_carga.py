"""Ensayo de carga: limpia, aplica A + P e inserta los puntos de una carga
dentro de una transacción que al final se DESHACE. Muestra las cifras reales
sin cambiar la base.

Uso, desde la carpeta backend:   python ensayo_carga.py 3
(el número es el id_carga; por defecto, 3)
"""
import sys
import time

from sqlalchemy import text

from app.basedatos import engine
from app.servicios import huella, ingesta, insercion, limpieza

id_carga = int(sys.argv[1]) if len(sys.argv) > 1 else 3

with engine.connect() as con:
    transaccion = con.begin()          # todo lo de abajo se deshace al final

    carga = con.execute(
        text("SELECT nombre_archivo, formato FROM carga_dataset WHERE id_carga = :c"),
        {"c": id_carga},
    ).one()
    print(f"Carga {id_carga}: {carga.nombre_archivo}")

    inicio = time.perf_counter()
    contenido = ingesta.ruta_archivo(id_carga, carga.formato).read_bytes()
    leido = ingesta.leer_archivo(contenido, carga.nombre_archivo)
    r = limpieza.limpiar(leido.datos, limpieza.catalogo_delitos(con))
    puntos, de_periodos_cargados, aplicada = huella.aplicar_calendario(
        r.puntos, huella.dias_cargados(con))
    huellas = huella.huellas(puntos)
    preparacion = time.perf_counter() - inicio

    print(f"  leídas {r.filas_leidas:,} · de GAM {r.filas_gam:,} · válidas {r.filas_validas:,}")
    print(f"  descartadas {r.descartadas}")
    print(f"  calendario aplicado: {aplicada} · de periodos ya cargados: {de_periodos_cargados:,}")
    print(f"  preparación: {preparacion:.1f} s")

    inicio = time.perf_counter()
    insertados = insercion.insertar_puntos(
        con, puntos, huellas, id_carga,
        al_avanzar=lambda f: print(f"  insertando… {f:.0%}"),
    )
    insercion_s = time.perf_counter() - inicio

    dentro, con_colonia = con.execute(text("""
        SELECT count(*) FILTER (WHERE dentro_gam), count(id_colonia)
          FROM punto_delictivo WHERE id_carga = :c
    """), {"c": id_carga}).one()

    print(f"  insertados {insertados:,} · duplicados {len(puntos) - insertados:,}")
    print(f"  dentro del polígono de GAM {dentro:,} · con colonia asignada {con_colonia:,}")
    print(f"  inserción: {insercion_s:.1f} s ({insertados / max(insercion_s, 0.001):,.0f} puntos/s)")

    transaccion.rollback()
    print("Ensayo terminado: todos los cambios se deshicieron.")