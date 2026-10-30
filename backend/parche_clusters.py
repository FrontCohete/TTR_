"""Etapa 6.5: el análisis deja de depender del orden en que se cargaron los datasets.

Se corre UNA vez desde la carpeta backend:  python parche_clustering.py
Cambia app/servicios/clustering.py (guarda antes una copia en clustering.py.bak):
  1. la consulta de puntos trae la huella de cada registro (hash_registro) y ordena por ella,
     no por id_punto (que depende del orden de carga);
  2. ejecutar() ordena los puntos por coordenadas y huella antes de HDBSCAN.
Si algo no coincide con lo esperado, no cambia nada y dice qué no encontró.
"""
import re
import shutil
from pathlib import Path

ruta = Path("app") / "servicios" / "clustering.py"
if not ruta.exists():
    raise SystemExit("No encuentro app\\servicios\\clustering.py: corre esto desde la carpeta backend.")
original = ruta.read_text(encoding="utf-8")
s = original
if "def orden_estable" in s:
    raise SystemExit("clustering.py ya tiene el cambio. No se tocó nada.")


def cambiar(viejo, nuevo, que, regex=False):
    global s
    if regex:
        s2, n = re.subn(viejo, nuevo, s, count=1, flags=re.M)
    else:
        n = s.count(viejo)
        s2 = s.replace(viejo, nuevo, 1)
    if n < 1:
        raise SystemExit(f"No encontré {que}. No se cambió nada.")
    s = s2
    print("  ✓", que)


cambiar(r"^(\s*coalesce\(c\.nombre, p\.colonia_texto, 'Sin colonia'\) AS colonia)\s*$",
        r"\1,\n           p.hash_registro AS huella", "la columna colonia en la consulta de puntos", regex=True)
cambiar("    ORDER BY p.id_punto\n", "    ORDER BY p.hash_registro\n", "ORDER BY p.id_punto")
cambiar("ORDER BY id_punto hace que el resultado sea siempre el mismo con los mismos datos.",
        "Se ordenan por la huella de cada registro (hash_registro), que depende solo de su contenido:\n"
        "    el resultado es el mismo sin importar en qué orden se cargaron los datasets (etapa 6.5).",
        "el comentario de leer_puntos")
cambiar("def ejecutar(puntos: pd.DataFrame, parametros: Parametros = PARAMETROS) -> Resultado:\n",
        '''def orden_estable(puntos: pd.DataFrame) -> pd.DataFrame:
    """Los mismos puntos siempre en el mismo orden, sin importar el orden de carga (etapa 6.5).

    HDBSCAN puede dar resultados ligeramente distintos con los mismos puntos en otro orden cuando
    hay coordenadas repetidas (muy común: varias víctimas en el mismo domicilio). Se ordena por
    coordenadas en metros y, para desempatar, por la huella del registro (si viene en los datos).
    """
    claves = ["x", "y"] + (["huella"] if "huella" in puntos.columns else [])
    return puntos.sort_values(claves, kind="mergesort").reset_index(drop=True)


def ejecutar(puntos: pd.DataFrame, parametros: Parametros = PARAMETROS) -> Resultado:
''', "la función ejecutar")
cambiar('''    inicio = time.perf_counter()
    xy = puntos[["x", "y"]].to_numpy()''', '''    inicio = time.perf_counter()
    puntos = orden_estable(puntos)
    xy = puntos[["x", "y"]].to_numpy()''', "el inicio de ejecutar")

# la prueba existente revisa las columnas exactas: ahora hay una más al final
prueba = Path("pruebas") / "test_clustering.py"
t = prueba.read_text(encoding="utf-8") if prueba.exists() else ""
viejo_t = '"peso", "delito", "colonia"]'
if t.count(viejo_t) != 1:
    raise SystemExit("No encontré la lista de columnas en pruebas\\test_clustering.py. No se cambió nada.")
print("  ✓ la lista de columnas en pruebas\\test_clustering.py")

shutil.copy(ruta, ruta.with_suffix(".py.bak"))
ruta.write_text(s, encoding="utf-8")
prueba.write_text(t.replace(viejo_t, '"peso", "delito", "colonia", "huella"]'), encoding="utf-8")
print("Listo. Copia del original en app\\servicios\\clustering.py.bak")