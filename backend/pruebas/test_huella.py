"""Regla de duplicados A + P (sin base de datos)."""
import datetime as dt

from app.servicios.huella import aplicar_calendario, huellas
from app.servicios.limpieza import limpiar
from pruebas.test_limpieza import CATALOGO, tabla


def huellas_de(*cambios: dict) -> list[str]:
    """Limpia unas filas de mentira y devuelve sus huellas."""
    return huellas(limpiar(tabla(*cambios), CATALOGO).puntos).tolist()


def test_cada_huella_mide_64_caracteres():
    (h,) = huellas_de({})
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def test_filas_identicas_en_un_archivo_reciben_huellas_distintas():
    h1, h2 = huellas_de({}, {})              # dos víctimas con los mismos datos
    assert h1 != h2                          # #1 y #2: entran las dos


def test_el_mismo_registro_en_otro_archivo_da_la_misma_huella():
    assert huellas_de({}, {}) == huellas_de({}, {})   # se reconocería como duplicado


def test_un_dato_distinto_cambia_la_huella():
    (a,) = huellas_de({})
    (b,) = huellas_de({"delito": "FRAUDE"})
    assert a != b


def test_la_huella_no_depende_del_formato_del_archivo():
    (csv,) = huellas_de({})
    (excel,) = huellas_de({
        "fecha_hecho": "2024-01-01 00:00:00",      # así llegan las fechas desde Excel
        "fecha_inicio": "02/01/2024",
        "hora_hecho": "6:00",
        "latitud": "19.51020000001",               # más decimales
        "alcaldia_hecho": "  gustavo a.  madero ",  # minúsculas y espacios
        "edad": "33.0",
    })
    assert csv == excel


def test_las_apariciones_se_cuentan_por_contenido():
    a1, b1, a2 = huellas_de({}, {"delito": "FRAUDE"}, {})
    assert len({a1, b1, a2}) == 3
    assert huellas_de({}, {}) == [a1, a2]          # el orden de los demás no importa


def test_calendario_quita_los_dias_ya_cargados():
    puntos = limpiar(tabla({"fecha_inicio": "2024-01-02"}, {"fecha_inicio": "2024-01-03"},
                           {"fecha_inicio": None}), CATALOGO).puntos
    siguen, quitadas, aplicada = aplicar_calendario(puntos, {dt.date(2024, 1, 2)})
    assert aplicada and quitadas == 1
    assert len(siguen) == 2                        # el día nuevo y la fila sin fecha_inicio


def test_calendario_sin_columna_fecha_inicio():
    puntos = limpiar(tabla({}).drop(columns=["fecha_inicio"]), CATALOGO).puntos
    siguen, quitadas, aplicada = aplicar_calendario(puntos, {dt.date(2024, 1, 2)})
    assert not aplicada and quitadas == 0 and len(siguen) == 1