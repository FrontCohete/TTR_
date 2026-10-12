"""Reglas de limpieza (sin base de datos): cada prueba revisa una regla."""
import datetime as dt

import pandas as pd
import pytest

from app.servicios.limpieza import a_fecha, a_hora, limpiar

# Catálogo de mentira: nombre normalizado -> id_delito
CATALOGO = {"AMENAZAS": 1, "FRAUDE": 2, "USURPACION DE IDENTIDAD": 3}

BASE = {  # una víctima válida de GAM; cada prueba cambia lo que necesita
    "fecha_inicio": "2024-01-02", "fecha_hecho": "2024-01-01", "hora_hecho": "06:00:00",
    "delito": "AMENAZAS", "sexo": "Femenino", "edad": "33", "tipo_persona": "FISICA",
    "calidad_juridica": "VICTIMA", "competencia": "FUERO COMUN",
    "colonia_hecho": "EL OLIVO", "colonia_catalogo": "El Olivo",
    "alcaldia_hecho": "GUSTAVO A. MADERO", "alcaldia_catalogo": "Gustavo A. Madero",
    "latitud": "19.5102", "longitud": "-99.1213",
}


def tabla(*cambios: dict) -> pd.DataFrame:
    """Una fila por diccionario de cambios, todo como texto (igual que leer_archivo)."""
    return pd.DataFrame([{**BASE, **c} for c in cambios], dtype="str")


def test_fila_valida_queda_lista_para_la_base():
    r = limpiar(tabla({}), CATALOGO)
    assert r.filas_leidas == 1 and r.filas_gam == 1 and r.filas_validas == 1
    fila = r.puntos.iloc[0]
    assert fila["id_delito"] == 1
    assert fila["fecha_hecho"] == dt.date(2024, 1, 1)
    assert fila["hora_hecho"] == dt.time(6, 0)
    assert fila["latitud"] == 19.5102
    assert fila["edad"] == 33
    assert fila["colonia_texto"] == "El Olivo"


def test_solo_se_quedan_las_filas_de_gam():
    r = limpiar(tabla({}, {"alcaldia_hecho": "COYOACAN", "alcaldia_catalogo": "Coyoacán"}), CATALOGO)
    assert r.filas_leidas == 2 and r.filas_gam == 1


def test_gam_solo_por_alcaldia_catalogo():
    r = limpiar(tabla({"alcaldia_hecho": None}), CATALOGO)
    assert r.filas_gam == 1


@pytest.mark.parametrize("cambio, motivo", [
    ({"latitud": None}, "sin_coordenadas"),
    ({"longitud": "abc"}, "sin_coordenadas"),
    ({"latitud": "0", "longitud": "0"}, "coordenadas_fuera_de_cdmx"),
    ({"fecha_hecho": "no es fecha"}, "sin_fecha_hecho"),
    ({"delito": "DELITO INVENTADO"}, "delito_desconocido"),
])
def test_motivos_de_descarte(cambio, motivo):
    r = limpiar(tabla({}, cambio), CATALOGO)
    assert r.filas_validas == 1
    assert r.descartadas[motivo] == 1


def test_delitos_desconocidos_se_reportan():
    r = limpiar(tabla({"delito": "X"}, {"delito": "X"}, {"delito": "Y"}), CATALOGO)
    assert r.delitos_desconocidos == {"X": 2, "Y": 1}


def test_delito_con_acentos_coincide_con_el_catalogo():
    r = limpiar(tabla({"delito": "Usurpación de Identidad"}), CATALOGO)
    assert r.puntos.iloc[0]["id_delito"] == 3


def test_edad_imposible_se_vacia_pero_la_fila_se_conserva():
    r = limpiar(tabla({"edad": "150"}, {"edad": "-3"}, {"edad": None}), CATALOGO)
    assert r.filas_validas == 3
    assert r.edades_anuladas == 2
    assert r.puntos["edad"].isna().sum() == 3


def test_textos_se_unifican():
    r = limpiar(tabla({"calidad_juridica": " VICTIMA Y DENUNCIANTE ",
                       "competencia": "INCOMPETENCIAS"}), CATALOGO)
    fila = r.puntos.iloc[0]
    assert fila["calidad_juridica"] == "DENUNCIANTE Y VICTIMA"
    assert fila["competencia"] == "INCOMPETENCIA"


def test_textos_se_recortan_al_largo_de_la_base():
    r = limpiar(tabla({"sexo": "X" * 40}), CATALOGO)
    assert len(r.puntos.iloc[0]["sexo"]) == 15


def test_archivo_sin_columnas_opcionales():
    datos = tabla({}).drop(columns=["fecha_inicio", "colonia_hecho", "colonia_catalogo",
                                    "sexo", "tipo_persona", "alcaldia_catalogo"])
    r = limpiar(datos, CATALOGO)
    assert r.filas_validas == 1
    assert pd.isna(r.puntos.iloc[0]["colonia_texto"])


def test_formatos_de_fecha():
    s = pd.Series(["2024-01-31", "2024-01-31 00:00:00", "31/01/2024", "basura", None], dtype="str")
    assert a_fecha(s).tolist()[:3] == [dt.date(2024, 1, 31)] * 3
    assert a_fecha(s).isna().tolist()[3:] == [True, True]


def test_formatos_de_hora():
    s = pd.Series(["06:00:00", "6:05", "25:00"], dtype="str")
    horas = a_hora(s).tolist()
    assert horas[0] == dt.time(6, 0) and horas[1] == dt.time(6, 5)
    assert pd.isna(horas[2])