"""Corre el análisis HDBSCAN real sin guardar nada (pieza 3.3) y dibuja su mapa.

Sirve para comprobar que clustering.py da lo mismo que la prueba de sensibilidad
(configuración 100 / 10) y para VER el resultado en el mapa.

Uso, desde la carpeta backend con (.venv):
    python probar_clustering.py            -> resumen en la terminal + mapa_clustering.html
    python probar_clustering.py --sin-mapa -> solo el resumen
"""
import sys

import numpy as np

import pruebas_hdbscan as S          # reutilizamos su mapa interactivo
from app.servicios import clustering as C
from db import get_engine

SALIDA_MAPA = "mapa_clustering.html"

with get_engine().connect() as con:
    puntos = C.leer_puntos(con)
    limite = S.cargar_limite(con)

p = C.PARAMETROS
print(f"Puntos analizados: {len(puntos):,}  (gravedad >= {p.peso_minimo})")
print(f"min_cluster_size {p.min_cluster_size} · min_samples {p.min_samples}\n")

r = C.ejecutar(puntos)
print(f"Hotspots: {r.n_hotspots}")
print(f"Ruido:    {r.n_ruido:,} ({r.pct_ruido} %)")
print(f"Tiempo:   {r.duracion_s} s\n")

print(f"{'código':<7}{'víctimas':>9}{'gravedad':>9}{'radio m':>9}  {'colonia':<32}delito principal")
for h in r.hotspots[:10]:
    print(f"{h['codigo']:<7}{h['n_puntos']:>9,}{h['indice_gravedad']:>9}{h['radio_m']:>9,.0f}  "
          f"{h['colonia'][:30]:<32}{h['delito_predominante'][:40]} ({h['pct_delito']} %)")
print(f"… y {max(r.n_hotspots - 10, 0)} más")


# ------------------------------------------------------------------ mapa
def a_corrida(r: C.Resultado) -> dict:
    """Traduce el resultado de clustering.py al formato que dibuja el mapa de sensibilidad."""
    tamanos = [h["n_puntos"] for h in r.hotspots] or [0]
    nodos = [{
        "id": h["codigo"], "rank": h["etiqueta"], "n": h["n_puntos"],
        "lat": h["lat_centroide"], "lon": h["lon_centroide"],          # medoide
        "colonia": h["colonia"], "delito": h["delito_predominante"], "pct_delito": h["pct_delito"],
        "gravedad": h["indice_gravedad"], "radio_m": round(h["radio_m"]),
        "densidad": h["densidad"], "confianza": h["confianza"],
        # GeoJSON guarda [lon, lat]; Leaflet dibuja con [lat, lon]
        "area": [[lat, lon] for lon, lat in h["area"]["coordinates"][0]] if h["area"] else None,
    } for h in r.hotspots]
    return {
        "min_cluster_size": r.parametros.min_cluster_size,
        "hotspots": r.n_hotspots,
        "ruido": r.n_ruido,
        "pct_ruido": r.pct_ruido,
        "menor": min(tamanos), "mediana": int(np.median(tamanos)), "mayor": max(tamanos),
        "en_rango": True, "elegido": True,
        "nodos": nodos,
        "etiquetas": [int(e) if e == e and e is not None else 0 for e in r.membresia.etiqueta],
    }


if "--sin-mapa" not in sys.argv:
    S.escribir_mapa(puntos, limite, [a_corrida(r)], salida=SALIDA_MAPA,
                    titulo="Hotspots del backend (clustering.py)", rango=None,
                    min_samples=p.min_samples)
    print(f"\nMapa: {SALIDA_MAPA}  <- ábrelo con doble clic "
          f"(el círculo de cada hotspot está en su medoide)")