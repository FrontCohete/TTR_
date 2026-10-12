"""Exploración de los CSV crudos de la FGJ antes de escribir ingesta.py.

Solo lee archivos; no toca la base de datos.
Se ejecuta desde la carpeta backend:   python explorar_fgj.py
El reporte también se guarda en backend/exploracion_fgj.txt
"""
import time
import unicodedata
from itertools import combinations
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PREVIO = RAIZ / "PI_AnalisisPreviodeGAM"
ARCHIVOS = sorted(PREVIO.glob("victimasFGJ_*.csv"))
CATALOGO = PREVIO / "catalogo_delitos.csv"
PARQUET = PREVIO / "victimas_cdmx_limpio.parquet"
REPORTE = Path(__file__).with_name("exploracion_fgj.txt")

OBLIGATORIAS = ["fecha_hecho", "hora_hecho", "delito", "alcaldia_hecho", "latitud", "longitud"]
HUELLA = ["fecha_hecho", "hora_hecho", "delito", "latitud", "longitud",
          "sexo", "edad", "calidad_juridica"]

lineas = []


def decir(texto=""):
    """Imprime en pantalla y guarda la línea para el reporte."""
    print(texto)
    lineas.append(str(texto))


def titulo(t):
    decir("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


def normalizar(s) -> str:
    """Mayúsculas, sin acentos y sin espacios dobles (igual que cargar_catalogos.py)."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def encabezado(c) -> str:
    """'Fecha Hecho' -> 'fecha_hecho'"""
    s = unicodedata.normalize("NFKD", str(c)).encode("ascii", "ignore").decode()
    return "_".join(s.strip().lower().split())


def leer_csv(ruta: Path):
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(ruta, encoding=codificacion, dtype=str)
            if df.shape[1] == 1:  # quizá el separador es ';'
                df = pd.read_csv(ruta, encoding=codificacion, dtype=str, sep=";")
            return df, codificacion
        except UnicodeDecodeError:
            continue
    raise ValueError(f"No pude leer {ruta.name}")


def construir_huella(d: pd.DataFrame) -> pd.Series:
    """Une los campos de la huella propuesta en un solo texto por fila."""
    partes = []
    for c in HUELLA:
        if c in ("latitud", "longitud"):
            v = pd.to_numeric(d[c], errors="coerce").round(6).astype(str)
        elif c == "edad":
            v = pd.to_numeric(d[c], errors="coerce").astype("Int64").astype(str)
        else:
            v = d[c].fillna("").map(normalizar)
        partes.append(v)
    huella = partes[0]
    for p in partes[1:]:
        huella = huella + "|" + p
    return huella


# ---------------------------------------------------------------- referencias
catalogo = pd.read_csv(CATALOGO, encoding="utf-8-sig")
cat_exacto = set(catalogo["delito"])
cat_normal = {normalizar(x) for x in catalogo["delito"]}
cols_parquet = set(pd.read_parquet(PARQUET).columns) - {"archivo", "hora"}
parquet = pd.read_parquet(PARQUET, columns=["archivo", "alcaldia_catalogo"])
gam_parquet = parquet[parquet["alcaldia_catalogo"] == "Gustavo A. Madero"].groupby("archivo").size()

decir(f"Archivos encontrados: {[r.name for r in ARCHIVOS]}")
decir(f"Catálogo: {len(cat_exacto)} delitos")

huellas = {}

for ruta in ARCHIVOS:
    titulo(f"ARCHIVO {ruta.name}")
    inicio = time.perf_counter()
    df, codificacion = leer_csv(ruta)
    df.columns = [encabezado(c) for c in df.columns]
    decir(f"Leído en {time.perf_counter() - inicio:.1f} s · codificación {codificacion} · "
          f"{len(df):,} filas · {df.shape[1]} columnas")
    decir("Columnas: " + ", ".join(df.columns))

    faltan = [c for c in OBLIGATORIAS if c not in df.columns]
    decir(f"Obligatorias faltantes: {faltan or 'ninguna'}")
    decir(f"Columnas del parquet que no están aquí: {sorted(cols_parquet - set(df.columns)) or 'ninguna'}")
    decir(f"Columnas de aquí que no están en el parquet: {sorted(set(df.columns) - cols_parquet) or 'ninguna'}")
    if faltan:
        continue

    # ------------------------------------------------------------ 1 · GAM
    es_gam = df["alcaldia_hecho"].fillna("").map(normalizar).str.contains("GUSTAVO A")
    gam = df[es_gam]
    lat = pd.to_numeric(gam["latitud"], errors="coerce")
    lon = pd.to_numeric(gam["longitud"], errors="coerce")
    sin_coord = lat.isna() | lon.isna()
    en_recuadro = lat.between(19.40, 19.65) & lon.between(-99.25, -99.00)
    anio = int(ruta.stem.split("_")[-1])
    decir(f"\n1 · Filas de GAM según alcaldia_hecho: {len(gam):,} ({len(gam) / len(df) * 100:.1f} %)")
    decir(f"    En el parquet limpio (alcaldia_catalogo, archivo {anio}): {gam_parquet.get(anio, 0):,}")
    decir(f"    Sin coordenadas: {sin_coord.sum():,} · "
          f"con coordenadas fuera del recuadro de GAM: {(~sin_coord & ~en_recuadro).sum():,}")
    decir("    Ejemplos de formato:")
    decir(gam[["fecha_hecho", "hora_hecho", "edad", "latitud", "longitud"]].head(3).to_string(index=False))

    # ------------------------------------------------------- 2 · delitos
    delitos = gam["delito"].fillna("")
    exacto = delitos.isin(cat_exacto)
    normal = delitos.map(normalizar).isin(cat_normal)
    decir(f"\n2 · Delitos distintos en GAM: {delitos.nunique()}")
    decir(f"    Registros cuyo delito coincide EXACTO con el catálogo: {exacto.mean() * 100:.2f} %")
    decir(f"    Registros que coinciden tras normalizar: {normal.mean() * 100:.2f} %")
    faltantes = delitos[~normal].value_counts().head(10)
    if len(faltantes):
        decir("    Delitos que NO están en el catálogo (los 10 más frecuentes):")
        decir(faltantes.to_string())

    # ------------------------------------------------- 3 · duplicados
    con_coord = gam[~sin_coord]
    huella = construir_huella(con_coord)
    decir(f"\n3 · Huella propuesta: {' | '.join(HUELLA)}")
    decir(f"    Registros con coordenadas: {len(huella):,} · huellas distintas: {huella.nunique():,}")
    decir(f"    Registros que comparten huella con otro: {huella.duplicated(keep=False).sum():,} "
          f"(se descartarían {huella.duplicated().sum():,})")
    decir(f"    Filas idénticas en TODAS las columnas: {con_coord.duplicated().sum():,}")
    huellas[ruta.name] = set(huella)

titulo("4 · REGISTROS REPETIDOS ENTRE ARCHIVOS (misma huella)")
for a, b in combinations(huellas, 2):
    decir(f"{a} y {b}: {len(huellas[a] & huellas[b]):,} huellas en común")

REPORTE.write_text("\n".join(lineas), encoding="utf-8")
print(f"\nReporte guardado en {REPORTE}")