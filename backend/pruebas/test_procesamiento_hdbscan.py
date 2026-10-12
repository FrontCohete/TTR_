"""Etapa hdbscan de /procesar (pieza 3.5).

Aquí NO se escribe en la base: se reemplazan (monkeypatch) las funciones que escriben
y se revisa el ORDEN de lo que hace procesar():
  * el análisis queda vigente ANTES de marcar 'completado';
  * sin puntos nuevos, no se repite HDBSCAN;
  * si HDBSCAN falla, la carga queda en 'error' con un mensaje claro;
  * al reintentar, no se vuelve a limpiar ni a insertar.
"""
import pytest

from app.servicios import analisis, procesamiento as P


@pytest.fixture
def registro(monkeypatch):
    """Anota cada paso en una lista en vez de tocar la base."""
    pasos = []
    monkeypatch.setattr(P, "marcar_aparte", lambda id_carga, **c: pasos.append(("marcar", c)))
    monkeypatch.setattr(P, "ya_insertada", lambda id_carga: False)
    monkeypatch.setattr(P, "ejecutar", lambda con, id_carga, avisar: pasos.append(("insertar",)))
    monkeypatch.setattr(analisis, "esta_al_dia", lambda con: False)

    def nuevo_analisis(engine, id_carga, al_avanzar=None):
        al_avanzar(0.5)
        pasos.append(("hdbscan", id_carga))
        return 99, None

    monkeypatch.setattr(analisis, "nuevo_analisis", nuevo_analisis)
    return pasos


def nombres(pasos):
    return [p[0] if p[0] != "marcar" else "marcar:" + p[1].get("estado", p[1].get("etapa", "avance"))
            for p in pasos]


def test_el_analisis_queda_vigente_antes_de_completar(registro):
    P.procesar(7)
    orden = nombres(registro)
    assert orden.index("insertar") < orden.index("hdbscan") < orden.index("marcar:completado")
    assert ("hdbscan", 7) in registro                          # origen = esta carga
    assert registro[-1] == ("marcar", {"estado": "completado", "avance": 100})


def test_informa_la_etapa_y_el_avance_de_hdbscan(registro):
    P.procesar(7)
    marcas = [c for p, *resto in registro if p == "marcar" for c in resto]
    assert {"etapa": "hdbscan", "avance": 80} in marcas
    assert {"avance": 90} in marcas                            # 80 + 20 × 0.5


def test_sin_puntos_nuevos_no_repite_hdbscan(registro, monkeypatch):
    monkeypatch.setattr(analisis, "esta_al_dia", lambda con: True)
    P.procesar(7)
    assert "hdbscan" not in nombres(registro)
    assert registro[-1] == ("marcar", {"estado": "completado", "avance": 100})


def test_si_falla_hdbscan_queda_en_error_con_mensaje_claro(registro, monkeypatch):
    def falla(*args, **kwargs):
        raise MemoryError()
    monkeypatch.setattr(analisis, "nuevo_analisis", falla)
    P.procesar(7)
    ultimo = registro[-1][1]
    assert ultimo["estado"] == "error"
    assert "Los puntos se guardaron" in ultimo["mensaje_error"]
    assert "MemoryError" in ultimo["mensaje_error"]
    assert "marcar:completado" not in nombres(registro)


def test_al_reintentar_salta_directo_a_hdbscan(registro, monkeypatch):
    monkeypatch.setattr(P, "ya_insertada", lambda id_carga: True)
    P.procesar(7)
    assert "insertar" not in nombres(registro)
    assert "hdbscan" in nombres(registro)


def test_si_falla_la_limpieza_no_corre_hdbscan(registro, monkeypatch):
    def archivo_malo(con, id_carga, avisar):
        raise P.ProcesamientoInvalido("Faltan columnas obligatorias: latitud.")
    monkeypatch.setattr(P, "ejecutar", archivo_malo)
    P.procesar(7)
    assert "hdbscan" not in nombres(registro)
    assert registro[-1][1] == {"estado": "error", "mensaje_error": "Faltan columnas obligatorias: latitud."}