import sys
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd
from sqlalchemy import text

from db import get_engine

# ------------------------------------------------------------------ rutas
RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "database" / "fuentes"
ARCHIVO_ALCALDIAS = FUENTES / "INEGI_alcaldias.json"
ARCHIVO_COLONIAS = FUENTES / "INEGI_colonias.json"
CATALOGO_DELITOS = RAIZ / "PI_AnalisisPreviodeGAM" / "catalogo_delitos.csv"
PARQUET_FGJ = RAIZ / "PI_AnalisisPreviodeGAM" / "victimas_cdmx_limpio.parquet"

# ------------------------------------------------------------- constantes
NOMBRE_GAM = "Gustavo A. Madero"  # debe coincidir con el trigger fn_punto_ubicacion
CVEGEO_GAM = "09005"              # clave INEGI: entidad 09, municipio 005
CVE_ALC_GAM = "005"
PESOS = {"Crítica": 4, "Alta": 3, "Media": 2, "Baja": 1, "No aplica": 0}
GEOM_SQL = "ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_GeomFromText(:wkt, 4326)), 3))"


def normalizar(s) -> str:
    """Mayúsculas, sin acentos y sin espacios dobles, para comparar nombres."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def titulo(t: str):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


def leer_geojson(ruta: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(ruta)
    return gdf.to_crs(4326) if gdf.crs and gdf.crs.to_epsg() != 4326 else gdf


# ======================================================================
# CARGAS
# ======================================================================
def cargar_alcaldia(con) -> int:
    gdf = leer_geojson(ARCHIVO_ALCALDIAS)
    gam = gdf[gdf["CVEGEO"] == CVEGEO_GAM]
    if len(gam) != 1:
        sys.exit(f"Se esperaba 1 polígono con CVEGEO={CVEGEO_GAM} y hay {len(gam)}")

    id_alcaldia = con.execute(text(f"""
        INSERT INTO alcaldia (nombre, geom)
        VALUES (:nombre, {GEOM_SQL})
        ON CONFLICT (nombre) DO UPDATE SET geom = EXCLUDED.geom
        RETURNING id_alcaldia
    """), {"nombre": NOMBRE_GAM, "wkt": gam.geometry.iloc[0].wkt}).scalar_one()
    print(f"alcaldia: '{NOMBRE_GAM}' cargada (id {id_alcaldia})")
    return id_alcaldia


def cargar_colonias(con, id_alcaldia: int) -> int:
    gdf = leer_geojson(ARCHIVO_COLONIAS)
    gam = gdf[gdf["cve_alc"] == CVE_ALC_GAM]
    filas = [
        {"id_alcaldia": id_alcaldia,
         "nombre": " ".join(str(r.colonia).split()),
         "clave": r.cve_col,
         "wkt": r.geometry.wkt}
        for r in gam.itertuples()
    ]
    con.execute(text(f"""
        INSERT INTO colonia (id_alcaldia, nombre, clave_oficial, geom)
        VALUES (:id_alcaldia, :nombre, :clave, {GEOM_SQL})
        ON CONFLICT (clave_oficial) DO UPDATE
           SET nombre = EXCLUDED.nombre,
               id_alcaldia = EXCLUDED.id_alcaldia,
               geom = EXCLUDED.geom
    """), filas)
    print(f"colonia: {len(filas)} colonias de GAM cargadas")
    return len(filas)


def cargar_delitos(con) -> int:
    cat = pd.read_csv(CATALOGO_DELITOS, encoding="utf-8-sig")
    invalidas = set(cat["gravedad"]) - set(PESOS)
    if invalidas:
        sys.exit(f"Gravedades no reconocidas en el catálogo: {invalidas}")
    fgj = pd.read_parquet(PARQUET_FGJ, columns=["delito", "categoria_delito"])
    categoria = fgj.groupby("delito")["categoria_delito"].agg(lambda s: s.mode().iloc[0])
    cat["categoria_oficial"] = cat["delito"].map(categoria)
    if cat["categoria_oficial"].isna().any():
        sys.exit("Hay delitos del catálogo sin categoría oficial en el parquet")

    filas = [
        {"nombre": r.delito, "categoria": r.categoria_oficial, "grupo": r.grupo,
         "gravedad": r.gravedad, "peso": PESOS[r.gravedad]}
        for r in cat.itertuples()
    ]
    con.execute(text("""
        INSERT INTO cat_delito (nombre, categoria_oficial, grupo, gravedad, peso_gravedad)
        VALUES (:nombre, :categoria, :grupo, :gravedad, :peso)
        ON CONFLICT (nombre) DO UPDATE
           SET categoria_oficial = EXCLUDED.categoria_oficial,
               grupo = EXCLUDED.grupo,
               gravedad = EXCLUDED.gravedad,
               peso_gravedad = EXCLUDED.peso_gravedad
    """), filas)
    print(f"cat_delito: {len(filas)} delitos cargados")
    return len(filas)


# ======================================================================
# VERIFICACIÓN
# ======================================================================
def verificar(engine):
    titulo("VERIFICACIÓN EN LA BASE DE DATOS")
    with engine.connect() as con:
        r = con.execute(text("""
            SELECT
              (SELECT count(*) FROM alcaldia),
              (SELECT count(*) FROM colonia),
              (SELECT count(*) FROM cat_delito),
              (SELECT round((ST_Area(geom::geography) / 1e6)::numeric, 1)
                 FROM alcaldia WHERE nombre = :gam),
              (SELECT count(*) FROM colonia c JOIN alcaldia a USING (id_alcaldia)
                WHERE NOT ST_Intersects(a.geom, ST_PointOnSurface(c.geom))),
              (SELECT round((100 * ST_Area(ST_Union(c.geom)::geography)
                                 / ST_Area(a.geom::geography))::numeric, 1)
                 FROM colonia c JOIN alcaldia a USING (id_alcaldia)
                GROUP BY a.geom)
        """), {"gam": NOMBRE_GAM}).one()
        print(f"Registros → alcaldia: {r[0]} | colonia: {r[1]} | cat_delito: {r[2]}")
        print(f"Superficie de GAM: {r[3]} km²")
        print(f"Colonias cuyo interior cae fuera de GAM: {r[4]} (debe ser 0)")
        print(f"Superficie de GAM cubierta por colonias: {r[5]}%")

        gravedad = con.execute(text("""
            SELECT gravedad, count(*) FROM cat_delito
            GROUP BY gravedad, peso_gravedad ORDER BY peso_gravedad DESC
        """)).all()
        print("Delitos por gravedad: " + ", ".join(f"{g}: {n}" for g, n in gravedad))

        gam = gpd.read_postgis("SELECT geom FROM alcaldia", con, geom_col="geom")
        colonias = gpd.read_postgis("SELECT nombre, geom FROM colonia", con, geom_col="geom")

    titulo("ENSAYO: ASÍ SE COMPORTARÁ EL TRIGGER CON LOS DATOS DE LA FGJ")
    fgj = pd.read_parquet(PARQUET_FGJ, columns=["alcaldia_catalogo", "colonia_catalogo",
                                                "latitud", "longitud"])
    fgj = fgj[(fgj["alcaldia_catalogo"] == NOMBRE_GAM)].dropna(subset=["latitud", "longitud"])
    puntos = gpd.GeoDataFrame(fgj, geometry=gpd.points_from_xy(fgj["longitud"], fgj["latitud"]),
                              crs=4326)

    dentro = puntos.within(gam.geometry.iloc[0])
    print(f"Registros etiquetados como GAM con coordenadas: {len(puntos):,}")
    print(f"  Caen dentro del polígono de GAM (dentro_gam = true): "
          f"{dentro.sum():,} ({dentro.mean() * 100:.1f}%)")
    print(f"  Caen fuera y se excluirán de HDBSCAN: {(~dentro).sum():,}")

    unidos = gpd.sjoin(puntos[dentro], colonias, how="left", predicate="within")
    unidos = unidos[~unidos.index.duplicated()]
    con_colonia = unidos["nombre"].notna()
    coincide = unidos["nombre"].map(normalizar) == unidos["colonia_catalogo"].map(normalizar)
    print(f"  De los que caen dentro, reciben colonia por ubicación: {con_colonia.mean() * 100:.1f}%")
    print(f"  Colonia por ubicación = colonia que reporta la FGJ: "
          f"{coincide[con_colonia].mean() * 100:.1f}%")


if __name__ == "__main__":
    faltan = [p for p in (ARCHIVO_ALCALDIAS, ARCHIVO_COLONIAS, CATALOGO_DELITOS, PARQUET_FGJ)
              if not p.exists()]
    if faltan:
        sys.exit("No encontré estos archivos:\n  " + "\n  ".join(str(p) for p in faltan))

    engine = get_engine()
    titulo("CARGA DE CATÁLOGOS")
    with engine.begin() as con: 
        id_gam = cargar_alcaldia(con)
        cargar_colonias(con, id_gam)
        cargar_delitos(con)
    print("Transacción confirmada.")

    verificar(engine)