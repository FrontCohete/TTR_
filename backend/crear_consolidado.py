"""Crea un consolidado 2023 + 2024 para probar la detección de duplicados.

Uso, desde la carpeta backend con (.venv):
    python crear_consolidado.py
"""
from pathlib import Path

import pandas as pd

ORIGEN = Path(__file__).resolve().parent.parent / "PI_AnalisisPreviodeGAM"
ARCHIVOS = ["victimasFGJ_2023.csv", "victimasFGJ_2024.csv"]
DESTINO = ORIGEN / "consolidado_2023_2024.csv"

partes = []
for nombre in ARCHIVOS:
    ruta = ORIGEN / nombre
    if not ruta.exists():
        raise SystemExit(f"No encontré {ruta}")
    # keep_default_na=False: los vacíos se quedan vacíos, sin convertirse en "nan"
    datos = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    print(f"{nombre}: {len(datos):,} filas")
    partes.append(datos)

consolidado = pd.concat(partes, ignore_index=True)   # uno debajo del otro
consolidado.to_csv(DESTINO, index=False, encoding="utf-8")
print(f"Listo: {DESTINO.name} con {len(consolidado):,} filas")