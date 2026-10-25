"""«Empezar de cero» (etapa 5.6), contra la base real.

TRUNCATE en PostgreSQL respeta las transacciones: todo corre dentro de la transacción de la
fixture `con`, que se deshace al final. La base queda exactamente como estaba (también los ids).
Los archivos se prueban en carpetas temporales (tmp_path), nunca en backend/cargas ni resultados.
Detén uvicorn mientras corren: TRUNCATE bloquea las tablas hasta que la prueba termina.
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.rutas import mantenimiento as R
from app.servicios import mantenimiento as S
from pruebas.test_insercion import con, id_carga  # noqa: F401  (fixtures que se deshacen)


@pytest.fixture
def activado(monkeypatch, tmp_path):
    monkeypatch.setenv("PERMITIR_REINICIO", "true")
    monkeypatch.setattr(S, "CARPETA_CARGAS", tmp_path / "cargas")        # nunca las carpetas reales
    monkeypatch.setattr(S, "CARPETA_RESULTADOS", tmp_path / "resultados")
    return tmp_path


@pytest.fixture
def libre(con):
    """Sin cargas procesándose ni agentes calculando (dentro de la transacción que se deshace)."""
    con.execute(text("UPDATE carga_dataset SET estado = 'error' WHERE estado = 'procesando'"))
    con.execute(text("UPDATE ejecucion_ag SET estado = 'error' WHERE estado IN ('pendiente', 'ejecutando')"))
    return con


def conteo(con, tabla):
    return con.execute(text(f"SELECT count(*) FROM {tabla}")).scalar()


# ------------------------------------------------------------------ servicio
def test_resumen_cuenta_lo_que_hay(con, id_carga, activado):
    r = S.resumen(con)
    assert r["permitido"] is True and r["confirmacion"] == "BORRAR"
    assert r["datos"]["cargas"] >= 1
    assert set(r["datos"]) == {"cargas", "puntos", "analisis", "hotspots", "particiones", "agentes", "simulaciones"}
    assert r["se_conservan"]["delitos"] > 0 and r["espacio_bytes"] > 0


def test_sin_la_variable_no_se_permite(con, monkeypatch):
    monkeypatch.delenv("PERMITIR_REINICIO", raising=False)
    assert S.resumen(con)["permitido"] is False
    with pytest.raises(S.NoPermitido):
        S.reiniciar(con, "BORRAR")


@pytest.mark.parametrize("palabra", ["", "borrar", "SI", "BORRA"])
def test_hay_que_escribir_borrar(con, activado, palabra):
    with pytest.raises(S.ConfirmacionInvalida):
        S.reiniciar(con, palabra)


def test_no_reinicia_si_hay_una_carga_procesandose(libre, id_carga, activado):
    libre.execute(text("UPDATE carga_dataset SET estado = 'procesando' WHERE id_carga = :c"), {"c": id_carga})
    assert "se está procesando" in S.resumen(libre)["ocupado"]
    with pytest.raises(S.Ocupado, match="se está procesando"):
        S.reiniciar(libre, "BORRAR")
    assert conteo(libre, "carga_dataset") >= 1                 # no se borró nada


def test_no_reinicia_si_hay_agentes_calculando(libre, activado):
    grafo = libre.execute(text("SELECT id_grafo FROM grafo LIMIT 1")).scalar()
    if grafo is None:
        pytest.skip("no hay grafos: genera una partición desde Analizar")
    libre.execute(text("""
        INSERT INTO ejecucion_ag (id_grafo, tam_poblacion, n_generaciones, tam_torneo, prob_cruce,
                                  prob_mutacion, op_cruce, op_mutacion, semilla, estado)
        VALUES (:g, 10, 5, 2, 0.9, 0.5, 'OX', 'inversion', 1, 'pendiente')
    """), {"g": grafo})
    with pytest.raises(S.Ocupado, match="agente"):
        S.reiniciar(libre, "BORRAR")


def test_reinicia_los_datos_y_conserva_los_catalogos(libre, id_carga, activado):
    catalogos = {t: conteo(libre, t) for t in S.CATALOGOS}
    antes = S.reiniciar(libre, "BORRAR")
    assert antes["cargas"] >= 1 and "espacio" in antes
    assert all(conteo(libre, t) == 0 for t in S.TABLAS_DE_DATOS)
    assert {t: conteo(libre, t) for t in S.CATALOGOS} == catalogos          # catálogos intactos
    nueva = libre.execute(text("""
        INSERT INTO carga_dataset (nombre_archivo, hash_archivo, filas_leidas)
        VALUES ('2024.xlsx', repeat('a', 64), 1) RETURNING id_carga
    """)).scalar_one()
    assert nueva == 1                                                        # los ids empiezan de nuevo
    assert S.resumen(libre)["datos"] == {k: (1 if k == "cargas" else 0) for k in antes if k != "espacio"}


def test_limpiar_archivos(tmp_path):
    cargas, resultados = tmp_path / "cargas", tmp_path / "resultados"
    (resultados / "grafos").mkdir(parents=True)
    cargas.mkdir()
    (cargas / "carga_3.xlsx").write_bytes(b"x")
    (cargas / "otro.txt").write_text("se queda")
    (resultados / "analisis_15.json").write_text("{}")
    (resultados / "grafos" / "particion_N3.json").write_text("{}")

    r = S.limpiar_archivos(cargas, resultados, ahora=datetime(2026, 10, 17, 1, 2, 3))
    assert r == {"cargas_borradas": 1, "resultados_archivados_en": "resultados/anteriores/2026-10-17_010203"}
    assert sorted(p.name for p in cargas.iterdir()) == ["otro.txt"]
    archivo = resultados / "anteriores" / "2026-10-17_010203"
    assert (archivo / "analisis_15.json").exists() and (archivo / "grafos" / "particion_N3.json").exists()
    assert [p.name for p in resultados.iterdir()] == ["anteriores"]
    # una segunda vez sin nada nuevo no crea otra carpeta
    assert S.limpiar_archivos(cargas, resultados)["resultados_archivados_en"] is None


def test_limpiar_archivos_sin_carpetas(tmp_path):
    assert S.limpiar_archivos(tmp_path / "no", tmp_path / "tampoco") == \
        {"cargas_borradas": 0, "resultados_archivados_en": None}


# ------------------------------------------------------------------ API
@pytest.fixture
def cliente(libre):
    app.dependency_overrides[R.conexion] = lambda: libre
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_estado(cliente, activado):
    r = cliente.get("/api/mantenimiento")
    assert r.status_code == 200
    assert r.json()["permitido"] is True and r.json()["ocupado"] is None


def test_api_reinicio_de_punta_a_punta(cliente, id_carga, activado):
    (activado / "cargas").mkdir()
    (activado / "cargas" / "carga_9.csv").write_text("x")
    r = cliente.post("/api/mantenimiento/reiniciar", json={"confirmacion": "BORRAR"})
    assert r.status_code == 200, r.text
    assert r.json()["borrado"]["cargas"] >= 1 and r.json()["archivos"]["cargas_borradas"] == 1
    assert all(v == 0 for v in cliente.get("/api/mantenimiento").json()["datos"].values())


def test_api_errores(cliente, activado, monkeypatch):
    assert cliente.post("/api/mantenimiento/reiniciar", json={"confirmacion": "si"}).status_code == 422
    assert cliente.post("/api/mantenimiento/reiniciar", json={}).status_code == 422
    monkeypatch.delenv("PERMITIR_REINICIO")
    r = cliente.post("/api/mantenimiento/reiniciar", json={"confirmacion": "BORRAR"})
    assert r.status_code == 403 and "PERMITIR_REINICIO" in r.json()["detail"]
