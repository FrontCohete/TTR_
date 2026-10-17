"""Agentes (etapa 5): un algoritmo genético por grafo, guardado para que la vista Rutas lo reproduzca.

Flujo de POST /api/agentes:
  1. crear_ejecuciones(): una fila de ejecucion_ag por grafo de la partición, en estado «pendiente».
  2. ejecutar_agentes() en segundo plano, un agente tras otro:
       «ejecutando» → genético (avance 0–85 %) → guardar() en UNA transacción (85–100 %) → «terminado».
     Si algo falla, ese agente queda en «error» con su mensaje y se sigue con el siguiente.
  3. guardar(): borra las rutas (tabla individuo) de las corridas anteriores del mismo grafo,
     escribe generacion e individuo con COPY y deja la ejecución terminada.

Las funciones de consulta (agente, generaciones, individuos, ruta) arman las respuestas de
README_INTEGRACION §4.13–4.16, con la élite de DECISIONES_ETAPA5_GENETICO.md.
"""
import json
import logging

import numpy as np
from sqlalchemy import text

from app.servicios import genetico as AG

log = logging.getLogger("ttr.agentes")
PARAMETROS = ("tam_poblacion", "n_generaciones", "tam_torneo", "prob_cruce", "prob_mutacion",
              "op_cruce", "op_mutacion", "semilla", "ruta_cerrada", "n_elite")
AVANCE_GENETICO = 85          # el genético llena 0–85 %; el guardado, 85–100 %


class NoEncontrado(LookupError):
    """404."""


class Ocupado(RuntimeError):
    """409: ya hay agentes calculándose."""


class NoTerminado(RuntimeError):
    """409: el agente todavía no tiene resultado."""


# ------------------------------------------------------------------ crear
def crear_ejecuciones(con, id_particion: int, p: AG.Parametros) -> list[dict]:
    """Una ejecución por grafo de la partición. No hace commit."""
    p.validar()
    con.execute(text("SELECT pg_advisory_xact_lock(5005)"))          # dos clics seguidos no duplican
    ocupada = con.execute(text(
        "SELECT min(id_ejecucion) FROM ejecucion_ag WHERE estado IN ('pendiente', 'ejecutando')")).scalar()
    if ocupada is not None:
        raise Ocupado(f"Todavía se están calculando agentes (ejecución {ocupada}). Espera a que terminen.")
    grafos = con.execute(text(
        "SELECT id_grafo, numero FROM grafo WHERE id_particion = :p ORDER BY numero"), {"p": id_particion}).all()
    if not grafos:
        raise NoEncontrado(f"No existe la partición {id_particion}.")
    valores = {k: getattr(p, k) for k in PARAMETROS}
    creadas = []
    for id_grafo, numero in grafos:
        id_ejecucion = con.execute(text("""
            INSERT INTO ejecucion_ag (id_grafo, tam_poblacion, n_generaciones, tam_torneo, prob_cruce, prob_mutacion,
                                      op_cruce, op_mutacion, semilla, ruta_cerrada, n_elite, estado, avance)
            VALUES (:g, :tam_poblacion, :n_generaciones, :tam_torneo, :prob_cruce, :prob_mutacion,
                    :op_cruce, :op_mutacion, :semilla, :ruta_cerrada, :n_elite, 'pendiente', 0)
            RETURNING id_ejecucion
        """), {"g": id_grafo, **valores}).scalar_one()
        creadas.append({"id_ejecucion": id_ejecucion, "id_grafo": id_grafo, "numero": numero, "estado": "pendiente"})
    return creadas


# ------------------------------------------------------------------ ejecutar (segundo plano)
def ejecutar_agentes(ids_ejecucion: list[int], motor=None) -> None:
    """Corre los agentes uno tras otro. `motor` es el engine (las pruebas pasan uno propio)."""
    if motor is None:
        from app.basedatos import engine as motor
    for id_ejecucion in ids_ejecucion:
        try:
            ejecutar_uno(id_ejecucion, motor)
        except Exception as error:                     # un agente con error no detiene a los demás
            log.exception("Falló el agente %s", id_ejecucion)
            with motor.begin() as con:
                con.execute(text("""
                    UPDATE ejecucion_ag SET estado = 'error', mensaje_error = :m WHERE id_ejecucion = :e
                """), {"e": id_ejecucion, "m": f"No se pudo calcular la ruta de este agente ({type(error).__name__}: {error})."})


def ejecutar_uno(id_ejecucion: int, motor) -> None:
    with motor.begin() as con:
        fila = con.execute(text("SELECT * FROM ejecucion_ag WHERE id_ejecucion = :e"), {"e": id_ejecucion}).mappings().one()
        p = AG.Parametros.desde(dict(fila))
        ids, D, hotspots = datos_grafo(con, fila["id_grafo"])
        con.execute(text("UPDATE ejecucion_ag SET estado = 'ejecutando', avance = 0 WHERE id_ejecucion = :e"),
                    {"e": id_ejecucion})

    def avisar(fraccion):
        with motor.begin() as c:
            c.execute(text("UPDATE ejecucion_ag SET avance = :a WHERE id_ejecucion = :e"),
                      {"a": int(fraccion * AVANCE_GENETICO), "e": id_ejecucion})

    r = AG.ejecutar_ag(ids, D, p, al_avanzar=avisar)
    avisar(89 / AVANCE_GENETICO)                       # 89 %: guardando
    with motor.begin() as con:
        guardar(con, id_ejecucion, fila["id_grafo"], r, hotspots)
    log.info("Agente %s: %d hotspots, %.1f m (generación %d), %.1f s",
             id_ejecucion, len(ids), r.mejor_distancia, r.generacion_mejor, r.duracion_s)


def datos_grafo(con, id_grafo: int):
    """ids (por etiqueta), matriz de distancias de la tabla arista e info de cada hotspot."""
    hotspots = [dict(h) for h in con.execute(text("""
        SELECT h.id_hotspot, h.etiqueta, h.codigo, h.n_puntos, h.indice_gravedad, h.lat_centroide, h.lon_centroide
        FROM nodo_grafo n JOIN hotspot h USING (id_hotspot)
        WHERE n.id_grafo = :g ORDER BY h.etiqueta
    """), {"g": id_grafo}).mappings()]
    if not hotspots:
        raise NoEncontrado(f"El grafo {id_grafo} no tiene hotspots.")
    ids = [int(h["id_hotspot"]) for h in hotspots]
    pos = {h: i for i, h in enumerate(ids)}
    D = np.zeros((len(ids), len(ids)))
    for o, d, m in con.execute(text("SELECT id_origen, id_destino, distancia_m FROM arista WHERE id_grafo = :g"),
                               {"g": id_grafo}):
        D[pos[o], pos[d]] = D[pos[d], pos[o]] = float(m)
    return ids, D, hotspots


# ------------------------------------------------------------------ guardar
def guardar(con, id_ejecucion: int, id_grafo: int, r: AG.Resultado, hotspots: list[dict]) -> None:
    """generacion + individuo con COPY, limpieza de corridas viejas y ejecución terminada. No hace commit."""
    borrar_rutas_anteriores(con, id_grafo, id_ejecucion)
    G = len(r.generaciones)
    ids_gen = _reservar(con, "generacion", "id_generacion", G)
    tamanos = [len(g.distancia) for g in r.generaciones]
    ids_ind = _reservar(con, "individuo", "id_individuo", sum(tamanos))
    crudo = con.connection.driver_connection
    with crudo.cursor() as cur:
        with cur.copy("COPY generacion (id_generacion, id_ejecucion, numero, mejor_fitness, fitness_promedio, "
                      "peor_fitness, mejor_permutacion, operaciones) FROM STDIN") as copia:
            for g, s in enumerate(r.resumen):
                ops = r.operaciones(g)
                copia.write_row((ids_gen[g], id_ejecucion, g, s["mejor_fitness"], s["fitness_promedio"], s["peor_fitness"],
                                 json.dumps(s["mejor_permutacion"]), None if ops is None else json.dumps(ops)))
        with cur.copy("COPY individuo (id_individuo, id_generacion, posicion, permutacion, distancia, origen, "
                      "id_padre_1, id_padre_2) FROM STDIN") as copia:
            inicio, previos = 0, None
            for g, gen in enumerate(r.generaciones):
                propios = ids_ind[inicio:inicio + tamanos[g]]
                filas = gen.poblacion.tolist()
                for i, fila in enumerate(filas):
                    p1, p2 = int(gen.padres[i, 0]), int(gen.padres[i, 1])
                    copia.write_row((propios[i], ids_gen[g], i, json.dumps([r.ids[k] for k in fila]),
                                     round(float(gen.distancia[i]), 1), AG.ORIGENES[gen.origen[i]],
                                     previos[p1] if p1 >= 0 else None, previos[p2] if p2 >= 0 else None))
                previos, inicio = propios, inicio + tamanos[g]
    ruta = r.ruta_optima
    if r.parametros.ruta_cerrada:                       # empieza en el hotspot de mayor carga (no cambia la distancia)
        ruta = AG.presentar_ruta(ruta, AG.prioridad_hotspots(hotspots))
    con.execute(text("""
        UPDATE ejecucion_ag
        SET estado = 'terminado', avance = 100, mejor_distancia = :d, ruta_optima = CAST(:ruta AS jsonb),
            generacion_mejor = :gm, duracion_s = :t, mensaje_error = NULL
        WHERE id_ejecucion = :e
    """), {"e": id_ejecucion, "d": r.mejor_distancia, "ruta": json.dumps(ruta), "gm": r.generacion_mejor, "t": r.duracion_s})


def borrar_rutas_anteriores(con, id_grafo: int, id_ejecucion: int) -> int:
    """Borra las filas de individuo de las corridas anteriores del grafo; conserva ejecucion_ag y generacion."""
    viejas = con.execute(text("""
        SELECT id_ejecucion FROM ejecucion_ag
        WHERE id_grafo = :g AND id_ejecucion <> :e AND NOT rutas_borradas AND estado IN ('terminado', 'error')
    """), {"g": id_grafo, "e": id_ejecucion}).scalars().all()
    if not viejas:
        return 0
    # primero se sueltan las referencias a padres (si no, cada fila borrada busca a sus hijos)
    con.execute(text("""
        UPDATE individuo SET id_padre_1 = NULL, id_padre_2 = NULL
        WHERE id_generacion IN (SELECT id_generacion FROM generacion WHERE id_ejecucion = ANY(:v))
          AND (id_padre_1 IS NOT NULL OR id_padre_2 IS NOT NULL)
    """), {"v": viejas})
    n = con.execute(text("""
        DELETE FROM individuo WHERE id_generacion IN (SELECT id_generacion FROM generacion WHERE id_ejecucion = ANY(:v))
    """), {"v": viejas}).rowcount
    con.execute(text("UPDATE ejecucion_ag SET rutas_borradas = true WHERE id_ejecucion = ANY(:v)"), {"v": viejas})
    return n


def _reservar(con, tabla: str, columna: str, n: int) -> list[int]:
    """Pide n ids a la secuencia de una vez, para poder escribir los padres en el mismo COPY."""
    return con.execute(text(f"SELECT nextval(pg_get_serial_sequence('{tabla}', '{columna}')) "
                            f"FROM generate_series(1, :n)"), {"n": n}).scalars().all()


def recuperar_interrumpidos(motor=None) -> int:
    """Al encender la API: los agentes que quedaron a medias por un reinicio pasan a error."""
    if motor is None:
        from app.basedatos import engine as motor
    with motor.begin() as con:
        return con.execute(text("""
            UPDATE ejecucion_ag SET estado = 'error',
                   mensaje_error = 'El servidor se reinició mientras se calculaba. Vuelve a generar los agentes.'
            WHERE estado IN ('pendiente', 'ejecutando')
        """)).rowcount


# ------------------------------------------------------------------ consultas (vista Rutas y Simular)
def _ejecucion(con, id_ejecucion: int):
    e = con.execute(text("""
        SELECT e.*, g.numero, g.color, g.n_nodos
        FROM ejecucion_ag e JOIN grafo g USING (id_grafo) WHERE e.id_ejecucion = :e
    """), {"e": id_ejecucion}).mappings().first()
    if e is None:
        raise NoEncontrado(f"No existe el agente {id_ejecucion}.")
    return e


def agente(con, id_ejecucion: int) -> dict:
    """GET /api/agentes/{id} (§4.13)."""
    e = _ejecucion(con, id_ejecucion)
    return {
        "id_ejecucion": e["id_ejecucion"], "id_grafo": e["id_grafo"], "numero": e["numero"], "color": e["color"],
        "n_nodos": e["n_nodos"], "estado": e["estado"], "avance": e["avance"],
        "mejor_distancia": e["mejor_distancia"], "ruta_optima": e["ruta_optima"],
        "generacion_mejor": e["generacion_mejor"], "duracion_s": e["duracion_s"], "mensaje_error": e["mensaje_error"],
        "parametros": {k: e[k] for k in PARAMETROS},
    }


def _terminado(e):
    if e["estado"] != "terminado":
        raise NoTerminado("El algoritmo de este agente todavía no termina." if e["estado"] != "error"
                          else (e["mensaje_error"] or "El algoritmo de este agente terminó con error."))


def generaciones(con, id_ejecucion: int) -> list[dict]:
    """GET /api/agentes/{id}/generaciones (§4.14): índice = numero, de la 0 a la última."""
    _terminado(_ejecucion(con, id_ejecucion))
    return [dict(g) for g in con.execute(text("""
        SELECT id_generacion, numero, mejor_fitness, fitness_promedio, peor_fitness, mejor_permutacion
        FROM generacion WHERE id_ejecucion = :e ORDER BY numero
    """), {"e": id_ejecucion}).mappings()]


def individuos(con, id_generacion: int) -> dict:
    """GET /api/generaciones/{id}/individuos (§4.15). padre_1 y padre_2 salen como posiciones."""
    g = con.execute(text("""
        SELECT g.id_generacion, g.numero, g.operaciones, e.rutas_borradas
        FROM generacion g JOIN ejecucion_ag e USING (id_ejecucion) WHERE g.id_generacion = :g
    """), {"g": id_generacion}).mappings().first()
    if g is None:
        raise NoEncontrado(f"No existe la generación {id_generacion}.")
    if g["rutas_borradas"]:
        raise NoEncontrado("Las rutas de esta corrida se borraron porque hay una más nueva del mismo grafo. "
                           "Vuelve a Analizar y genera los agentes de nuevo.")
    filas = con.execute(text("""
        SELECT i.posicion, i.permutacion, i.distancia, i.origen, p1.posicion AS padre_1, p2.posicion AS padre_2
        FROM individuo i
        LEFT JOIN individuo p1 ON p1.id_individuo = i.id_padre_1
        LEFT JOIN individuo p2 ON p2.id_individuo = i.id_padre_2
        WHERE i.id_generacion = :g ORDER BY i.posicion
    """), {"g": id_generacion}).mappings().all()
    return {"id_generacion": g["id_generacion"], "numero": g["numero"],
            "individuos": [dict(f) for f in filas], "operaciones": g["operaciones"]}


def ruta(con, id_ejecucion: int) -> dict:
    """GET /api/agentes/{id}/ruta (§4.16): LineString de centroides en el orden de visita."""
    e = _ejecucion(con, id_ejecucion)
    _terminado(e)
    orden = [int(h) for h in e["ruta_optima"]]
    info = {int(h["id_hotspot"]): h for h in con.execute(text("""
        SELECT id_hotspot, codigo, lon_centroide, lat_centroide FROM hotspot WHERE id_hotspot = ANY(:ids)
    """), {"ids": orden}).mappings()}
    coords = [[round(float(info[h]["lon_centroide"]), 6), round(float(info[h]["lat_centroide"]), 6)] for h in orden]
    if e["ruta_cerrada"] and len(coords) > 1:
        coords.append(coords[0])
    if len(coords) == 1:                      # un solo hotspot: LineString de 2 puntos iguales
        coords.append(coords[0])
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {
            "id_ejecucion": e["id_ejecucion"], "numero_grafo": e["numero"], "color": e["color"],
            "distancia_m": e["mejor_distancia"], "orden": [info[h]["codigo"] for h in orden], "hotspots": orden,
            "ruta_cerrada": e["ruta_cerrada"], "generacion_mejor": e["generacion_mejor"],
        },
    }


def registrar_simulacion(con, id_ejecucion: int, distancia_total: float | None, duracion_s: float | None) -> dict:
    """POST /api/simulaciones (§4.17). No hace commit."""
    _ejecucion(con, id_ejecucion)
    fila = con.execute(text("""
        INSERT INTO simulacion (id_ejecucion, distancia_total, duracion_s) VALUES (:e, :d, :t)
        RETURNING id_simulacion, id_ejecucion, fecha, distancia_total, duracion_s
    """), {"e": id_ejecucion, "d": distancia_total, "t": duracion_s}).mappings().one()
    return {**fila, "fecha": fila["fecha"].isoformat()}