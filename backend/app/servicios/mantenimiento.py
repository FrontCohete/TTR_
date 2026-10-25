"""Mantenimiento (etapa 5.6): «Empezar de cero» para cargar datasets nuevos.

Borra TODO lo que sale de los datasets (cargas, puntos, análisis, hotspots, particiones, grafos,
agentes y simulaciones) y conserva los catálogos (alcaldía, colonias y delitos con su gravedad),
sin los cuales la siguiente carga fallaría. Los ids vuelven a empezar en 1.

Protecciones:
  * solo funciona si backend/.env tiene PERMITIR_REINICIO=true (si no, 403);
  * hay que mandar la palabra BORRAR (si no, 422);
  * no corre si hay una carga procesándose o agentes calculándose (409). Toma los mismos candados
    que las cargas (2024), las particiones (4004) y los agentes (5005), así nada empieza a la mitad;
  * TRUNCATE va dentro de la transacción: si algo falla, no se borra nada.

Archivos (después del commit):
  * backend/cargas/carga_*: archivos subidos que no se procesaron. Se borran, porque con los ids
    reiniciados «carga_1.xlsx» chocaría con la nueva carga 1;
  * backend/resultados/: los JSON de los scripts (analisis_<id>.json, grafos/particion_N<n>.json).
    NO se borran: se mueven a resultados/anteriores/<fecha>/ porque pueden ser evidencia de la tesis
    y sus ids ya no coinciden con la base nueva.
"""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config import CARPETA_CARGAS

log = logging.getLogger("uvicorn.error")

BACKEND = Path(__file__).resolve().parents[2]
CARPETA_RESULTADOS = BACKEND / "resultados"
CONFIRMACION = "BORRAR"

CATALOGOS = ("alcaldia", "colonia", "cat_delito")
TABLAS_DE_DATOS = (
    "carga_dataset", "punto_delictivo", "analisis_hdbscan", "analisis_carga", "hotspot",
    "membresia_hotspot", "particion_louvain", "grafo", "nodo_grafo", "arista",
    "ejecucion_ag", "generacion", "individuo", "simulacion",
)
CANDADOS = (2024, 4004, 5005)        # cargas, particiones, agentes (mismo orden siempre)

# Lo que se muestra en el diálogo de confirmación
_CONTEOS = {
    "cargas": "SELECT count(*) FROM carga_dataset",
    "puntos": "SELECT count(*) FROM punto_delictivo",
    "analisis": "SELECT count(*) FROM analisis_hdbscan",
    "hotspots": "SELECT count(*) FROM hotspot WHERE id_analisis = "
                "(SELECT id_analisis FROM analisis_hdbscan WHERE vigente)",
    "particiones": "SELECT count(*) FROM particion_louvain",
    "agentes": "SELECT count(*) FROM ejecucion_ag",
    "simulaciones": "SELECT count(*) FROM simulacion",
}
_CONTEOS_CATALOGO = {
    "colonias": "SELECT count(*) FROM colonia",
    "delitos": "SELECT count(*) FROM cat_delito",
}


class NoPermitido(PermissionError):
    """PERMITIR_REINICIO no está activado. La ruta responde 403."""


class ConfirmacionInvalida(ValueError):
    """No se escribió BORRAR. La ruta responde 422."""


class Ocupado(RuntimeError):
    """Hay trabajo en curso. La ruta responde 409."""


def permitido() -> bool:
    return os.getenv("PERMITIR_REINICIO", "false").strip().lower() in ("1", "true", "si", "sí")


def motivo_ocupado(con) -> str | None:
    """Por qué no se puede reiniciar ahora, o None si se puede."""
    carga = con.execute(text(
        "SELECT id_carga, nombre_archivo FROM carga_dataset WHERE estado = 'procesando' LIMIT 1"
    )).first()
    if carga:
        return (f"La carga {carga.id_carga} ({carga.nombre_archivo}) se está procesando. "
                "Espera a que termine y vuelve a intentarlo.")
    agentes = con.execute(text(
        "SELECT count(*) FROM ejecucion_ag WHERE estado IN ('pendiente', 'ejecutando')"
    )).scalar()
    if agentes:
        return (f"Hay {agentes} agente(s) calculando su ruta. "
                "Espera a que terminen y vuelve a intentarlo.")
    return None


def _espacio(con) -> int:
    return int(con.execute(text(
        "SELECT coalesce(sum(pg_total_relation_size(t::regclass)), 0) FROM unnest(CAST(:t AS text[])) AS t"
    ), {"t": list(TABLAS_DE_DATOS)}).scalar())


def legible(n_bytes: int) -> str:
    for unidad in ("B", "kB", "MB", "GB"):
        if n_bytes < 1024 or unidad == "GB":
            return f"{n_bytes:,.0f} {unidad}" if unidad == "B" else f"{n_bytes:,.1f} {unidad}"
        n_bytes /= 1024
    return ""


def resumen(con) -> dict:
    """GET /api/mantenimiento: qué hay hoy, cuánto ocupa y si se puede reiniciar."""
    datos = {k: int(con.execute(text(q)).scalar()) for k, q in _CONTEOS.items()}
    espacio = _espacio(con)
    return {
        "permitido": permitido(),
        "ocupado": motivo_ocupado(con),
        "confirmacion": CONFIRMACION,
        "datos": datos,
        "espacio_bytes": espacio,
        "espacio": legible(espacio),
        "se_conservan": {k: int(con.execute(text(q)).scalar()) for k, q in _CONTEOS_CATALOGO.items()},
    }


def reiniciar(con, confirmacion: str) -> dict:
    """Vacía las tablas de datos dentro de la transacción de `con` (no hace commit).

    Devuelve lo que había antes (para el mensaje «se borraron …»).
    """
    if not permitido():
        raise NoPermitido("El reinicio está desactivado. Para activarlo, agrega PERMITIR_REINICIO=true "
                          "en backend/.env y reinicia el servidor.")
    if (confirmacion or "").strip() != CONFIRMACION:
        raise ConfirmacionInvalida(f"Para confirmar escribe {CONFIRMACION} en mayúsculas.")
    try:
        con.execute(text("SET LOCAL lock_timeout = '10s'"))
        for candado in CANDADOS:
            con.execute(text("SELECT pg_advisory_xact_lock(:c)"), {"c": candado})
        motivo = motivo_ocupado(con)
        if motivo:
            raise Ocupado(motivo)
        antes = {k: int(con.execute(text(q)).scalar()) for k, q in _CONTEOS.items()}
        antes["espacio"] = legible(_espacio(con))
        con.execute(text(f"TRUNCATE {', '.join(TABLAS_DE_DATOS)} RESTART IDENTITY CASCADE"))
    except OperationalError as error:
        if "lock" in str(error).lower():
            raise Ocupado("La base de datos está en uso (alguien está consultando o guardando). "
                          "Vuelve a intentarlo en unos segundos.") from error
        raise
    return antes


def limpiar_archivos(cargas: Path | None = None, resultados: Path | None = None,
                     ahora: datetime | None = None) -> dict:
    """Después del commit: borra los archivos subidos y archiva los JSON de resultados/."""
    cargas = cargas or CARPETA_CARGAS
    resultados = resultados or CARPETA_RESULTADOS
    borrados = 0
    if cargas.is_dir():
        for archivo in cargas.glob("carga_*"):
            if archivo.is_file():
                archivo.unlink(missing_ok=True)
                borrados += 1

    archivado = None
    if resultados.is_dir():
        mover = [p for p in resultados.iterdir() if p.name != "anteriores"]
        if mover:
            destino = resultados / "anteriores" / (ahora or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
            destino.mkdir(parents=True, exist_ok=True)
            for p in mover:
                shutil.move(str(p), str(destino / p.name))
                archivado = destino.relative_to(resultados.parent).as_posix()   # mismo texto en Windows y Linux
    return {"cargas_borradas": borrados, "resultados_archivados_en": archivado}
