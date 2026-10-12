"""Regla de duplicados A + P (etapa 2, pieza 2.9).

A · Huella de registro: SHA-256 de las 22 columnas de la FGJ, normalizadas,
    más el número de aparición de esa fila dentro del archivo (#1, #2…).
P · Calendario: las filas cuyo día de fecha_inicio ya tiene puntos cargados
    no se vuelven a insertar.

Ver claude/DECISIONES_BACKEND.md para la justificación.
"""
import hashlib

import pandas as pd
from sqlalchemy import text

from app.servicios.limpieza import a_hora
from app.servicios.texto import normalizar

# Las 22 columnas de los archivos de la FGJ, siempre en este orden
COLUMNAS_HUELLA = [
    "anio_inicio", "mes_inicio", "fecha_inicio", "hora_inicio",
    "anio_hecho", "mes_hecho", "fecha_hecho", "hora_hecho",
    "delito", "categoria_delito", "sexo", "edad", "tipo_persona",
    "calidad_juridica", "competencia", "colonia_hecho", "colonia_catalogo",
    "alcaldia_hecho", "alcaldia_catalogo", "municipio_hecho", "latitud", "longitud",
]
FECHAS = {"fecha_inicio", "fecha_hecho"}
HORAS = {"hora_inicio", "hora_hecho"}
ENTEROS = {"anio_inicio", "anio_hecho", "edad"}
COORDENADAS = {"latitud", "longitud"}


def _vacia(valor) -> bool:
    return valor is None or (not isinstance(valor, str) and pd.isna(valor))


def columna_normalizada(puntos: pd.DataFrame, columna: str) -> pd.Series:
    """Cada valor convertido a un texto que no depende del formato del archivo."""
    if columna not in puntos.columns:
        return pd.Series("", index=puntos.index)
    valores = puntos[columna]

    if columna in COORDENADAS:                       # 19.51020000001 -> '19.510200'
        return valores.map(lambda v: "" if _vacia(v) else f"{float(v):.6f}")
    if columna in FECHAS:                            # date(2024, 1, 31) -> '2024-01-31'
        return valores.map(lambda v: "" if _vacia(v) else v.isoformat())
    if columna in HORAS:                             # '6:00' -> '06:00:00'
        if columna == "hora_inicio":                 # (hora_hecho ya viene convertida)
            valores = a_hora(valores)
        return valores.map(lambda v: "" if _vacia(v) else v.strftime("%H:%M:%S"))
    if columna in ENTEROS:                           # '2021.0' -> '2021'
        numeros = pd.to_numeric(valores, errors="coerce").round().astype("Int64")
        return numeros.map(lambda v: "" if _vacia(v) else str(v))

    texto = valores.astype("object").fillna("")      # ' Gustavo A.  Madero' -> 'GUSTAVO A. MADERO'
    normalizados = {v: normalizar(v) for v in texto.unique()}
    return texto.map(normalizados)


def huellas(puntos: pd.DataFrame) -> pd.Series:
    """Una huella SHA-256 (64 caracteres) por fila. Dos filas idénticas reciben #1 y #2."""
    columnas = [columna_normalizada(puntos, c).tolist() for c in COLUMNAS_HUELLA]
    filas = ["|".join(valores) for valores in zip(*columnas)]   # funciona aunque no haya filas
    contenido = pd.Series(filas, index=puntos.index, dtype=object)

    aparicion = contenido.groupby(contenido).cumcount() + 1   # 1, 2, 3… por cada contenido
    resultado = [hashlib.sha256(f"{texto}#{n}".encode("utf-8")).hexdigest()
                 for texto, n in zip(filas, aparicion)]
    return pd.Series(resultado, index=puntos.index, dtype=object)


# ------------------------------------------------------------- regla P
def dias_cargados(con) -> set:
    """Los días de fecha_inicio que ya tienen puntos en la base."""
    filas = con.execute(text(
        "SELECT DISTINCT fecha_inicio FROM punto_delictivo WHERE fecha_inicio IS NOT NULL"
    )).scalars()
    return set(filas)


def aplicar_calendario(puntos: pd.DataFrame, dias: set) -> tuple[pd.DataFrame, int, bool]:
    """Quita las filas cuyo día ya está cargado.

    Devuelve (filas que siguen, cuántas se quitaron, si la regla se pudo aplicar).
    Las filas sin fecha_inicio se conservan: para ellas solo cuenta la huella.
    """
    if "fecha_inicio" not in puntos.columns or puntos["fecha_inicio"].isna().all():
        return puntos, 0, False                    # el archivo no trae fecha_inicio
    ya_cargado = puntos["fecha_inicio"].isin(dias)
    return puntos[~ya_cargado], int(ya_cargado.sum()), True