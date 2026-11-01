"""Agentes (etapa 5; «la mejor de tres», etapa 7): un genético por grafo, guardado para la vista Rutas.

Flujo de POST /api/agentes:
  1. crear_ejecuciones(): una fila de ejecucion_ag por grafo de la partición, en estado «pendiente».
  2. ejecutar_agentes() en segundo plano:
       a. liberar_tandas_anteriores(): «solo la última tanda conserva el detalle» (etapa 5.6). A TODOS
          los agentes anteriores se les borran las rutas (individuo) y las operaciones de cada
          generación; se conservan ejecucion_ag (distancia, ruta óptima) y el resumen por generación
          (la curva de aptitud). El detalle se puede regenerar idéntico con la misma semilla.
       b. _matriz_de_la_tanda(): la matriz por calles del análisis (matriz_calles.py), UNA vez por
          tanda. De la base si ya está; si no, se pide a OSRM. Si no se puede, todos corren solo A.
       c. un agente tras otro: «ejecutando» → «la mejor de tres» (avance 0–85 %) → guardar() en UNA
          transacción (85–100 %) → «terminado». Si algo falla, ese agente queda en «error» con su
          mensaje y se sigue con el siguiente.
  3. guardar(): escribe generacion e individuo con COPY y deja la ejecución terminada.

«La mejor de tres» (etapa 7, PLAN_ETAPA7_CALLES.md): cada agente corre el genético tres veces con la
MISMA semilla, cada una con una forma de medir (A línea recta, B calles con sentido, C calles con el
promedio de ida y vuelta). Las tres rutas se miden por calles en su mejor sentido y gana la más
corta (empate al metro: A, luego C, luego B). Se guarda el paso a paso solo de la ganadora y, en
`comparacion`, el resumen de las tres. A siempre compite, así que nunca queda peor que en línea recta.
`mejor_distancia` = metros por calles de la ganadora (lo que recorre la patrulla); en línea recta
queda en `distancia_recta_m`.

Forma de medir (columna `medir`, se elige en Analizar): «mejor_de_tres» (lo anterior, por defecto) o
una sola: «recta» (solo A), «calles» (solo B), «calles_promedio» (solo C). Con una sola, el genético
corre una vez y la vista Rutas reproduce esa forma de medir aunque no sea la más corta.

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
VARIANTES = (("A", "recta"), ("B", "calles"), ("C", "calles_promedio"))
DESEMPATE = {"A": 0, "C": 1, "B": 2}      # E1: empate al metro → A, luego C, luego B
MEDIR = ("mejor_de_tres", "recta", "calles", "calles_promedio")


class NoEncontrado(LookupError):
    """404."""


class Ocupado(RuntimeError):
    """409: ya hay agentes calculándose."""


class NoTerminado(RuntimeError):
    """409: el agente todavía no tiene resultado."""


# ------------------------------------------------------------------ crear
def crear_ejecuciones(con, id_particion: int, p: AG.Parametros, medir: str = "mejor_de_tres") -> list[dict]:
    """Una ejecución por grafo de la partición. No hace commit."""
    p.validar()
    if medir not in MEDIR:
        raise AG.ParametrosInvalidos(f"La forma de medir debe ser una de: {', '.join(MEDIR)}.")
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
                                      op_cruce, op_mutacion, semilla, ruta_cerrada, n_elite, medir, estado, avance)
            VALUES (:g, :tam_poblacion, :n_generaciones, :tam_torneo, :prob_cruce, :prob_mutacion,
                    :op_cruce, :op_mutacion, :semilla, :ruta_cerrada, :n_elite, :medir, 'pendiente', 0)
            RETURNING id_ejecucion
        """), {"g": id_grafo, **valores, "medir": medir}).scalar_one()
        creadas.append({"id_ejecucion": id_ejecucion, "id_grafo": id_grafo, "numero": numero, "estado": "pendiente"})
    return creadas


# ------------------------------------------------------------------ ejecutar (segundo plano)
def ejecutar_agentes(ids_ejecucion: list[int], motor=None) -> None:
    """Corre los agentes uno tras otro. `motor` es el engine (las pruebas pasan uno propio)."""
    if motor is None:
        from app.basedatos import engine as motor
    try:                                               # si la limpieza falla, los agentes corren igual
        with motor.begin() as con:
            liberado = liberar_tandas_anteriores(con, ids_ejecucion)
        if liberado["agentes"]:
            log.info("Tandas anteriores: se liberó el detalle de %(agentes)d agente(s) "
                     "(%(individuos)d rutas, %(generaciones)d generaciones con operaciones)", liberado)
            _vacuum(motor)
    except Exception:
        log.exception("No se pudo liberar el detalle de las tandas anteriores")
    matriz, motivo = _matriz_de_la_tanda(ids_ejecucion, motor)
    for id_ejecucion in ids_ejecucion:
        try:
            ejecutar_uno(id_ejecucion, motor, matriz, motivo)
        except Exception as error:                     # un agente con error no detiene a los demás
            log.exception("Falló el agente %s", id_ejecucion)
            with motor.begin() as con:
                con.execute(text("""
                    UPDATE ejecucion_ag SET estado = 'error', mensaje_error = :m WHERE id_ejecucion = :e
                """), {"e": id_ejecucion, "m": f"No se pudo calcular la ruta de este agente ({type(error).__name__}: {error})."})


def _matriz_de_la_tanda(ids_ejecucion: list[int], motor):
    """(matriz, motivo): la matriz por calles del análisis de la tanda, o (None, por qué no hay)."""
    from app.servicios import matriz_calles as M      # aquí y no arriba: ruteo importa este módulo
    from app.servicios import ruteo
    try:
        with motor.begin() as con:
            analisis = con.execute(text("""
                SELECT DISTINCT p.id_analisis
                FROM ejecucion_ag e JOIN grafo g USING (id_grafo) JOIN particion_louvain p USING (id_particion)
                WHERE e.id_ejecucion = ANY(:t)
            """), {"t": list(ids_ejecucion)}).scalars().all()
            if len(analisis) != 1:
                return None, "la tanda no corresponde a un solo análisis"
            return M.obtener(con, analisis[0]), None
    except ruteo.RuteoNoDisponible as error:
        log.warning("Sin matriz por calles: los agentes se optimizan solo en línea recta (%s)", error)
        return None, str(error)
    except Exception as error:
        log.exception("No se pudo obtener la matriz por calles")
        return None, f"{type(error).__name__}: {error}"


def elegir(variantes: list[dict]) -> int:
    """Índice de la ganadora: la más corta por calles (o en línea recta si no hay calles), redondeada
    al metro; empate → A, luego C, luego B (E1)."""
    def clave(i):
        v = variantes[i]
        d = v["distancia_calles_m"] if v["distancia_calles_m"] is not None else v["distancia_recta_m"]
        return (round(d), DESEMPATE[v["variante"]])
    return min(range(len(variantes)), key=clave)


def ejecutar_uno(id_ejecucion: int, motor, matriz=None, motivo: str | None = None) -> None:
    from app.servicios import matriz_calles as M
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

    medir = fila.get("medir") or "mejor_de_tres"
    if matriz is not None:
        matrices = matriz.submatrices(ids, recta=D)
        variantes = VARIANTES if medir == "mejor_de_tres" else tuple(v for v in VARIANTES if v[1] == medir)
    else:                                              # respaldo: solo A, como antes de la etapa 7
        matrices, variantes = {"recta": D}, VARIANTES[:1]
    calles = matrices.get("calles")
    pos = {h: i for i, h in enumerate(ids)}
    resumen, ganadora, r_ganadora = [], None, None
    for k, (letra, metrica) in enumerate(variantes):
        r = AG.ejecutar_ag(ids, matrices[metrica], p,
                           al_avanzar=lambda f, k=k: avisar((k + f) / len(variantes)))
        orden = [pos[h] for h in r.ruta_optima]
        recta_m = M.largo(orden, D, p.ruta_cerrada)
        calles_m, invertida = M.mejor_sentido(orden, calles, p.ruta_cerrada) if calles is not None else (None, False)
        resumen.append({
            "variante": letra, "metrica": metrica,
            "distancia_calles_m": None if calles_m is None else round(calles_m, 1),
            "distancia_recta_m": round(recta_m, 1), "fitness_m": r.mejor_distancia,
            "generacion_mejor": r.generacion_mejor, "duracion_s": r.duracion_s,
            "invertida": invertida, "ganadora": False,
        })
        if elegir(resumen) == len(resumen) - 1:        # la nueva es la mejor hasta ahora: se queda su detalle
            ganadora, r_ganadora = resumen[-1], r
        del r                                          # solo se conserva en memoria el detalle de la mejor
    ganadora["ganadora"] = True
    if matriz is not None:
        aviso = None
    elif medir == "recta":
        aviso = f"No se pudo obtener la distancia por calles ({motivo}): no se sabe cuánto mide esta ruta por calles."
    else:
        aviso = f"No se pudo obtener la distancia por calles ({motivo}). Este agente se optimizó solo en línea recta."
    comparacion = {"medir": medir, "ganadora": ganadora["variante"], "variantes": resumen, "aviso": aviso}
    eleccion = {
        "metrica": ganadora["metrica"], "invertir": ganadora["invertida"], "comparacion": comparacion,
        "distancia_recta_m": ganadora["distancia_recta_m"],
        "mejor_distancia": ganadora["distancia_calles_m"] if ganadora["distancia_calles_m"] is not None
        else r_ganadora.mejor_distancia,
    }
    avisar(89 / AVANCE_GENETICO)                       # 89 %: guardando
    with motor.begin() as con:
        guardar(con, id_ejecucion, fila["id_grafo"], r_ganadora, hotspots, eleccion)
    log.info("Agente %s: %d hotspots · gana %s (%s) · %.1f m por calles, %.1f m en línea recta · %s",
             id_ejecucion, len(ids), ganadora["variante"], ganadora["metrica"], eleccion["mejor_distancia"],
             ganadora["distancia_recta_m"],
             " / ".join(f"{v['variante']} {v['distancia_calles_m'] or v['distancia_recta_m']:.0f} m" for v in resumen))


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
def guardar(con, id_ejecucion: int, id_grafo: int, r: AG.Resultado, hotspots: list[dict],
            eleccion: dict | None = None) -> None:
    """generacion + individuo con COPY y ejecución terminada. No hace commit.

    eleccion (etapa 7): metrica, invertir, mejor_distancia (por calles), distancia_recta_m y
    comparacion. Sin ella se guarda como antes: optimizado y medido en línea recta.
    """
    if eleccion is None:
        eleccion = {"metrica": "recta", "invertir": False, "comparacion": None,
                    "mejor_distancia": r.mejor_distancia, "distancia_recta_m": r.mejor_distancia}
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
    ruta = list(r.ruta_optima)
    if eleccion["invertir"]:                            # con calles de un sentido, el sentido más corto
        ruta = ruta[::-1]
    if r.parametros.ruta_cerrada:                       # empieza en el hotspot de mayor carga (no cambia la distancia)
        ruta = AG.presentar_ruta(ruta, AG.prioridad_hotspots(hotspots))
    comparacion = eleccion["comparacion"]
    duracion = sum(v["duracion_s"] for v in comparacion["variantes"]) if comparacion else r.duracion_s
    con.execute(text("""
        UPDATE ejecucion_ag
        SET estado = 'terminado', avance = 100, mejor_distancia = :d, ruta_optima = CAST(:ruta AS jsonb),
            generacion_mejor = :gm, duracion_s = :t, mensaje_error = NULL,
            metrica = :m, distancia_recta_m = :dr, comparacion = CAST(:c AS jsonb)
        WHERE id_ejecucion = :e
    """), {"e": id_ejecucion, "d": round(float(eleccion["mejor_distancia"]), 1), "ruta": json.dumps(ruta),
           "gm": r.generacion_mejor, "t": round(duracion, 3), "m": eleccion["metrica"],
           "dr": round(float(eleccion["distancia_recta_m"]), 1),
           "c": None if comparacion is None else json.dumps(comparacion)})


def liberar_tandas_anteriores(con, tanda: list[int]) -> dict:
    """«Solo la última tanda conserva el detalle»: borra individuo y operaciones de los demás agentes.

    `tanda`: los id_ejecucion que se van a calcular ahora (no se tocan). Solo se liberan agentes
    terminados o con error (crear_ejecuciones ya impide que haya otros calculando). También vacía
    operaciones que quedaron de corridas limpiadas con la regla anterior. No hace commit.
    """
    viejas = con.execute(text("""
        SELECT id_ejecucion FROM ejecucion_ag
        WHERE NOT (id_ejecucion = ANY(:t)) AND estado IN ('terminado', 'error') AND NOT rutas_borradas
    """), {"t": list(tanda)}).scalars().all()
    n = 0
    if viejas:
        # un solo DELETE con todas las generaciones: los hijos se borran en la misma sentencia, así que
        # «ON DELETE SET NULL» no tiene nada que actualizar (soltar antes los padres era 2× más lento)
        n = con.execute(text("""
            DELETE FROM individuo
            WHERE id_generacion IN (SELECT id_generacion FROM generacion WHERE id_ejecucion = ANY(:v))
        """), {"v": viejas}).rowcount
        con.execute(text("UPDATE ejecucion_ag SET rutas_borradas = true WHERE id_ejecucion = ANY(:v)"), {"v": viejas})
    ops = con.execute(text("""
        UPDATE generacion g SET operaciones = NULL
        FROM ejecucion_ag e
        WHERE g.id_ejecucion = e.id_ejecucion AND e.rutas_borradas AND g.operaciones IS NOT NULL
          AND NOT (e.id_ejecucion = ANY(:t))
    """), {"t": list(tanda)}).rowcount
    return {"agentes": len(viejas), "individuos": n, "generaciones": ops}


def _vacuum(motor) -> None:
    """VACUUM (sin FULL, no bloquea lecturas): el espacio liberado se reutiliza en la tanda nueva
    en lugar de crecer el archivo. Las pruebas usan un motor sin connect(): ahí no se hace."""
    if not hasattr(motor, "connect"):
        return
    try:
        with motor.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.execute(text("VACUUM individuo, generacion"))
    except Exception:
        log.warning("No se pudo hacer VACUUM después de liberar las tandas anteriores", exc_info=True)


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
        "parametros": {**{k: e[k] for k in PARAMETROS}, "medir": e["medir"]},
        # etapa 7: lo que se pidió (medir), con qué se optimizó la ruta guardada y la comparación
        "medir": e["medir"], "metrica": e["metrica"], "distancia_recta_m": e["distancia_recta_m"],
        "comparacion": e["comparacion"],
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
        raise NoEncontrado("El paso a paso de este agente se borró porque se generó una tanda de agentes más nueva "
                           "(solo la última tanda conserva el detalle). Vuelve a Analizar y genera los agentes "
                           "de nuevo: con la misma semilla el resultado es idéntico.")
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
            "metrica": e["metrica"], "distancia_recta_m": e["distancia_recta_m"],
        },
    }


def distancias(con, id_ejecucion: int) -> dict:
    """GET /api/agentes/{id}/distancias (etapa 7): la matriz con la que se optimizó la ruta ganadora.

    Para que la vista Rutas muestre los metros de cada tramo con la misma vara que el genético.
    ids en el orden de las filas (por etiqueta); distancias_m[i][j] = de ids[i] a ids[j]
    (con la métrica «calles», ida y vuelta pueden ser distintas).
    """
    from app.servicios import matriz_calles as M
    e = _ejecucion(con, id_ejecucion)
    _terminado(e)
    ids, D, _ = datos_grafo(con, e["id_grafo"])
    metrica = e["metrica"] or "recta"
    if metrica != "recta":
        id_analisis = con.execute(text("""
            SELECT p.id_analisis FROM grafo g JOIN particion_louvain p USING (id_particion) WHERE g.id_grafo = :g
        """), {"g": e["id_grafo"]}).scalar_one()
        m = M.obtener(con, id_analisis, pedir=False)
        if m is None:
            raise NoEncontrado("La matriz por calles de este análisis ya no está guardada. "
                               "Vuelve a generar los agentes.")
        D = m.submatrices(ids, recta=D)[metrica]
    return {"id_ejecucion": e["id_ejecucion"], "metrica": metrica, "ids": ids,
            "distancias_m": [[round(float(x), 1) for x in fila] for fila in D]}


def registrar_simulacion(con, id_ejecucion: int, distancia_total: float | None, duracion_s: float | None) -> dict:
    """POST /api/simulaciones (§4.17). No hace commit."""
    _ejecucion(con, id_ejecucion)
    fila = con.execute(text("""
        INSERT INTO simulacion (id_ejecucion, distancia_total, duracion_s) VALUES (:e, :d, :t)
        RETURNING id_simulacion, id_ejecucion, fecha, distancia_total, duracion_s
    """), {"e": id_ejecucion, "d": distancia_total, "t": duracion_s}).mappings().one()
    return {**fila, "fecha": fila["fecha"].isoformat()}
