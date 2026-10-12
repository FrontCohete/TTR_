"""Inserción en la base REAL, dentro de una transacción que al final se deshace.

Igual que verificar_base.py: la base queda exactamente como estaba.
"""
import pytest
from sqlalchemy import text

from app.basedatos import engine
from app.servicios.huella import huellas
from app.servicios.insercion import insertar_puntos
from app.servicios.limpieza import catalogo_delitos, limpiar
from pruebas.test_limpieza import tabla

COYOACAN = {"latitud": "19.3131", "longitud": "-99.1421"}   # dice GAM, pero cae en Coyoacán


@pytest.fixture
def con():
    """Una conexión con transacción abierta que se deshace al terminar la prueba."""
    with engine.connect() as conexion:
        transaccion = conexion.begin()
        yield conexion
        transaccion.rollback()


@pytest.fixture
def id_carga(con):
    """Una carga de prueba (también se deshace)."""
    return con.execute(text("""
        INSERT INTO carga_dataset (nombre_archivo, hash_archivo, filas_leidas)
        VALUES ('prueba.csv', repeat('f', 64), 3) RETURNING id_carga
    """)).scalar_one()


def preparar(con, *cambios):
    puntos = limpiar(tabla(*cambios), catalogo_delitos(con)).puntos
    return puntos, huellas(puntos)


def test_inserta_todas_las_filas_incluso_las_identicas(con, id_carga):
    puntos, h = preparar(con, {}, {}, COYOACAN)
    assert insertar_puntos(con, puntos, h, id_carga) == 3
    total = con.execute(text("SELECT count(*) FROM punto_delictivo WHERE id_carga = :c"),
                        {"c": id_carga}).scalar()
    assert total == 3


def test_volver_a_insertar_no_duplica(con, id_carga):
    puntos, h = preparar(con, {}, {})
    assert insertar_puntos(con, puntos, h, id_carga) == 2
    assert insertar_puntos(con, puntos, h, id_carga) == 0     # mismas huellas: se descartan


def test_el_trigger_decide_si_esta_dentro_de_gam(con, id_carga):
    puntos, h = preparar(con, {}, COYOACAN)
    insertar_puntos(con, puntos, h, id_carga)
    dentro = con.execute(text("""
        SELECT dentro_gam FROM punto_delictivo WHERE id_carga = :c ORDER BY latitud DESC
    """), {"c": id_carga}).scalars().all()
    assert dentro == [True, False]          # El Olivo sí; la de Coyoacán no


def test_los_vacios_llegan_como_null(con, id_carga):
    puntos, h = preparar(con, {"edad": None, "hora_hecho": None, "sexo": None})
    insertar_puntos(con, puntos, h, id_carga)
    fila = con.execute(text("SELECT edad, hora_hecho, sexo FROM punto_delictivo WHERE id_carga = :c"),
                       {"c": id_carga}).one()
    assert tuple(fila) == (None, None, None)


def test_informa_el_avance(con, id_carga):
    avances = []
    puntos, h = preparar(con, {}, {}, {})
    insertar_puntos(con, puntos, h, id_carga, al_avanzar=avances.append)
    assert avances[-1] == 1.0