"""Lectura, validación y vista previa de archivos (sin base de datos)."""
import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app
from app.servicios import ingesta

ENCABEZADO = "fecha_hecho,hora_hecho,delito,alcaldia_hecho,latitud,longitud,edad\n"
FILAS = (
    "2024-01-01,06:00:00,AMENAZAS,GUSTAVO A. MADERO,19.4944,-99.1162,33\n"
    "2024-01-01,12:25:00,FRAUDE,GUSTAVO A. MADERO,,,\n"
    "2024-01-02,08:10:00,FRAUDE,COYOACAN,19.3131,-99.1421,40\n"
)


def test_csv_con_comas():
    leido = ingesta.leer_archivo((ENCABEZADO + FILAS).encode("utf-8"), "datos.csv")
    assert leido.formato == "csv" and leido.hoja is None
    assert len(leido.datos) == 3
    assert list(leido.datos.columns)[:2] == ["fecha_hecho", "hora_hecho"]


def test_csv_latin1_con_punto_y_coma_y_encabezados_con_acentos():
    texto = "Fecha Hecho;Alcaldía Hecho;Latitud\n2024-01-01;GUSTAVO A. MADERO;19.49\n"
    leido = ingesta.leer_archivo(texto.encode("latin-1"), "DATOS.CSV")
    assert list(leido.datos.columns) == ["fecha_hecho", "alcaldia_hecho", "latitud"]


def test_xlsx():
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Victimas"
    hoja.append(["Fecha_Hecho", "Delito", "Alcaldia_Hecho"])
    hoja.append(["2024-01-01", "AMENAZAS", "GUSTAVO A. MADERO"])
    salida = io.BytesIO()
    libro.save(salida)
    leido = ingesta.leer_archivo(salida.getvalue(), "datos.xlsx")
    assert leido.formato == "xlsx" and leido.hoja == "Victimas"
    assert leido.datos.loc[0, "delito"] == "AMENAZAS"


@pytest.mark.parametrize("nombre, contenido, mensaje", [
    ("datos.txt", b"a,b\n1,2\n", "Formato no aceptado"),
    ("datos.csv", b"", "vacío"),
    ("datos.csv", b"fecha_hecho,delito\n", "no tiene filas"),
    ("datos.xlsx", b"esto no es un excel", "No se pudo leer"),
])
def test_archivos_invalidos(nombre, contenido, mensaje):
    with pytest.raises(ingesta.ArchivoInvalido, match=mensaje):
        ingesta.leer_archivo(contenido, nombre)


def test_columnas_faltantes():
    leido = ingesta.leer_archivo(b"fecha_hecho,delito\n2024-01-01,FRAUDE\n", "datos.csv")
    faltantes = ingesta.revisar_columnas(leido.datos)["faltantes"]
    assert faltantes == ["hora_hecho", "alcaldia_hecho", "latitud", "longitud"]


def test_resumen_de_gam():
    leido = ingesta.leer_archivo((ENCABEZADO + FILAS).encode(), "datos.csv")
    assert ingesta.resumir(leido.datos) == {"filas_gam": 2, "sin_coordenadas": 1}


def test_vista_previa_es_json_valido():
    leido = ingesta.leer_archivo((ENCABEZADO + FILAS * 10).encode(), "datos.csv")
    previa = ingesta.vista_previa(leido.datos)
    assert len(previa) == 20                       # nunca más de 20 filas
    assert previa[0]["latitud"] == 19.4944         # número, no texto
    assert previa[1]["latitud"] is None            # vacío -> null, no NaN
    assert previa[1]["edad"] is None


def test_endpoint_rechaza_formato_con_422():
    cliente = TestClient(app)
    r = cliente.post("/api/cargas", files={"archivo": ("notas.txt", b"hola", "text/plain")})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("Formato no aceptado (.txt)")


def test_endpoint_exige_el_campo_archivo():
    r = TestClient(app).post("/api/cargas")
    assert r.status_code == 422
    assert r.json() == {"detail": "Falta el campo «archivo»."}