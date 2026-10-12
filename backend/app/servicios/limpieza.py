"""Limpieza de los registros de la FGJ antes de insertarlos (etapa 2, pieza 2.8).

Replica las reglas de PI_AnalisisPreviodeGAM/01_prep.ipynb y prepara cada fila
para la tabla punto_delictivo. No toca la base de datos: recibe una tabla y
devuelve otra, más un conteo de lo que se descartó y por qué.
"""
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy import text

from app.servicios.texto import normalizar

# Recuadro amplio alrededor de la CDMX. Lo que caiga fuera es un error de captura.
# La decisión fina (dentro o fuera de GAM) la toma el trigger con el polígono oficial.
LAT_MIN, LAT_MAX = 19.0, 19.7
LON_MIN, LON_MAX = -99.4, -98.9

# Unificación de textos (las mismas de 01_prep.ipynb)
REEMPLAZOS = {
    "calidad_juridica": {"VICTIMA Y DENUNCIANTE": "DENUNCIANTE Y VICTIMA"},
    "competencia": {
        "HECHOS NO DELICTIVOS": "HECHO NO DELICTIVO",
        "INCOMPETENCIAS": "INCOMPETENCIA",
    },
}

# Largo máximo de las columnas de texto en punto_delictivo (01_esquema.sql)
LARGOS = {"sexo": 15, "tipo_persona": 10, "calidad_juridica": 40,
          "competencia": 30, "colonia_texto": 150}


@dataclass
class ResultadoLimpieza:
    puntos: pd.DataFrame                    # filas listas para insertar
    filas_leidas: int
    filas_gam: int
    descartadas: dict = field(default_factory=dict)   # motivo -> cuántas
    edades_anuladas: int = 0
    delitos_desconocidos: dict = field(default_factory=dict)

    @property
    def filas_validas(self) -> int:
        return len(self.puntos)


# ------------------------------------------------------------ piezas sueltas
def mascara_gam(datos: pd.DataFrame) -> pd.Series:
    """True en las filas cuya alcaldía (del hecho o del catálogo) es Gustavo A. Madero."""
    mascara = pd.Series(False, index=datos.index)
    for columna in ("alcaldia_hecho", "alcaldia_catalogo"):
        if columna in datos.columns:
            valores = datos[columna].fillna("")
            # Se normaliza cada nombre distinto una sola vez (hay ~20, no 250 mil)
            normalizados = {v: normalizar(v) for v in valores.unique()}
            mascara |= valores.map(normalizados).str.contains("GUSTAVO A", regex=False)
    return mascara


def a_fecha(serie: pd.Series) -> pd.Series:
    """Texto -> fecha. Acepta '2024-01-31', '2024-01-31 00:00:00' y '31/01/2024'."""
    fechas = pd.to_datetime(serie, format="ISO8601", errors="coerce")
    faltan = fechas.isna() & serie.notna()
    if faltan.any():
        fechas[faltan] = pd.to_datetime(serie[faltan], format="mixed",
                                        dayfirst=True, errors="coerce")
    return fechas.dt.date


def a_hora(serie: pd.Series) -> pd.Series:
    """Texto -> hora. Acepta '06:00:00' y '6:00'."""
    horas = pd.to_datetime(serie, format="%H:%M:%S", errors="coerce")
    faltan = horas.isna() & serie.notna()
    if faltan.any():
        horas[faltan] = pd.to_datetime(serie[faltan], format="%H:%M", errors="coerce")
    return horas.dt.time


def catalogo_delitos(con) -> dict[str, int]:
    """{'VIOLENCIA FAMILIAR': 87, …} con los nombres normalizados."""
    filas = con.execute(text("SELECT id_delito, nombre FROM cat_delito")).all()
    return {normalizar(f.nombre): f.id_delito for f in filas}


def _texto(datos: pd.DataFrame, columna: str) -> pd.Series:
    """La columna sin espacios sobrantes; vacía o inexistente -> NA."""
    if columna not in datos.columns:
        return pd.Series(pd.NA, index=datos.index, dtype="object")
    valores = datos[columna].astype("object").str.strip()
    return valores.where(valores.notna() & (valores != ""), pd.NA)


# ------------------------------------------------------------ todo junto
def limpiar(datos: pd.DataFrame, catalogo: dict[str, int]) -> ResultadoLimpieza:
    """Aplica las reglas de limpieza a un archivo ya leído (encabezados normalizados)."""
    filas_leidas = len(datos)
    d = datos[mascara_gam(datos)].copy()
    filas_gam = len(d)
    descartadas = {}

    def descartar(mascara: pd.Series, motivo: str):
        nonlocal d
        descartadas[motivo] = int(mascara.sum())
        d = d[~mascara]

    # 1 · Coordenadas: obligatorias y dentro del recuadro de la CDMX
    d["latitud"] = pd.to_numeric(d["latitud"], errors="coerce")
    d["longitud"] = pd.to_numeric(d["longitud"], errors="coerce")
    descartar(d["latitud"].isna() | d["longitud"].isna(), "sin_coordenadas")
    fuera = ~(d["latitud"].between(LAT_MIN, LAT_MAX) & d["longitud"].between(LON_MIN, LON_MAX))
    descartar(fuera, "coordenadas_fuera_de_cdmx")

    # 2 · Fechas y hora
    d["fecha_hecho"] = a_fecha(_texto(d, "fecha_hecho"))
    descartar(d["fecha_hecho"].isna(), "sin_fecha_hecho")
    d["fecha_inicio"] = a_fecha(_texto(d, "fecha_inicio"))
    d["hora_hecho"] = a_hora(_texto(d, "hora_hecho"))

    # 3 · Delito -> id_delito (por nombre normalizado)
    delito = _texto(d, "delito").fillna("")
    normalizados = {v: normalizar(v) for v in delito.unique()}
    d["id_delito"] = delito.map(normalizados).map(catalogo)
    desconocido = d["id_delito"].isna()
    delitos_desconocidos = dict(Counter(delito[desconocido]).most_common(10))
    descartar(desconocido, "delito_desconocido")
    d["id_delito"] = d["id_delito"].astype(int)

    # 4 · Edad: fuera de 0–100 -> vacía (la fila se conserva)
    edad = pd.to_numeric(_texto(d, "edad"), errors="coerce").round()
    imposible = edad.notna() & ~edad.between(0, 100)
    edades_anuladas = int(imposible.sum())
    d["edad"] = edad.mask(imposible).astype("Int64")

    # 5 · Textos: sin espacios sobrantes, unificados y con el largo de la base
    for columna in ("sexo", "tipo_persona", "calidad_juridica", "competencia"):
        d[columna] = _texto(d, columna)
    for columna, cambios in REEMPLAZOS.items():
        d[columna] = d[columna].replace(cambios)
    d["colonia_texto"] = _texto(d, "colonia_catalogo").fillna(_texto(d, "colonia_hecho"))
    for columna, largo in LARGOS.items():
        d[columna] = d[columna].str.slice(0, largo)

    return ResultadoLimpieza(
        puntos=d,
        filas_leidas=filas_leidas,
        filas_gam=filas_gam,
        descartadas=descartadas,
        edades_anuladas=edades_anuladas,
        delitos_desconocidos=delitos_desconocidos,
    )