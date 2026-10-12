import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd
from sqlalchemy import text

from db import get_engine

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "database" / "fuentes"
PARQUET_FGJ = RAIZ / "PI_AnalisisPreviodeGAM" / "victimas_cdmx_limpio.parquet"

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 40)


def normalizar(s) -> str:
    """Mayúsculas, sin acentos y sin espacios dobles, para comparar nombres."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def titulo(t: str):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)

titulo("1 · CONEXIÓN A LA BASE DE DATOS")
try:
    with get_engine().connect() as con:
        fila = con.execute(text("""
            SELECT current_user, current_database(), postgis_lib_version(),
                   (SELECT count(*) FROM information_schema.tables
                     WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                       AND table_name <> 'spatial_ref_sys')
        """)).one()
    print(f"Usuario: {fila[0]} | Base: {fila[1]} | PostGIS: {fila[2]} | Tablas: {fila[3]}")
except Exception as e:
    print(f"ERROR de conexión: {e}")
    print("Revisa el archivo backend/.env")
archivos = sorted(FUENTES.glob("*.geojson")) + sorted(FUENTES.glob("*.json"))
if not archivos:
    print(f"\nNo encontré archivos .geojson en {FUENTES}")

colonias_geo = {}

for ruta in archivos:
    titulo(f"2 · ARCHIVO: {ruta.name}")
    gdf = gpd.read_file(ruta)
    print(f"Registros: {len(gdf):,}")
    print(f"Sistema de coordenadas: {gdf.crs}")
    print(f"Tipos de geometría: {gdf.geom_type.value_counts().to_dict()}")
    print(f"Límites (lon/lat): {[round(float(v), 4) for v in gdf.total_bounds]}")

    atributos = gdf.drop(columns="geometry")
    print("\nColumnas:")
    for c in atributos.columns:
        ejemplo = atributos[c].dropna().astype(str).head(3).tolist()
        print(f"  - {c:<20} {str(atributos[c].dtype):<10} ej: {ejemplo}")
    texto = atributos.select_dtypes(include=["object", "string"])
    mascara_gam = pd.Series(False, index=gdf.index)
    for c in texto.columns:
        coincide = texto[c].map(normalizar).str.contains("GUSTAVO A", na=False)
        if coincide.any():
            print(f"\n'Gustavo A. Madero' aparece en la columna '{c}' "
                  f"({coincide.sum()} registros) como: {texto.loc[coincide, c].unique()[:3].tolist()}")
            mascara_gam |= coincide
    for c in atributos.columns:
        valores = atributos[c].astype(str)
        coincide = valores.isin(["005", "5", "09005", "9005"])
        if coincide.any() and not mascara_gam.any():
            print(f"Posible clave de GAM en la columna '{c}' ({coincide.sum()} registros)")

    if mascara_gam.any():
        gam = gdf[mascara_gam]
        print(f"\nRegistros de GAM: {len(gam)}")
        print(gam.drop(columns="geometry").head(5).to_string())
        # Si hay varios registros de GAM, probablemente son colonias:
        # se guardan todas las columnas de texto con valores casi únicos
        if len(gam) > 1:
            candidatas = {}
            for c in texto.columns:
                nombres = gam[c].dropna().map(normalizar)
                if nombres.nunique() > len(gam) * 0.8:
                    candidatas[c] = set(nombres)
            if candidatas:
                colonias_geo[ruta.name] = candidatas
                print(f"Columnas candidatas a nombre de colonia: {list(candidatas)}")

titulo("3 · COINCIDENCIA DE NOMBRES CON LA FGJ")
if not PARQUET_FGJ.exists():
    print(f"No encontré {PARQUET_FGJ}; se omite la comparación.")
elif not colonias_geo:
    print("No se identificó un archivo de colonias de GAM; se omite la comparación.")
else:
    fgj = pd.read_parquet(PARQUET_FGJ, columns=["alcaldia_catalogo", "colonia_catalogo"])
    fgj = fgj[fgj["alcaldia_catalogo"] == "Gustavo A. Madero"]
    nombres_fgj = set(fgj["colonia_catalogo"].dropna().map(normalizar))
    print(f"Colonias distintas de GAM en la FGJ: {len(nombres_fgj)}")
    for archivo, candidatas in colonias_geo.items():
        col, nombres = max(candidatas.items(), key=lambda kv: len(kv[1] & nombres_fgj))
        comunes = nombres & nombres_fgj
        print(f"\n{archivo} · columna de nombre detectada: '{col}' ({len(nombres)} colonias de GAM)")
        print(f"  Coinciden por nombre: {len(comunes)} "
              f"({len(comunes) / len(nombres_fgj) * 100:.1f}% de las de la FGJ)")
        solo_fgj = sorted(nombres_fgj - nombres)[:10]
        if solo_fgj:
            print(f"  Ejemplos que están en la FGJ y no en el archivo: {solo_fgj}")