"""Procesamiento de cargas, contra la base REAL y dentro de una transacción que se deshace."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import CARPETA_CARGAS
from app.main import app
from app.servicios import procesamiento as P
from pruebas.test_insercion import COYOACAN, con, id_carga  # noqa: F401  (fixtures compartidos)
from pruebas.test_limpieza import tabla


def nueva_carga(con, nombre: str, *cambios) -> int:
    """Crea una carga 'recibido' y deja su archivo .csv en la carpeta de cargas."""
    id_nueva = con.execute(text("""
        INSERT INTO carga_dataset (nombre_archivo, hash_archivo, filas_leidas, formato)
        VALUES (:n, :h, :f, 'csv') RETURNING id_carga
    """), {"n": nombre, "h": uuid.uuid4().hex * 2, "f": len(cambios)}).scalar_one()
    # fecha_inicio en 2099: así nunca choca con días reales ya cargados (regla P)
    filas = tabla(*({"fecha_inicio": "2099-01-02", **c} for c in cambios))
    filas.to_csv(CARPETA_CARGAS / f"carga_{id_nueva}.csv", index=False)
    return id_nueva


@pytest.fixture
def archivos():
    """Borra al final los .csv de prueba que se hayan creado."""
    creados = set(CARPETA_CARGAS.glob("carga_*.csv"))
    yield
    for archivo in set(CARPETA_CARGAS.glob("carga_*.csv")) - creados:
        archivo.unlink()


def estado_de(con, id_carga):
    return con.execute(text("SELECT estado FROM carga_dataset WHERE id_carga = :c"),
                       {"c": id_carga}).scalar()


# ------------------------------------------------------------------ iniciar
def test_iniciar_deja_la_carga_procesando(con, id_carga):
    P.iniciar(con, id_carga)
    assert estado_de(con, id_carga) == "procesando"


def test_no_se_puede_iniciar_dos_veces(con, id_carga):
    P.iniciar(con, id_carga)
    with pytest.raises(P.ConflictoCarga, match="ya se está procesando"):
        P.iniciar(con, id_carga)


def test_una_carga_a_la_vez(con, id_carga, archivos):
    P.iniciar(con, id_carga)
    otra = nueva_carga(con, "otra.csv", {})
    with pytest.raises(P.ConflictoCarga, match=f"Espera a que termine la carga {id_carga}"):
        P.iniciar(con, otra)


def test_carga_inexistente(con):
    with pytest.raises(P.CargaNoEncontrada):
        P.iniciar(con, 999_999_999)


# ----------------------------------------------------------------- ejecutar
def test_ejecutar_deja_la_carga_lista_para_hdbscan(con, archivos):
    id_c = nueva_carga(con, "a.csv", {}, {}, {"latitud": None}, COYOACAN)
    avisos = []
    resumen = P.ejecutar(con, id_c, lambda **c: avisos.append(c))

    assert resumen["insertados"] == 3                      # 2 idénticas + la de Coyoacán
    assert resumen["descartadas"]["sin_coordenadas"] == 1
    carga = P.obtener_carga(con, id_c)
    # ejecutar() deja la carga lista para HDBSCAN; 'completado' lo pone procesar() al final
    assert carga["etapa"] == "hdbscan" and carga["avance"] == 80
    assert carga["estado"] != "completado"

    assert carga["puntos_gam_nuevos"] == 3 and carga["puntos_duplicados"] == 0
    assert carga["resumen_limpieza"]["filas_validas"] == 3
    assert {"etapa": "insercion", "avance": 30} in avisos  # la barra cambió de etapa
    assert avisos[-1] == {"avance": 80}


def test_el_calendario_evita_cargar_dos_veces_los_mismos_dias(con, archivos):
    primera = nueva_carga(con, "a.csv", {}, {})
    P.ejecutar(con, primera, lambda **c: None)
    # Mismos días, aunque con un dato corregido: no debe entrar nada
    segunda = nueva_carga(con, "b.csv", {"delito": "FRAUDE"}, {})
    resumen = P.ejecutar(con, segunda, lambda **c: None)
    assert resumen["de_periodos_cargados"] == 2 and resumen["insertados"] == 0
    assert P.obtener_carga(con, segunda)["puntos_duplicados"] == 2


def test_faltan_columnas(con, archivos):
    id_c = nueva_carga(con, "a.csv", {})
    (CARPETA_CARGAS / f"carga_{id_c}.csv").write_text("fecha_hecho,delito\n2024-01-01,FRAUDE\n",
                                                      encoding="utf-8")
    with pytest.raises(P.ProcesamientoInvalido, match="Faltan columnas obligatorias"):
        P.ejecutar(con, id_c, lambda **c: None)


# ---------------------------------------------------------------- consultas
def test_el_historial_no_muestra_las_cargas_recibidas(con, id_carga):
    ids = [c["id_carga"] for c in P.listar_cargas(con)]
    assert id_carga not in ids                             # sigue en 'recibido'
    assert P.obtener_carga(con, id_carga)["id_analisis"] is None


# ---------------------------------------------------------------- endpoints
def test_endpoints_responden_en_espanol():
    cliente = TestClient(app)
    assert cliente.post("/api/cargas/999999999/procesar").json() == {
        "detail": "No existe la carga 999999999."}
    assert cliente.get("/api/cargas/abc").json() == {
        "detail": "«id_carga» debe ser un número entero."}
    historial = cliente.get("/api/cargas")
    assert historial.status_code == 200 and isinstance(historial.json(), list)