"""Ingesta de archivos de víctimas de la FGJ (vista Inicio).

Parte 1 · recibir el archivo: leerlo, validar columnas, armar la vista previa
          y registrarlo en carga_dataset con estado 'recibido'.
Parte 2 · (siguiente paso) limpiar, insertar los puntos y lanzar HDBSCAN.
"""
import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from app.basedatos import engine
from app.config import CARPETA_CARGAS
from app.servicios.limpieza import mascara_gam
from app.servicios.texto import encabezado

log = logging.getLogger("uvicorn.error")

FORMATOS = {".csv": "csv", ".xlsx": "xlsx", ".xls": "xls"}
# Las mismas que marca el frontend en la vista previa
OBLIGATORIAS = ["fecha_hecho", "hora_hecho", "delito", "alcaldia_hecho", "latitud", "longitud"]
FILAS_VISTA_PREVIA = 20


class ArchivoInvalido(Exception):
    """El archivo no se puede aceptar. La ruta responde 422."""


class CargaDuplicada(Exception):
    """El archivo ya se procesó o se está procesando. La ruta responde 409."""


@dataclass
class ArchivoLeido:
    datos: pd.DataFrame
    formato: str
    hoja: str | None


# ---------------------------------------------------------------- lectura
def detectar_formato(nombre: str) -> str:
    extension = Path(nombre).suffix.lower()
    if extension not in FORMATOS:
        raise ArchivoInvalido(
            f"Formato no aceptado ({extension or 'sin extensión'}). "
            "Sube un archivo .csv, .xlsx o .xls."
        )
    return FORMATOS[extension]


def _leer_csv(contenido: bytes) -> pd.DataFrame:
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            datos = pd.read_csv(io.BytesIO(contenido), encoding=codificacion, dtype=str)
        except UnicodeDecodeError:
            continue
        if datos.shape[1] == 1:  # una sola columna: probablemente el separador es ';'
            datos = pd.read_csv(io.BytesIO(contenido), encoding=codificacion, dtype=str, sep=";")
        return datos
    raise ArchivoInvalido("No se pudo leer el texto del archivo.")


def _leer_excel(contenido: bytes, motor: str) -> tuple[pd.DataFrame, str]:
    libro = pd.ExcelFile(io.BytesIO(contenido), engine=motor)
    hoja = libro.sheet_names[0]
    return libro.parse(hoja, dtype=str), hoja


def leer_archivo(contenido: bytes, nombre: str) -> ArchivoLeido:
    """Convierte los bytes del archivo en una tabla con encabezados normalizados."""
    formato = detectar_formato(nombre)
    if not contenido:
        raise ArchivoInvalido("El archivo está vacío.")
    try:
        if formato == "csv":
            datos, hoja = _leer_csv(contenido), None
        else:
            datos, hoja = _leer_excel(contenido, "openpyxl" if formato == "xlsx" else "xlrd")
    except ArchivoInvalido:
        raise
    except Exception as error:  # archivo dañado, con contraseña, mal formado…
        log.warning("No se pudo leer %s: %r", nombre, error)
        raise ArchivoInvalido(
            f"No se pudo leer el archivo como .{formato}. Revisa que no esté dañado."
        ) from error
    if datos.empty:
        raise ArchivoInvalido("El archivo no tiene filas de datos.")
    datos.columns = [encabezado(c) for c in datos.columns]
    return ArchivoLeido(datos, formato, hoja)


# ---------------------------------------------------- validación y resumen
def revisar_columnas(datos: pd.DataFrame) -> dict:
    todas = list(datos.columns)
    return {
        "todas": todas,
        "encontradas": todas,
        "faltantes": [c for c in OBLIGATORIAS if c not in todas],
    }




def resumir(datos: pd.DataFrame) -> dict:
    gam = mascara_gam(datos)
    if {"latitud", "longitud"} <= set(datos.columns):
        lat = pd.to_numeric(datos.loc[gam, "latitud"], errors="coerce")
        lon = pd.to_numeric(datos.loc[gam, "longitud"], errors="coerce")
        sin_coordenadas = int((lat.isna() | lon.isna()).sum())
    else:
        sin_coordenadas = int(gam.sum())
    return {"filas_gam": int(gam.sum()), "sin_coordenadas": sin_coordenadas}


def _valor_json(columna: str, valor):
    """Convierte un valor de la tabla en algo que JSON acepte."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    if columna in ("latitud", "longitud"):
        try:
            return float(valor)
        except ValueError:
            return valor
    return valor


def vista_previa(datos: pd.DataFrame) -> list[dict]:
    primeras = datos.head(FILAS_VISTA_PREVIA).to_dict(orient="records")
    return [{c: _valor_json(c, v) for c, v in fila.items()} for fila in primeras]


# ------------------------------------------------------------ base de datos
def huella_archivo(contenido: bytes) -> str:
    """SHA-256 de los bytes: 64 caracteres que cambian si cambia un solo byte."""
    return hashlib.sha256(contenido).hexdigest()


def _carga_existente(con, huella: str):
    fila = con.execute(
        text("SELECT id_carga, estado FROM carga_dataset WHERE hash_archivo = :h"),
        {"h": huella},
    ).first()
    if fila is not None and fila.estado in ("procesando", "completado"):
        raise CargaDuplicada(
            f"Este archivo ya se había cargado (carga {fila.id_carga}, estado «{fila.estado}»)."
        )
    return fila


def registrar_carga(con, *, nombre: str, huella: str, filas: int, formato: str) -> int:
    """Crea la fila de carga_dataset, o reutiliza la de un intento anterior."""
    existente = _carga_existente(con, huella)
    datos = {"nombre": nombre, "huella": huella, "filas": filas, "formato": formato}
    if existente is not None:  # estaba en 'recibido' o 'error': se reinicia
        con.execute(text("""
            UPDATE carga_dataset
               SET nombre_archivo = :nombre, filas_leidas = :filas, formato = :formato,
                   estado = 'recibido', etapa = NULL, avance = 0, mensaje_error = NULL,
                   filas_validas = NULL, puntos_gam_nuevos = NULL, puntos_duplicados = NULL,
                   fecha_carga = now()
             WHERE id_carga = :id
        """), {**datos, "id": existente.id_carga})
        return existente.id_carga
    return con.execute(text("""
        INSERT INTO carga_dataset (nombre_archivo, hash_archivo, filas_leidas, formato)
        VALUES (:nombre, :huella, :filas, :formato)
        RETURNING id_carga
    """), datos).scalar_one()


def ruta_archivo(id_carga: int, formato: str) -> Path:
    return CARPETA_CARGAS / f"carga_{id_carga}.{formato}"


# ----------------------------------------------------------- todo junto
def recibir_carga(contenido: bytes, nombre: str) -> dict:
    """POST /api/cargas: valida, registra y devuelve la vista previa."""
    detectar_formato(nombre)          # falla rápido si la extensión no sirve
    huella = huella_archivo(contenido)
    with engine.connect() as con:     # falla rápido si ya se procesó (409)
        _carga_existente(con, huella)

    leido = leer_archivo(contenido, nombre)
    filas = len(leido.datos)

    with engine.begin() as con:
        id_carga = registrar_carga(con, nombre=nombre, huella=huella,
                                   filas=filas, formato=leido.formato)
        ruta_archivo(id_carga, leido.formato).write_bytes(contenido)

    return {
        "id_carga": id_carga,
        "nombre_archivo": nombre,
        "formato": leido.formato,
        "hoja": leido.hoja,
        "filas_leidas": filas,
        "columnas": revisar_columnas(leido.datos),
        "vista_previa": vista_previa(leido.datos),
        "vista_previa_disponible": True,
        "resumen": resumir(leido.datos),
    }