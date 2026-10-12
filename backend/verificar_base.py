"""
Paso 5 · Verificación integral de la base de datos.

Ejecuta cinco pruebas con datos reales de la FGJ y datos de prueba:
  1. El trigger de ubicación (dentro_gam, colonia, geometría calculada)
  2. Las reglas que protegerán la ingesta (duplicados, dominios, llaves)
  3. El ciclo completo: análisis, cambio de vigente, partición, agente y cascadas
  4. Las consultas GeoJSON que usará la API de mapas
  5. El rendimiento de una carga de 10,000 puntos

TODO ocurre dentro de una transacción que se DESHACE al final:
la base queda exactamente como estaba.

Genera database/verificacion/muestra.geojson para verlo en https://geojson.io

Ejecutar desde la carpeta backend, con el entorno virtual activo:
    python verificar_base.py
"""
import hashlib
import json
import time
import unicodedata
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from db import get_engine

RAIZ = Path(__file__).resolve().parent.parent
PARQUET_FGJ = RAIZ / "PI_AnalisisPreviodeGAM" / "victimas_cdmx_limpio.parquet"
SALIDA = RAIZ / "database" / "verificacion" / "muestra.geojson"
NOMBRE_GAM = "Gustavo A. Madero"
N_RENDIMIENTO = 10_000

resultados = []  # (prueba, ok)


# ======================================================================
# Utilidades
# ======================================================================
def titulo(t: str):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


def check(nombre: str, ok: bool, detalle: str = ""):
    resultados.append((nombre, ok))
    marca = "[OK]   " if ok else "[FALLA]"
    print(f"{marca} {nombre}" + (f"  ->  {detalle}" if detalle else ""))


def normalizar(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def huella(*partes) -> str:
    return hashlib.sha256("|".join(map(str, partes)).encode()).hexdigest()


def debe_fallar(con, nombre: str, sql: str, params: dict, sqlstate: str, motivo: str):
    """Ejecuta un INSERT que la base debe rechazar, dentro de un savepoint."""
    try:
        with con.begin_nested():
            con.execute(text(sql), params)
        check(nombre, False, "la base lo aceptó y debía rechazarlo")
    except DBAPIError as e:
        codigo = getattr(e.orig, "sqlstate", None)
        check(nombre, codigo == sqlstate, f"rechazado ({motivo})" if codigo == sqlstate
              else f"rechazado con otro código: {codigo}")


def fila_punto(r, id_carga: int, id_delito: int, hash_registro: str) -> dict:
    """Convierte un registro de la FGJ en parámetros para punto_delictivo."""
    edad = None if pd.isna(r.edad) else int(r.edad)
    return {
        "id_carga": id_carga, "id_delito": id_delito,
        "colonia_texto": None if pd.isna(r.colonia_catalogo) else r.colonia_catalogo,
        "fecha_hecho": r.fecha_hecho.date(),
        "hora_hecho": None if pd.isna(r.hora_hecho) else r.hora_hecho,
        "sexo": None if pd.isna(r.sexo) else r.sexo,
        "edad": edad,
        "lat": float(r.latitud), "lon": float(r.longitud),
        "hash": hash_registro,
    }


INSERT_PUNTO = """
    INSERT INTO punto_delictivo (id_carga, id_delito, colonia_texto, fecha_hecho,
                                 hora_hecho, sexo, edad, latitud, longitud, hash_registro)
    VALUES (:id_carga, :id_delito, :colonia_texto, :fecha_hecho,
            :hora_hecho, :sexo, :edad, :lat, :lon, :hash)
"""


# ======================================================================
# Datos de la FGJ
# ======================================================================
fgj = pd.read_parquet(PARQUET_FGJ, columns=[
    "delito", "alcaldia_catalogo", "colonia_catalogo", "latitud", "longitud",
    "fecha_hecho", "hora_hecho", "sexo", "edad"])
fgj = fgj.dropna(subset=["latitud", "longitud", "fecha_hecho"])
gam_fgj = fgj[(fgj["alcaldia_catalogo"] == NOMBRE_GAM) & fgj["colonia_catalogo"].notna()]

engine = get_engine()
con = engine.connect()
trans = con.begin()

try:
    delitos = dict(con.execute(text("SELECT nombre, id_delito FROM cat_delito")).all())
    id_carga = con.execute(text("""
        INSERT INTO carga_dataset (nombre_archivo, hash_archivo, filas_leidas, estado)
        VALUES ('verificacion.xlsx', :h, 0, 'procesando') RETURNING id_carga
    """), {"h": huella("verificacion")}).scalar_one()

    # ==================================================================
    titulo("1 · TRIGGER DE UBICACIÓN")
    # a) Un registro real de GAM con colonia
    ra = gam_fgj.iloc[0]
    # b) Un punto real dentro de GAM pero en una zona sin colonia
    lon_b, lat_b = con.execute(text("""
        SELECT ST_X(p), ST_Y(p) FROM (
          SELECT ST_PointOnSurface(ST_Difference(a.geom, ST_Union(c.geom))) AS p
          FROM alcaldia a JOIN colonia c USING (id_alcaldia) GROUP BY a.geom) s
    """)).one()
    # c) Un registro real claramente fuera de GAM (colonia Centro, Cuauhtémoc)
    cuauh = fgj[fgj["alcaldia_catalogo"] == "Cuauhtémoc"]
    fuera = cuauh[cuauh["colonia_catalogo"].map(normalizar) == "CENTRO"]
    rc = (fuera if len(fuera) else cuauh).iloc[0]

    ids = {}
    for clave, r in (("a", ra), ("c", rc)):
        p = fila_punto(r, id_carga, delitos[r.delito], huella("prueba", clave))
        ids[clave] = con.execute(text(INSERT_PUNTO + " RETURNING id_punto"), p).scalar_one()
    pb = fila_punto(ra, id_carga, delitos[ra.delito], huella("prueba", "b"))
    pb.update(lat=lat_b, lon=lon_b, colonia_texto=None)
    ids["b"] = con.execute(text(INSERT_PUNTO + " RETURNING id_punto"), pb).scalar_one()

    puntos = {k: con.execute(text("""
        SELECT p.dentro_gam, c.nombre, ST_X(p.geom) = p.longitud AND ST_Y(p.geom) = p.latitud
        FROM punto_delictivo p LEFT JOIN colonia c USING (id_colonia) WHERE id_punto = :i
    """), {"i": i}).one() for k, i in ids.items()}

    check("Punto de GAM: dentro_gam = true", puntos["a"][0] is True)
    check("Punto de GAM: colonia por ubicación = colonia de la FGJ",
          normalizar(puntos["a"][1]) == normalizar(ra.colonia_catalogo),
          f"{puntos['a'][1]} / FGJ: {ra.colonia_catalogo}")
    check("Punto en zona sin colonia: dentro_gam = true y colonia vacía",
          puntos["b"][0] is True and puntos["b"][1] is None)
    check("Punto de Cuauhtémoc: dentro_gam = false", puntos["c"][0] is False,
          f"colonia FGJ: {rc.colonia_catalogo}")
    check("Geometría calculada a partir de latitud y longitud",
          all(v[2] for v in puntos.values()))

    # ==================================================================
    titulo("2 · REGLAS QUE PROTEGEN LA INGESTA")
    base = fila_punto(ra, id_carga, delitos[ra.delito], huella("prueba", "a"))
    debe_fallar(con, "Registro duplicado", INSERT_PUNTO, base, "23505", "hash_registro único")
    debe_fallar(con, "Edad de 150 años", INSERT_PUNTO,
                {**base, "hash": huella("x1"), "edad": 150}, "23514", "CHECK edad 0-100")
    debe_fallar(con, "Delito que no existe en el catálogo", INSERT_PUNTO,
                {**base, "hash": huella("x2"), "id_delito": -1}, "23503", "llave foránea")
    debe_fallar(con, "Coordenadas imposibles", INSERT_PUNTO,
                {**base, "hash": huella("x3"), "lat": 120.0}, "23514", "CHECK latitud")

    # ==================================================================
    titulo("3 · CICLO COMPLETO")
    # Análisis 1 con dos hotspots y la membresía de los puntos
    a1 = con.execute(text("""
        INSERT INTO analisis_hdbscan (id_carga_origen, min_cluster_size, n_puntos,
                                      n_hotspots, n_ruido, vigente)
        VALUES (:c, 15, 2, 2, 0, true) RETURNING id_analisis"""), {"c": id_carga}).scalar_one()
    con.execute(text("INSERT INTO analisis_carga VALUES (:a, :c)"), {"a": a1, "c": id_carga})
    hot = {}
    for et, (lat, lon) in enumerate(((float(ra.latitud), float(ra.longitud)), (lat_b, lon_b))):
        hot[et] = con.execute(text("""
            INSERT INTO hotspot (id_analisis, etiqueta, codigo, lat_centroide, lon_centroide,
                                 geom_area, n_puntos, indice_gravedad)
            VALUES (:a, :e, :cod, :lat, :lon,
                    ST_Buffer(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 200)::geometry,
                    1, 2.5)
            RETURNING id_hotspot"""),
            {"a": a1, "e": et, "cod": f"H-{et:02d}", "lat": lat, "lon": lon}).scalar_one()
    con.execute(text("INSERT INTO membresia_hotspot VALUES (:a, :p, :h, 0.95), (:a, :q, :g, 0.80)"),
                {"a": a1, "p": ids["a"], "h": hot[0], "q": ids["b"], "g": hot[1]})
    check("Análisis con 2 hotspots y membresía", True, f"análisis {a1}")

    # Cambio de vigente: el patrón que usará el backend en cada carga
    debe_fallar(con, "Segundo análisis vigente sin desmarcar el anterior", """
        INSERT INTO analisis_hdbscan (id_carga_origen, min_cluster_size, n_puntos,
                                      n_hotspots, n_ruido, vigente)
        VALUES (:c, 15, 2, 1, 1, true)""", {"c": id_carga}, "23505", "un solo vigente")
    con.execute(text("UPDATE analisis_hdbscan SET vigente = false WHERE id_analisis = :a"), {"a": a1})
    a2 = con.execute(text("""
        INSERT INTO analisis_hdbscan (id_carga_origen, id_analisis_previo, min_cluster_size,
                                      n_puntos, n_hotspots, n_ruido, vigente)
        VALUES (:c, :prev, 15, 2, 1, 1, true) RETURNING id_analisis"""),
        {"c": id_carga, "prev": a1}).scalar_one()
    h2 = con.execute(text("""
        INSERT INTO hotspot (id_analisis, etiqueta, codigo, lat_centroide, lon_centroide, n_puntos)
        VALUES (:a, 0, 'H-00', :lat, :lon, 2) RETURNING id_hotspot"""),
        {"a": a2, "lat": float(ra.latitud), "lon": float(ra.longitud)}).scalar_one()
    vigentes = con.execute(text("SELECT array_agg(id_analisis) FROM analisis_hdbscan WHERE vigente")).scalar_one()
    check("Cambio de vigente: desmarcar el anterior y marcar el nuevo", vigentes == [a2],
          f"vigente: {vigentes}")

    # Partición, grafos, nodos y aristas sobre el análisis 1
    debe_fallar(con, "Partición con N = 6", """
        INSERT INTO particion_louvain (id_analisis, n_grafos) VALUES (:a, 6)""",
        {"a": a1}, "23514", "CHECK N de 1 a 5")
    pa = con.execute(text("""
        INSERT INTO particion_louvain (id_analisis, n_grafos, resolucion, vigente)
        VALUES (:a, 2, 1.0, true) RETURNING id_particion"""), {"a": a1}).scalar_one()
    g1, g2 = [con.execute(text("""
        INSERT INTO grafo (id_particion, numero, n_nodos, n_aristas, color)
        VALUES (:p, :n, 1, 1, :col) RETURNING id_grafo"""),
        {"p": pa, "n": n, "col": col}).scalar_one() for n, col in ((1, "#2F6FD0"), (2, "#C2410C"))]
    con.execute(text("INSERT INTO nodo_grafo VALUES (:p, :h0, :g1), (:p, :h1, :g2)"),
                {"p": pa, "h0": hot[0], "h1": hot[1], "g1": g1, "g2": g2})
    debe_fallar(con, "Hotspot en dos grafos de la misma partición",
                "INSERT INTO nodo_grafo VALUES (:p, :h, :g)",
                {"p": pa, "h": hot[0], "g": g2}, "23505", "PK (partición, hotspot)")
    distancia = con.execute(text("""
        SELECT ST_Distance(a.geom::geography, b.geom::geography)
        FROM hotspot a, hotspot b WHERE a.id_hotspot = :x AND b.id_hotspot = :y"""),
        {"x": hot[0], "y": hot[1]}).scalar_one()
    con.execute(text("INSERT INTO arista VALUES (:g, :x, :y, :d), (:g, :y, :x, :d)"),
                {"g": g1, "x": hot[0], "y": hot[1], "d": distancia})
    debe_fallar(con, "Arista de un hotspot consigo mismo",
                "INSERT INTO arista VALUES (:g, :x, :x, 0)",
                {"g": g1, "x": hot[0]}, "23514", "CHECK origen <> destino")

    # Agente: ejecución, generación, individuos con padres y simulación
    ej = con.execute(text("""
        INSERT INTO ejecucion_ag (id_grafo, tam_poblacion, n_generaciones, tam_torneo,
                                  prob_cruce, prob_mutacion, op_cruce, op_mutacion, semilla)
        VALUES (:g, 50, 200, 3, 0.9, 0.1, 'OX', 'swap', 42) RETURNING id_ejecucion"""),
        {"g": g1}).scalar_one()
    gen = con.execute(text("""
        INSERT INTO generacion (id_ejecucion, numero, mejor_fitness, fitness_promedio,
                                peor_fitness, mejor_permutacion)
        VALUES (:e, 0, :d, :d, :d, '[0, 1]') RETURNING id_generacion"""),
        {"e": ej, "d": 2 * distancia}).scalar_one()
    p1 = con.execute(text("""
        INSERT INTO individuo (id_generacion, posicion, permutacion, distancia, origen)
        VALUES (:g, 0, '[0, 1]', :d, 'aleatorio') RETURNING id_individuo"""),
        {"g": gen, "d": 2 * distancia}).scalar_one()
    con.execute(text("""
        INSERT INTO individuo (id_generacion, posicion, permutacion, distancia, origen, id_padre_1, id_padre_2)
        VALUES (:g, 1, '[1, 0]', :d, 'cruce', :p, :p)"""), {"g": gen, "d": 2 * distancia, "p": p1})
    con.execute(text("UPDATE ejecucion_ag SET ruta_optima = '[0, 1]', mejor_distancia = :d, "
                     "estado = 'terminado' WHERE id_ejecucion = :e"), {"d": 2 * distancia, "e": ej})
    con.execute(text("INSERT INTO simulacion (id_ejecucion, distancia_total, duracion_s) "
                     "VALUES (:e, :d, 12.5)"), {"e": ej, "d": 2 * distancia})
    check("Partición, grafos, agente, generación, individuos y simulación", True,
          f"distancia entre hotspots: {distancia:,.0f} m")

    # Cascada: borrar el análisis 1 elimina solo lo suyo
    def conteos():
        return con.execute(text("""
            SELECT (SELECT count(*) FROM hotspot WHERE id_analisis = :a1),
                   (SELECT count(*) FROM particion_louvain WHERE id_analisis = :a1),
                   (SELECT count(*) FROM grafo WHERE id_particion = :pa),
                   (SELECT count(*) FROM individuo WHERE id_generacion = :gen),
                   (SELECT count(*) FROM simulacion WHERE id_ejecucion = :ej),
                   (SELECT count(*) FROM hotspot WHERE id_analisis = :a2),
                   (SELECT count(*) FROM punto_delictivo WHERE id_carga = :c)
        """), {"a1": a1, "a2": a2, "pa": pa, "gen": gen, "ej": ej, "c": id_carga}).one()
    antes = conteos()
    con.execute(text("DELETE FROM analisis_hdbscan WHERE id_analisis = :a"), {"a": a1})
    despues = conteos()
    check("Cascada: se borran hotspots, partición, grafos, individuos y simulación del análisis 1",
          tuple(despues[:5]) == (0, 0, 0, 0, 0), f"antes {tuple(antes[:5])} -> después {tuple(despues[:5])}")
    check("Cascada: el análisis 2 y los puntos delictivos se conservan",
          despues[5] == antes[5] == 1 and despues[6] == antes[6] == 3,
          f"hotspots del análisis 2: {despues[5]}, puntos: {despues[6]}")

    # ==================================================================
    titulo("4 · CONSULTAS GEOJSON PARA LA API DE MAPAS")
    consultas = {
        "Contorno de GAM": ("""
            SELECT json_build_object('type', 'FeatureCollection', 'features',
                   json_agg(ST_AsGeoJSON(t.*)::json))
            FROM (SELECT nombre, ST_SimplifyPreserveTopology(geom, 0.0001) AS geom FROM alcaldia) t""",
            {"Polygon", "MultiPolygon"}),
        "Colonias de GAM": ("""
            SELECT json_build_object('type', 'FeatureCollection', 'features',
                   json_agg(ST_AsGeoJSON(t.*)::json))
            FROM (SELECT id_colonia, nombre, clave_oficial, geom FROM colonia) t""",
            {"Polygon", "MultiPolygon"}),
        "Puntos con delito y gravedad": ("""
            SELECT json_build_object('type', 'FeatureCollection', 'features',
                   json_agg(ST_AsGeoJSON(t.*)::json))
            FROM (SELECT p.id_punto, d.nombre AS delito, d.gravedad, p.dentro_gam,
                         c.nombre AS colonia, p.geom
                  FROM punto_delictivo p JOIN cat_delito d USING (id_delito)
                  LEFT JOIN colonia c USING (id_colonia)
                  WHERE p.id_carga = :c) t""",
            {"Point"}),
        "Hotspots del análisis vigente": ("""
            SELECT json_build_object('type', 'FeatureCollection', 'features',
                   json_agg(ST_AsGeoJSON(t.*)::json))
            FROM (SELECT h.codigo, h.n_puntos, h.geom
                  FROM hotspot h JOIN analisis_hdbscan a USING (id_analisis)
                  WHERE a.vigente) t""",
            {"Point"}),
    }
    capas = {}
    for nombre, (sql, tipos) in consultas.items():
        fc = con.execute(text(sql), {"c": id_carga}).scalar_one()
        features = fc.get("features") or []
        geoms = {f["geometry"]["type"] for f in features}
        ok = fc["type"] == "FeatureCollection" and len(features) > 0 and geoms <= tipos
        check(f"GeoJSON · {nombre}", ok, f"{len(features)} elementos, tipo {sorted(geoms)}")
        capas[nombre] = features

    # Archivo para ver en geojson.io: contorno, puntos de prueba y áreas de hotspots
    estilo = {"a": ("#2F6FD0", "Dentro de GAM, con colonia"),
              "b": ("#15803D", "Dentro de GAM, sin colonia"),
              "c": ("#B91C1C", "Fuera de GAM (Centro, Cuauhtémoc)")}
    muestra = []
    for f in capas["Contorno de GAM"]:
        f["properties"].update({"stroke": "#555555", "fill-opacity": 0.05, "capa": "Límite de GAM"})
        muestra.append(f)
    for clave, i in ids.items():
        geo, dentro, colonia = con.execute(text("""
            SELECT ST_AsGeoJSON(p.geom)::json, p.dentro_gam, c.nombre
            FROM punto_delictivo p LEFT JOIN colonia c USING (id_colonia) WHERE id_punto = :i"""),
            {"i": i}).one()
        color, caso = estilo[clave]
        muestra.append({"type": "Feature", "geometry": geo, "properties": {
            "caso": caso, "dentro_gam": dentro, "colonia": colonia,
            "marker-color": color, "marker-size": "large"}})
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps({"type": "FeatureCollection", "features": muestra},
                                 ensure_ascii=False), encoding="utf-8")
    print(f"Archivo para geojson.io: {SALIDA}")

    # ==================================================================
    titulo(f"5 · RENDIMIENTO: CARGA DE {N_RENDIMIENTO:,} PUNTOS REALES")
    muestra_perf = gam_fgj.sample(min(N_RENDIMIENTO, len(gam_fgj)), random_state=1)
    filas = [fila_punto(r, id_carga, delitos[r.delito], huella("perf", i))
             for i, r in enumerate(muestra_perf.itertuples())]
    t0 = time.perf_counter()
    con.execute(text(INSERT_PUNTO), filas)
    segundos = time.perf_counter() - t0
    por_seg = len(filas) / segundos
    check(f"Inserción de {len(filas):,} puntos con trigger", True,
          f"{segundos:.1f} s ({por_seg:,.0f} puntos/s); 63,000 puntos ≈ {63_000 / por_seg:.0f} s")

    dentro_pct, con_col = con.execute(text("""
        SELECT avg(dentro_gam::int) * 100, avg((id_colonia IS NOT NULL)::int) * 100
        FROM punto_delictivo WHERE hash_registro = ANY(:h)"""),
        {"h": [f["hash"] for f in filas]}).one()
    check("Puntos de la muestra dentro de GAM", dentro_pct > 99,
          f"{dentro_pct:.1f}% dentro, {con_col:.1f}% con colonia")

    con.execute(text("ANALYZE punto_delictivo"))
    plan = "\n".join(r[0] for r in con.execute(text("""
        EXPLAIN SELECT count(*) FROM punto_delictivo
        WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 0.005)"""),
        {"lon": float(ra.longitud), "lat": float(ra.latitud)}))
    check("Búsqueda por cercanía usa el índice espacial de puntos", "ix_punto_geom" in plan,
          "Index Scan con ix_punto_geom" if "ix_punto_geom" in plan else plan.splitlines()[0])

finally:
    trans.rollback()  # la base queda exactamente como estaba
    con.close()

# ======================================================================
titulo("RESUMEN")
fallas = [n for n, ok in resultados if not ok]
print(f"{len(resultados) - len(fallas)} de {len(resultados)} pruebas aprobadas.")
for n in fallas:
    print(f"  Falló: {n}")
print("Todos los cambios se deshicieron: la base quedó como estaba.")