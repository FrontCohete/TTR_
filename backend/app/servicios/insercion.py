"""Inserción masiva de puntos delictivos (etapa 2, pieza 2.10).

1. COPY: las filas limpias viajan de golpe a una tabla temporal.
2. INSERT … SELECT por lotes: de la temporal a punto_delictivo. En cada fila
   corre el trigger (dentro_gam y colonia) y ON CONFLICT descarta las huellas
   que ya existían. Entre lote y lote se informa el avance.

Todo ocurre en la transacción que recibe: si algo falla, no queda ningún punto.
"""
from collections.abc import Callable

import pandas as pd
from sqlalchemy import text

# Columnas de punto_delictivo que llenamos (id_carga y hash_registro aparte).
# geom y dentro_gam las calcula la base; id_colonia la asigna el trigger.
COLUMNAS = [
    "id_delito", "colonia_texto", "fecha_hecho", "hora_hecho", "fecha_inicio",
    "sexo", "edad", "tipo_persona", "calidad_juridica", "competencia",
    "latitud", "longitud",
]
TAMANO_LOTE = 2000

_CREAR_TEMPORAL = text("""
    CREATE TEMP TABLE tmp_puntos (
        n                 int,
        id_delito         int,
        colonia_texto     varchar(150),
        fecha_hecho       date,
        hora_hecho        time,
        fecha_inicio      date,
        sexo              varchar(15),
        edad              smallint,
        tipo_persona      varchar(10),
        calidad_juridica  varchar(40),
        competencia       varchar(30),
        latitud           double precision,
        longitud          double precision,
        hash_registro     char(64)
    ) ON COMMIT DROP
""")

_LISTA = ", ".join(COLUMNAS)
_INSERTAR_LOTE = text(f"""
    INSERT INTO punto_delictivo (id_carga, {_LISTA}, hash_registro)
    SELECT :id_carga, {_LISTA}, hash_registro
      FROM tmp_puntos
     WHERE n >= :desde AND n < :hasta
     ORDER BY n
    ON CONFLICT (hash_registro) DO NOTHING
""")


def _sin_vacios(valor):
    """pandas usa NA/NaT para «vacío»; la base necesita None (NULL)."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    return valor


def _filas(puntos: pd.DataFrame, huellas: pd.Series):
    """Genera cada fila como tupla de valores de Python, lista para COPY."""
    tabla = puntos[COLUMNAS].astype(object)
    for n, (fila, huella) in enumerate(zip(tabla.itertuples(index=False), huellas)):
        yield (n, *(_sin_vacios(v) for v in fila), huella)


def insertar_puntos(con, puntos: pd.DataFrame, huellas: pd.Series, id_carga: int,
                    al_avanzar: Callable[[float], None] | None = None) -> int:
    """Inserta los puntos y devuelve cuántos entraron (los demás eran duplicados)."""
    total = len(puntos)
    if total == 0:
        return 0

    # 1 · Tabla temporal + COPY (psycopg habla directo con PostgreSQL)
    con.execute(_CREAR_TEMPORAL)
    cursor = con.connection.driver_connection.cursor()
    columnas_tmp = "n, " + _LISTA + ", hash_registro"
    with cursor.copy(f"COPY tmp_puntos ({columnas_tmp}) FROM STDIN") as copia:
        for fila in _filas(puntos, huellas):
            copia.write_row(fila)

    # 2 · De la temporal a punto_delictivo, por lotes
    insertados = 0
    for desde in range(0, total, TAMANO_LOTE):
        hasta = min(desde + TAMANO_LOTE, total)
        resultado = con.execute(_INSERTAR_LOTE,
                                {"id_carga": id_carga, "desde": desde, "hasta": hasta})
        insertados += resultado.rowcount
        if al_avanzar:
            al_avanzar(hasta / total)

    con.execute(text("DROP TABLE tmp_puntos"))   # por si se inserta otra vez en la misma transacción
    return insertados