"""Guarda un análisis HDBSCAN en la base (etapa 3, pieza 3.4).

clustering.py CALCULA; este módulo GUARDA. Todo se escribe en una sola transacción:

  1. analisis_hdbscan   una fila con los criterios y las cifras del análisis
  2. hotspot            una fila por hotspot (con su área como polígono)
  3. membresia_hotspot  una fila por punto analizado: a qué hotspot cayó (NULL = ruido)
  4. analisis_carga     qué cargas aportaron puntos a este análisis
  5. resultado_json     el análisis completo en JSON (los hotspots como GeoJSON)
  6. vigente            el análisis anterior deja de ser vigente y este pasa a serlo

Si algo falla a la mitad, la transacción se deshace y el análisis anterior sigue vigente.
Nada se borra: los análisis anteriores se quedan en la base como historial.
"""
import json

from sqlalchemy import text

from app.servicios import clustering as C


# ------------------------------------------------------------------ consultas
def analisis_vigente(con) -> int | None:
    """id del análisis vigente, o None si todavía no hay ninguno."""
    return con.execute(text(
        "SELECT id_analisis FROM analisis_hdbscan WHERE vigente FOR UPDATE"
    )).scalar()


def ultima_carga_completada(con) -> int | None:
    """La carga completada más reciente (origen del primer análisis, pieza 3.6)."""
    return con.execute(text(
        "SELECT max(id_carga) FROM carga_dataset WHERE estado = 'completado'"
    )).scalar()


def esta_al_dia(con, parametros: C.Parametros = C.PARAMETROS) -> bool:
    """True si NO hace falta un análisis nuevo.

    Pasa cuando el análisis vigente ya usa todos los puntos analizables con los mismos
    criterios (p. ej. una carga repetida o un consolidado que no aportó puntos nuevos),
    o cuando todavía no hay ningún punto que analizar. Como los puntos nunca se borran,
    si el conteo es el mismo, los puntos son los mismos.
    """
    n = C.contar_puntos(con, parametros)
    if n == 0:
        return True
    vigente = con.execute(text("""
        SELECT n_puntos, min_cluster_size, min_samples, peso_minimo, fecha_desde
        FROM analisis_hdbscan WHERE vigente
    """)).first()
    return vigente is not None and tuple(vigente) == (
        n, parametros.min_cluster_size, parametros.min_samples,
        parametros.peso_minimo, parametros.fecha_desde)


CONSULTA_HOTSPOTS = text("""
    SELECT id_hotspot, etiqueta, codigo, lon_centroide, lat_centroide, n_puntos,
           radio_m, delito_predominante, indice_gravedad, colonia,
           ST_AsGeoJSON(geom_area, 6) AS area
    FROM hotspot
    WHERE id_analisis = :id
    ORDER BY etiqueta
""")


def hotspots_geojson(con, id_analisis: int) -> dict:
    """Los hotspots de un análisis como FeatureCollection (formato de README_INTEGRACION §4.9).

    La geometría es el área del hotspot; properties.centroide es el medoide [lon, lat].
    La usa resultado_json y la usará el endpoint GET /api/analisis/vigente/hotspots.
    """
    features = []
    for h in con.execute(CONSULTA_HOTSPOTS, {"id": id_analisis}).mappings():
        features.append({
            "type": "Feature",
            "geometry": json.loads(h["area"]),
            "properties": {
                "id_hotspot": int(h["id_hotspot"]),
                "etiqueta": h["etiqueta"],
                "codigo": h["codigo"],
                "centroide": [h["lon_centroide"], h["lat_centroide"]],
                "n_puntos": h["n_puntos"],
                "indice_gravedad": h["indice_gravedad"],
                "radio_m": h["radio_m"],
                "delito_predominante": h["delito_predominante"],
                "colonia": h["colonia"],
            },
        })
    return {"type": "FeatureCollection", "features": features}


# ------------------------------------------------------------------ escritura
INSERTAR_ANALISIS = text("""
    INSERT INTO analisis_hdbscan
        (id_carga_origen, id_analisis_previo, min_cluster_size, min_samples, metrica,
         n_puntos, n_hotspots, n_ruido, duracion_s, vigente,
         peso_minimo, fecha_desde, min_cluster_size_base, hotspots_minimos)
    VALUES
        (:origen, :previo, :mcs, :ms, :metrica,
         :n_puntos, :n_hotspots, :n_ruido, :duracion, false,
         :peso_minimo, :fecha_desde, :mcs, NULL)
    RETURNING id_analisis, fecha
""")

# El área es el polígono que calculó clustering.py. Si no se pudo calcular (menos de
# 3 coordenadas distintas, p. ej. muchas víctimas registradas en el mismo punto), se usa
# un círculo de radio_m alrededor del medoide, para que ningún hotspot quede sin área.
INSERTAR_HOTSPOT = text("""
    INSERT INTO hotspot
        (id_analisis, etiqueta, codigo, lat_centroide, lon_centroide, geom_area,
         n_puntos, radio_m, delito_predominante, indice_gravedad, colonia)
    VALUES
        (:id, :etiqueta, :codigo, :lat, :lon,
         coalesce(
             ST_SetSRID(ST_GeomFromGeoJSON(CAST(:area AS text)), 4326),
             ST_Buffer(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radio)::geometry
         ),
         :n, :radio, :delito, :gravedad, :colonia)
    RETURNING id_hotspot
""")

INSERTAR_CARGAS = text("""
    INSERT INTO analisis_carga (id_analisis, id_carga)
    SELECT DISTINCT CAST(:id AS bigint), p.id_carga
    FROM membresia_hotspot m
    JOIN punto_delictivo p USING (id_punto)
    WHERE m.id_analisis = :id
    UNION
    SELECT CAST(:id AS bigint), CAST(:origen AS bigint)
""")


def _copiar_membresia(con, id_analisis: int, r: C.Resultado, id_de_etiqueta: dict) -> None:
    """Escribe ~54 mil filas de membresía con COPY (mucho más rápido que INSERT fila por fila).

    Usa la misma conexión, así que el COPY queda dentro de la misma transacción.
    """
    m = r.membresia
    filas = zip(m.id_punto.tolist(), m.etiqueta.tolist(), m.probabilidad.tolist())
    crudo = con.connection.driver_connection          # la conexión de psycopg debajo de SQLAlchemy
    with crudo.cursor() as cur, cur.copy(
        "COPY membresia_hotspot (id_analisis, id_punto, id_hotspot, probabilidad) FROM STDIN"
    ) as copia:
        for id_punto, etiqueta, prob in filas:
            ruido = etiqueta is None or etiqueta != etiqueta          # None o NaN
            copia.write_row((id_analisis, int(id_punto),
                             None if ruido else id_de_etiqueta[int(etiqueta)],
                             float(prob)))


def guardar(con, r: C.Resultado, id_carga_origen: int) -> int:
    """Guarda el resultado de clustering.ejecutar() y lo deja como el análisis vigente.

    No hace commit: quien llama abre la transacción (with engine.begin() as con).
    Devuelve el id_analisis nuevo.
    """
    p = r.parametros
    previo = analisis_vigente(con)

    # 1. el análisis
    id_analisis, fecha = con.execute(INSERTAR_ANALISIS, {
        "origen": id_carga_origen, "previo": previo,
        "mcs": p.min_cluster_size, "ms": p.min_samples, "metrica": C.METRICA,
        "n_puntos": r.n_puntos, "n_hotspots": r.n_hotspots, "n_ruido": r.n_ruido,
        "duracion": r.duracion_s, "peso_minimo": p.peso_minimo, "fecha_desde": p.fecha_desde,
    }).one()

    # 2. los hotspots
    id_de_etiqueta = {}
    for h in r.hotspots:
        id_de_etiqueta[h["etiqueta"]] = con.execute(INSERTAR_HOTSPOT, {
            "id": id_analisis, "etiqueta": h["etiqueta"], "codigo": h["codigo"],
            "lat": h["lat_centroide"], "lon": h["lon_centroide"],
            "area": json.dumps(h["area"]) if h["area"] else None,
            "n": h["n_puntos"], "radio": h["radio_m"],
            "delito": h["delito_predominante"][:255], "gravedad": h["indice_gravedad"],
            "colonia": h["colonia"][:150] if h["colonia"] else None,
        }).scalar_one()

    # 3. la membresía de cada punto  ·  4. las cargas que aportaron puntos
    _copiar_membresia(con, id_analisis, r, id_de_etiqueta)
    con.execute(INSERTAR_CARGAS, {"id": id_analisis, "origen": id_carga_origen})

    # 5. el JSON del análisis
    geojson = hotspots_geojson(con, id_analisis)
    extras = {h["etiqueta"]: h for h in r.hotspots}
    for f in geojson["features"]:                       # datos que no tienen columna propia
        h = extras[f["properties"]["etiqueta"]]
        f["properties"].update(pct_delito=h["pct_delito"], confianza=h["confianza"],
                               densidad=h["densidad"])
    resultado = {
        "id_analisis": id_analisis,
        "fecha": fecha.isoformat(),
        "id_analisis_previo": previo,
        "id_carga_origen": id_carga_origen,
        "parametros": {
            "min_cluster_size": p.min_cluster_size,
            "min_samples": p.min_samples,
            "cluster_selection_method": "eom",
            "metrica": C.METRICA,
            "peso_minimo": p.peso_minimo,
            "fecha_desde": p.fecha_desde.isoformat() if p.fecha_desde else None,
        },
        "n_puntos": r.n_puntos,
        "n_hotspots": r.n_hotspots,
        "n_ruido": r.n_ruido,
        "pct_ruido": r.pct_ruido,
        "duracion_s": r.duracion_s,
        "hotspots": geojson,
    }

    # 6. cambio de vigente: primero se apaga el anterior (el índice único no permite dos)
    con.execute(text("UPDATE analisis_hdbscan SET vigente = false WHERE vigente"))
    con.execute(text("""
        UPDATE analisis_hdbscan
        SET vigente = true, resultado_json = CAST(:json AS jsonb)
        WHERE id_analisis = :id
    """), {"id": id_analisis, "json": json.dumps(resultado, ensure_ascii=False)})
    return id_analisis


# ------------------------------------------------------------------ todo junto
def nuevo_analisis(engine, id_carga_origen: int | None = None,
                   parametros: C.Parametros = C.PARAMETROS,
                   al_avanzar=None) -> tuple[int, C.Resultado]:
    """Lee los puntos, corre HDBSCAN y guarda el resultado como análisis vigente.

    HDBSCAN (~50 s) corre FUERA de la transacción; solo la escritura va dentro,
    así la base no queda bloqueada mientras se calcula.
    al_avanzar(fraccion) informa el avance (0 a 1), igual que en insercion.py.
    """
    avanzar = al_avanzar or (lambda fraccion: None)
    with engine.connect() as con:
        puntos = C.leer_puntos(con, parametros)
    avanzar(0.1)
    r = C.ejecutar(puntos, parametros)
    avanzar(0.9)
    with engine.begin() as con:                         # commit al salir sin error
        if id_carga_origen is None:
            id_carga_origen = ultima_carga_completada(con)
        if id_carga_origen is None:
            raise ValueError("No hay ninguna carga completada: primero carga un dataset.")
        id_analisis = guardar(con, r, id_carga_origen)
    return id_analisis, r