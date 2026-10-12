"""Procesamiento de una carga (etapa 2, pieza 2.11; etapa 3, pieza 3.5).

POST /procesar   → iniciar():  revisa la carga y la marca 'procesando' (rápido).
segundo plano    → procesar(): tres etapas, informando el avance:
                     1. limpieza   leer y limpiar el archivo, aplicar A + P      0 – 30 %
                     2. insercion  guardar los puntos nuevos (commit)            30 – 80 %
                     3. hdbscan    nuevo análisis vigente, si hay puntos nuevos  80 – 100 %
                   Solo al final deja la carga en 'completado' (o en 'error').
GET /cargas…     → obtener_carga() y listar_cargas().

Si falla HDBSCAN, los puntos ya insertados se conservan y el análisis anterior sigue
vigente. Al volver a pulsar «Analizar», procesar() ve que los puntos ya están y
salta directo a la etapa hdbscan.
"""
import json
import logging
import time

from sqlalchemy import text

from app.basedatos import engine
from app.config import CARPETA_CARGAS
from app.servicios import analisis, huella, ingesta, insercion, limpieza

log = logging.getLogger("uvicorn.error")


class CargaNoEncontrada(LookupError):
    """No existe esa carga. La ruta responde 404."""


class ConflictoCarga(Exception):
    """La carga no se puede procesar ahora. La ruta responde 409."""


class ProcesamientoInvalido(Exception):
    """Un problema conocido del archivo; su texto se muestra tal cual a la persona."""


# ------------------------------------------------------- escribir en la carga
_CAMPOS = {"estado", "etapa", "avance", "mensaje_error", "filas_validas",
           "puntos_gam_nuevos", "puntos_duplicados", "resumen_limpieza"}


def marcar(con, id_carga: int, **campos) -> None:
    """Actualiza columnas de carga_dataset. Solo acepta las de la lista _CAMPOS."""
    desconocidos = set(campos) - _CAMPOS
    if desconocidos:
        raise ValueError(f"Columnas no permitidas: {desconocidos}")
    if "resumen_limpieza" in campos:
        campos["resumen_limpieza"] = json.dumps(campos["resumen_limpieza"], ensure_ascii=False)
    asignaciones = ", ".join(
        f"{c} = CAST(:{c} AS jsonb)" if c == "resumen_limpieza" else f"{c} = :{c}"
        for c in campos
    )
    con.execute(text(f"UPDATE carga_dataset SET {asignaciones} WHERE id_carga = :id"),
                {**campos, "id": id_carga})


def marcar_aparte(id_carga: int, **campos) -> None:
    """Igual que marcar(), en su propia transacción: el frontend lo ve al instante."""
    with engine.begin() as con:
        marcar(con, id_carga, **campos)


# ------------------------------------------------------------ POST /procesar
def iniciar(con, id_carga: int) -> None:
    """Revisa que la carga se pueda procesar y la deja en 'procesando'."""
    con.execute(text("SELECT pg_advisory_xact_lock(2024)"))   # una revisión a la vez
    fila = con.execute(text("SELECT estado FROM carga_dataset WHERE id_carga = :id"),
                       {"id": id_carga}).first()
    if fila is None:
        raise CargaNoEncontrada(f"No existe la carga {id_carga}.")
    if fila.estado == "completado":
        raise ConflictoCarga(f"La carga {id_carga} ya se había procesado.")
    if fila.estado == "procesando":
        raise ConflictoCarga(f"La carga {id_carga} ya se está procesando.")
    otra = con.execute(text("""
        SELECT id_carga FROM carga_dataset
         WHERE estado = 'procesando' AND id_carga <> :id LIMIT 1
    """), {"id": id_carga}).scalar()
    if otra is not None:
        raise ConflictoCarga(f"Espera a que termine la carga {otra}: se procesa una a la vez.")
    marcar(con, id_carga, estado="procesando", etapa="limpieza", avance=0, mensaje_error=None)


# ----------------------------------------------------------- segundo plano
def ejecutar(con, id_carga: int, avisar) -> dict:
    """Todo el trabajo, dentro de la transacción `con`. `avisar(**campos)` informa el avance."""
    carga = con.execute(text(
        "SELECT nombre_archivo, formato FROM carga_dataset WHERE id_carga = :id"
    ), {"id": id_carga}).one()

    ruta = ingesta.ruta_archivo(id_carga, carga.formato)
    if not ruta.exists():
        raise ProcesamientoInvalido("No se encontró el archivo de esta carga. Vuelve a subirlo.")
    leido = ingesta.leer_archivo(ruta.read_bytes(), carga.nombre_archivo)
    faltantes = ingesta.revisar_columnas(leido.datos)["faltantes"]
    if faltantes:
        raise ProcesamientoInvalido("Faltan columnas obligatorias: " + ", ".join(faltantes) + ".")
    avisar(avance=10)

    # Limpieza y regla A + P
    r = limpieza.limpiar(leido.datos, limpieza.catalogo_delitos(con))
    avisar(avance=20)
    puntos, de_periodos_cargados, calendario = huella.aplicar_calendario(
        r.puntos, huella.dias_cargados(con))
    huellas = huella.huellas(puntos)
    avisar(etapa="insercion", avance=30)

    # Inserción: del 30 % al 80 %
    insertados = insercion.insertar_puntos(
        con, puntos, huellas, id_carga,
        al_avanzar=lambda f: avisar(avance=30 + round(50 * f)),
    )
    duplicados_por_huella = len(puntos) - insertados

    resumen = {
        "filas_leidas": r.filas_leidas,
        "filas_gam": r.filas_gam,
        "filas_validas": r.filas_validas,
        "descartadas": r.descartadas,
        "edades_anuladas": r.edades_anuladas,
        "delitos_desconocidos": r.delitos_desconocidos,
        "calendario_aplicado": calendario,
        "de_periodos_cargados": de_periodos_cargados,
        "duplicados_por_huella": duplicados_por_huella,
        "insertados": insertados,
    }
    # En la MISMA transacción que los puntos: o queda todo, o nada.
    # La carga sigue 'procesando': falta la etapa hdbscan (ver procesar()).
    marcar(con, id_carga, etapa="hdbscan", avance=80,
           filas_validas=r.filas_validas, puntos_gam_nuevos=insertados,
           puntos_duplicados=de_periodos_cargados + duplicados_por_huella,
           resumen_limpieza=resumen)
    return resumen


def ya_insertada(id_carga: int) -> bool:
    """True si los puntos de esta carga ya se guardaron en un intento anterior.

    puntos_gam_nuevos se escribe en la misma transacción que los puntos: si tiene
    valor, la inserción terminó bien (aunque después haya fallado HDBSCAN).
    """
    with engine.connect() as con:
        return con.execute(text(
            "SELECT puntos_gam_nuevos IS NOT NULL FROM carga_dataset WHERE id_carga = :id"
        ), {"id": id_carga}).scalar() is True


def actualizar_hotspots(id_carga: int, avisar) -> int | None:
    """Etapa hdbscan: crea el análisis nuevo y lo deja vigente (con commit).

    Se omite si el análisis vigente ya usa todos los puntos (la carga no aportó
    puntos nuevos analizables). Devuelve el id_analisis nuevo, o None si se omitió.
    """
    avisar(etapa="hdbscan", avance=80)
    with engine.connect() as con:
        if analisis.esta_al_dia(con):
            return None
    id_analisis, _ = analisis.nuevo_analisis(
        engine, id_carga, al_avanzar=lambda f: avisar(avance=80 + round(20 * f)))
    return id_analisis


def procesar(id_carga: int) -> None:
    """Se ejecuta en segundo plano. Nunca lanza errores: los deja escritos en la carga."""
    inicio = time.perf_counter()

    def avisar(**campos):
        marcar_aparte(id_carga, **campos)

    # Etapas 1 y 2: limpieza e inserción (se saltan si ya se hicieron en un intento anterior)
    try:
        if not ya_insertada(id_carga):
            with engine.begin() as con:
                ejecutar(con, id_carga, avisar)
    except (ProcesamientoInvalido, ingesta.ArchivoInvalido) as error:
        marcar_aparte(id_carga, estado="error", mensaje_error=str(error))
        return
    except Exception as error:
        log.exception("Falló el procesamiento de la carga %s", id_carga)
        marcar_aparte(id_carga, estado="error", mensaje_error=(
            f"Error inesperado al procesar ({type(error).__name__}). "
            "Revisa la terminal del backend."))
        return

    # Etapa 3: HDBSCAN. El análisis queda vigente ANTES de marcar 'completado'.
    try:
        id_analisis = actualizar_hotspots(id_carga, avisar)
    except Exception as error:
        log.exception("Falló HDBSCAN en la carga %s", id_carga)
        marcar_aparte(id_carga, estado="error", mensaje_error=(
            f"Los puntos se guardaron, pero falló el cálculo de hotspots ({type(error).__name__}). "
            "El análisis anterior sigue vigente. Vuelve a pulsar Analizar para reintentarlo."))
        return

    marcar_aparte(id_carga, estado="completado", avance=100)
    for archivo in CARPETA_CARGAS.glob(f"carga_{id_carga}.*"):   # ya no hace falta
        archivo.unlink(missing_ok=True)
    log.info("Carga %s procesada en %.1f s · %s", id_carga, time.perf_counter() - inicio,
             f"análisis {id_analisis} vigente" if id_analisis
             else "sin puntos nuevos: se conserva el análisis vigente")


def recuperar_interrumpidas() -> int:
    """Al encender la API: las cargas que quedaron a medias pasan a 'error'."""
    with engine.begin() as con:
        return con.execute(text("""
            UPDATE carga_dataset
               SET estado = 'error',
                   mensaje_error = 'El procesamiento se interrumpió porque el servidor se reinició. Vuelve a pulsar Analizar.'
             WHERE estado = 'procesando'
        """)).rowcount


# ----------------------------------------------------------------- consultas
_SQL_CARGAS = """
    SELECT c.id_carga, c.nombre_archivo, c.formato, c.fecha_carga, c.estado, c.etapa,
           c.avance, c.filas_leidas, c.filas_validas, c.puntos_gam_nuevos,
           c.puntos_duplicados, c.mensaje_error, c.resumen_limpieza,
           (SELECT max(a.id_analisis) FROM analisis_hdbscan a
             WHERE a.id_carga_origen = c.id_carga) AS id_analisis
      FROM carga_dataset c
"""


def obtener_carga(con, id_carga: int) -> dict:
    fila = con.execute(text(_SQL_CARGAS + " WHERE c.id_carga = :id"), {"id": id_carga}).first()
    if fila is None:
        raise CargaNoEncontrada(f"No existe la carga {id_carga}.")
    return dict(fila._mapping)


def listar_cargas(con) -> list[dict]:
    """Historial: de la más nueva a la más vieja, sin las que solo se subieron."""
    filas = con.execute(text(_SQL_CARGAS + """
        WHERE c.estado <> 'recibido'
        ORDER BY c.fecha_carga DESC, c.id_carga DESC
    """))
    return [dict(f._mapping) for f in filas]