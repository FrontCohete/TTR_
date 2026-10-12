"""Funciones para limpiar y comparar texto.

Es la misma lógica de normalizar() en cargar_catalogos.py, ahora en un solo
lugar para toda la API.
"""
import unicodedata


def sin_acentos(s) -> str:
    """'Álvaro Obregón' -> 'Alvaro Obregon'"""
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()


def normalizar(s) -> str:
    """'  Gustavo A.  Madero ' -> 'GUSTAVO A. MADERO'"""
    return " ".join(sin_acentos(s).upper().split())


def encabezado(s) -> str:
    """'Alcaldía Hecho' -> 'alcaldia_hecho'"""
    return "_".join(sin_acentos(s).strip().lower().split())