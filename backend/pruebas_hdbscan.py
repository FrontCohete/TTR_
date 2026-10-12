"""Prueba de sensibilidad de HDBSCAN con mapa (etapa 3, paso 3.1).

Corre HDBSCAN con cada combinación de min_cluster_size y min_samples sobre
los puntos que entrarán al análisis. Genera:

  1. sensibilidad_hdbscan.csv   -> resumen: un renglón por cada combinación
  2. hotspots_sensibilidad.csv  -> detalle: un renglón por cada hotspot encontrado
  3. sensibilidad_hdbscan.html  -> mapa interactivo de GAM para comparar los valores

No escribe nada en la base de datos.

Uso, desde la carpeta backend con (.venv):
    python sensibilidad_hdbscan.py
"""
import json
import time
from datetime import date

import numpy as np
import pandas as pd
from scipy.spatial import ConvexHull
from scipy.spatial import QhullError
from sklearn.cluster import HDBSCAN
from sqlalchemy import text

from db import get_engine

# ----------------------------------------------------------------- ajustes
# Se prueba cada min_cluster_size con cada min_samples: 5 × 2 = 10 corridas
VALORES_MIN_CLUSTER_SIZE = [75, 80, 85, 90, 95, 100]
VALORES_MIN_SAMPLES = [10, 20]
ETIQUETAS_FIJAS = 15         # cuántos hotspots (los más grandes) llevan nombre siempre visible

# Qué víctimas entran al análisis
PESO_MINIMO = 2              # 2 = Media, Alta y Crítica (1 = Baja también; 0 nunca entra)
FECHA_DESDE = None           # p. ej. "2022-01-01" para excluir hechos ocurridos antes; None = sin filtro

SALIDA_RESUMEN = "sensibilidad_hdbscan.csv"
SALIDA_HOTSPOTS = "hotspots_sensibilidad.csv"
SALIDA_MAPA = "sensibilidad_hdbscan.html"

TODAS_LAS_GRAVEDADES = {1: "Baja", 2: "Media", 3: "Alta", 4: "Crítica"}
GRAVEDADES = {p: g for p, g in TODAS_LAS_GRAVEDADES.items() if p >= PESO_MINIMO}

# Puntos dentro de GAM con gravedad >= PESO_MINIMO (los hechos no delictivos, peso 0, nunca entran).
# x, y = coordenadas en metros (UTM zona 14 Norte, EPSG:32614) para HDBSCAN.
# lat, lon = coordenadas originales para dibujar el mapa.
CONSULTA_PUNTOS = text("""
    SELECT p.latitud::float8  AS lat,
           p.longitud::float8 AS lon,
           ST_X(t.g) AS x,
           ST_Y(t.g) AS y,
           d.peso_gravedad AS peso,
           d.nombre AS delito,
           coalesce(c.nombre, p.colonia_texto, 'Sin colonia') AS colonia
    FROM punto_delictivo p
    JOIN cat_delito d USING (id_delito)
    LEFT JOIN colonia c USING (id_colonia)
    CROSS JOIN LATERAL (
        SELECT ST_Transform(
                   ST_SetSRID(ST_MakePoint(p.longitud::float8, p.latitud::float8), 4326),
                   32614) AS g
    ) t
    WHERE p.dentro_gam
      AND d.peso_gravedad >= greatest(:peso_minimo, 1)
      AND (CAST(:desde AS date) IS NULL OR p.fecha_hecho >= CAST(:desde AS date))
    ORDER BY p.id_punto
""")

# Contorno de GAM, simplificado (~4 m) para que el HTML no pese de más
CONSULTA_LIMITE = text("""
    SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_Union(geom), 0.00004), 6)
    FROM alcaldia
    WHERE nombre ILIKE '%gustavo%' OR (SELECT count(*) FROM alcaldia) = 1
""")


# ------------------------------------------------------------------ datos
def cargar_puntos(con) -> pd.DataFrame:
    return pd.read_sql(CONSULTA_PUNTOS, con,
                       params={"peso_minimo": PESO_MINIMO, "desde": FECHA_DESDE})


def cargar_limite(con):
    """GeoJSON del contorno de GAM, o None si no se pudo leer."""
    try:
        geojson = con.execute(CONSULTA_LIMITE).scalar()
        return json.loads(geojson) if geojson else None
    except Exception as error:                       # el mapa funciona igual sin contorno
        print(f"Aviso: no se pudo leer el contorno de GAM ({error}).")
        return None


# ------------------------------------------------------------- hotspots
def moda(serie: pd.Series):
    """El valor más frecuente y qué porcentaje representa."""
    conteo = serie.value_counts()
    return conteo.index[0], round(100 * conteo.iloc[0] / len(serie))


def envolvente(lat: np.ndarray, lon: np.ndarray):
    """Polígono que encierra los puntos del hotspot (envolvente convexa), o None."""
    unicos = np.unique(np.c_[lat, lon], axis=0)
    if len(unicos) < 3:
        return None
    try:
        casco = ConvexHull(unicos)
    except QhullError:                               # puntos alineados
        return None
    return [[round(float(a), 5), round(float(b), 5)] for a, b in unicos[casco.vertices]]


def describir_hotspots(puntos: pd.DataFrame, etiquetas: np.ndarray,
                       probabilidades: np.ndarray) -> list[dict]:
    """Un diccionario por hotspot, ordenados del más grande al más chico (H-01, H-02…)."""
    datos = puntos.assign(etiqueta=etiquetas, prob=probabilidades)
    datos = datos[datos.etiqueta >= 0]
    hotspots = []
    for etiqueta, grupo in datos.groupby("etiqueta"):
        cx, cy = grupo.x.mean(), grupo.y.mean()                    # centro en metros
        distancias = np.hypot(grupo.x - cx, grupo.y - cy)
        radio = max(float(np.percentile(distancias, 90)), 10.0)    # 90 % de los puntos
        delito, pct_delito = moda(grupo.delito)
        colonia, _ = moda(grupo.colonia)
        hotspots.append({
            "etiqueta_hdbscan": int(etiqueta),
            "n": len(grupo),
            "lat": round(grupo.lat.mean(), 5),
            "lon": round(grupo.lon.mean(), 5),
            "colonia": colonia,
            "delito": delito,
            "pct_delito": pct_delito,
            "gravedad": round(grupo.peso.mean(), 2),
            "radio_m": round(radio),
            "densidad": round(len(grupo) / (np.pi * radio ** 2 / 1e6)),   # víctimas por km²
            "confianza": round(grupo.prob.mean(), 2),
            "area": envolvente(grupo.lat.to_numpy(), grupo.lon.to_numpy()),
        })
    hotspots.sort(key=lambda h: -h["n"])
    for i, h in enumerate(hotspots, start=1):
        h["rank"] = i
        h["id"] = f"H-{i:02d}"
    return hotspots


def renumerar(etiquetas: np.ndarray, hotspots: list[dict]) -> list[int]:
    """Cambia la etiqueta interna de HDBSCAN por el número de rank (1 = el más grande)."""
    a_rank = {h["etiqueta_hdbscan"]: h["rank"] for h in hotspots}
    return [a_rank.get(int(e), 0) for e in etiquetas]              # 0 = ruido


# ------------------------------------------------------------- principal
def correr_hdbscan(puntos: pd.DataFrame, xy: np.ndarray, mcs: int, ms: int) -> dict:
    """Una corrida de HDBSCAN con su resumen, sus hotspots y la etiqueta de cada punto."""
    n = len(xy)
    inicio = time.perf_counter()
    modelo = HDBSCAN(min_cluster_size=mcs, min_samples=ms,
                     cluster_selection_method="eom", copy=True).fit(xy)
    segundos = time.perf_counter() - inicio

    hotspots = describir_hotspots(puntos, modelo.labels_, modelo.probabilities_)
    tamanos = [h["n"] for h in hotspots] or [0]
    ruido = int((modelo.labels_ == -1).sum())
    return {
        "min_cluster_size": mcs,
        "min_samples": ms,
        "hotspots": len(hotspots),
        "ruido": ruido,
        "pct_ruido": round(100 * ruido / n, 1),
        "menor": min(tamanos),
        "mediana": int(np.median(tamanos)),
        "mayor": max(tamanos),
        "segundos": round(segundos, 1),
        "nodos": hotspots,
        "etiquetas": renumerar(modelo.labels_, hotspots),
    }


COLUMNAS = ["min_cluster_size", "min_samples", "hotspots", "ruido", "pct_ruido",
            "menor", "mediana", "mayor", "segundos"]


def imprimir(fila: dict):
    print(f"{fila['min_cluster_size']:>16} {fila['min_samples']:>11} {fila['hotspots']:>9} "
          f"{fila['ruido']:>8,} {fila['pct_ruido']:>8} {fila['menor']:>6} {fila['mediana']:>8} "
          f"{fila['mayor']:>7} {fila['segundos']:>6}")


def main():
    with get_engine().connect() as con:
        puntos = cargar_puntos(con)
        limite = cargar_limite(con)
    n = len(puntos)
    if n == 0:
        raise SystemExit("No hay puntos para analizar. ¿Ya procesaste alguna carga?")
    xy = puntos[["x", "y"]].to_numpy()
    filtro = f"gravedad {', '.join(GRAVEDADES.values())}"
    if FECHA_DESDE:
        filtro += f", hechos desde {FECHA_DESDE}"
    total = len(VALORES_MIN_CLUSTER_SIZE) * len(VALORES_MIN_SAMPLES)
    print(f"Puntos que entran al análisis: {n:,} ({filtro})")
    print(f"Corridas: {total} (cada una tarda entre 20 s y 1 min)\n")

    encabezado = (f"{'min_cluster_size':>16} {'min_samples':>11} {'hotspots':>9} {'ruido':>8} "
                  f"{'% ruido':>8} {'menor':>6} {'mediana':>8} {'mayor':>7} {'seg':>6}")
    print(encabezado)
    print("-" * len(encabezado))

    corridas = []
    for ms in VALORES_MIN_SAMPLES:
        for mcs in VALORES_MIN_CLUSTER_SIZE:
            corrida = correr_hdbscan(puntos, xy, mcs, ms)
            corridas.append(corrida)
            imprimir(corrida)

    pd.DataFrame([{k: c[k] for k in COLUMNAS} for c in corridas]).to_csv(SALIDA_RESUMEN, index=False)
    detalle = [{"min_cluster_size": c["min_cluster_size"], "min_samples": c["min_samples"],
                **{k: v for k, v in h.items() if k != "area"}}
               for c in corridas for h in c["nodos"]]
    pd.DataFrame(detalle).to_csv(SALIDA_HOTSPOTS, index=False, encoding="utf-8-sig")
    escribir_mapa(puntos, limite, corridas,
                  min_samples=" y ".join(str(m) for m in VALORES_MIN_SAMPLES))
    print(f"\nListo:\n  {SALIDA_RESUMEN}\n  {SALIDA_HOTSPOTS}\n  {SALIDA_MAPA}  <- ábrelo con doble clic")


# ------------------------------------------------------------------ mapa
def escribir_mapa(puntos: pd.DataFrame, limite, corridas: list[dict], salida: str = None,
                  titulo: str = "Sensibilidad de HDBSCAN", rango=None,
                  min_samples=None, filtro: str = None):
    """Escribe el mapa interactivo. probar_clustering.py también lo usa."""
    datos = {
        "titulo": titulo,
        "n": len(puntos),
        "fecha": date.today().isoformat(),
        "min_samples": min_samples,
        "filtro": filtro or ("gravedad " + ", ".join(GRAVEDADES.values()).lower()
                             + (f" · hechos desde {FECHA_DESDE}" if FECHA_DESDE else "")),
        "etiquetas_fijas": ETIQUETAS_FIJAS,
        "rango": rango,
        "gravedades": GRAVEDADES,
        "bounds": [[puntos.lat.min(), puntos.lon.min()], [puntos.lat.max(), puntos.lon.max()]],
        "limite": limite,
        # [lat, lon, peso] por punto; el orden coincide con "etiquetas" de cada corrida
        "puntos": [[round(a, 5), round(b, 5), int(p)]
                   for a, b, p in zip(puntos.lat, puntos.lon, puntos.peso)],
        "corridas": corridas,
    }
    contenido = PLANTILLA.replace(
        "__DATOS__", json.dumps(datos, ensure_ascii=False, separators=(",", ":")))
    with open(salida or SALIDA_MAPA, "w", encoding="utf-8") as archivo:
        archivo.write(contenido)


PLANTILLA = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Sensibilidad HDBSCAN — GAM</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet.heat/0.2.0/leaflet-heat.js"></script>
<style>
  html,body{margin:0;height:100%;font-family:Arial,Helvetica,sans-serif;background:#f4f4f4}
  #map{position:absolute;top:0;bottom:0;left:0;right:0}
  .panel{position:absolute;z-index:1000;background:rgba(255,255,255,.95);
    box-shadow:0 1px 6px rgba(0,0,0,.25);border-radius:8px;padding:10px 12px}
  #title{top:10px;left:10px;max-width:330px}
  #title h1{margin:0 0 3px;font-size:16px;color:#1F3864}
  #title p{margin:0;font-size:11px;color:#555;line-height:1.35}
  #controls{top:10px;right:10px;font-size:12.5px;color:#222;width:215px}
  #controls label{display:block;margin:3px 0;cursor:pointer}
  #controls select{width:100%;margin-top:4px;padding:3px;font-size:12px}
  #controls .sec{font-weight:bold;color:#1F3864;margin-top:8px;border-top:1px solid #e0e0e0;padding-top:6px}
  #controls .sec:first-child{border-top:none;margin-top:0;padding-top:0}
  #controls .nota{font-size:10.5px;color:#777;margin:2px 0 0 18px}
  #tabla{bottom:14px;left:10px;font-size:11.5px;color:#222;max-height:45vh;overflow:auto}
  #tabla table{border-collapse:collapse}
  #tabla th,#tabla td{padding:2px 7px;text-align:right;border-bottom:1px solid #eee}
  #tabla th{color:#1F3864;font-size:10.5px;position:sticky;top:0;background:#fff}
  #tabla tr.fila{cursor:pointer}
  #tabla tr.fila:hover{background:#eef3fb}
  #tabla tr.activa{background:#dce7f7;font-weight:bold}
  #tabla tr.fuera td{color:#9a9a9a}
  #tabla td.marca{text-align:center;color:#c47f00;font-weight:bold}
  #legend{bottom:14px;right:10px;font-size:11.5px;color:#222;line-height:1.5}
  #legend .bar{height:11px;width:150px;border-radius:3px;margin:3px 0;
    background:linear-gradient(90deg,#2c7bb6,#abd9e9,#ffffbf,#fdae61,#d7191c)}
  #legend .dot{display:inline-block;border-radius:50%;background:#e8112d;border:1.5px solid #7a0010;vertical-align:middle;margin-right:5px}
  #legend .gris{display:inline-block;width:9px;height:9px;border-radius:50%;background:#9e9e9e;vertical-align:middle;margin-right:5px}
  .hotname{background:rgba(255,255,255,.9);border:1px solid #e8112d;border-radius:4px;
    padding:1px 5px;font-size:11px;font-weight:bold;color:#1a1a1a;box-shadow:0 1px 3px rgba(0,0,0,.25)}
  .hotname:before{border-right-color:rgba(255,255,255,.9)!important}
  body.nolabels .hotname{display:none}
  .credit{font-size:10px;color:#888;margin-top:6px}
  @media (max-width:700px){
    #title{max-width:calc(100% - 44px)} #controls{top:auto;bottom:14px;width:auto;left:10px;right:10px}
    #tabla,#legend{display:none}
  }
</style>
</head>
<body>
<div id="map"></div>

<div id="title" class="panel">
  <h1 id="titulo">Sensibilidad de HDBSCAN</h1>
  <p><b>Alcaldía Gustavo A. Madero, CDMX</b><br>
  <span id="subtitulo"></span></p>
</div>

<div id="controls" class="panel">
  <div class="sec">min_cluster_size / min_samples</div>
  <select id="selMcs"></select>
  <div class="sec">Capas</div>
  <label><input type="checkbox" id="cbHeat" checked> Mapa de calor</label>
  <label><input type="checkbox" id="cbHot" checked> Hotspots (círculos)</label>
  <label><input type="checkbox" id="cbLbl" checked> Etiquetas</label>
  <label><input type="checkbox" id="cbArea"> Área de cada hotspot</label>
  <label><input type="checkbox" id="cbLim" checked> Límite de GAM</label>
  <label><input type="checkbox" id="cbPts"> Puntos por hotspot</label>
  <div class="nota">Color = hotspot, gris = ruido.<br>Tarda unos segundos en dibujarse.</div>
  <div class="sec">Gravedad</div>
  <select id="selGrav"><option value="0">Todas las analizadas</option></select>
  <div class="sec">Mapa base</div>
  <label><input type="radio" name="base" id="bLight" checked> Claro</label>
  <label><input type="radio" name="base" id="bStreet"> Calles</label>
</div>

<div id="tabla" class="panel">
  <table>
    <thead><tr><th></th><th>min_cluster_size</th><th>min_samples</th><th>hotspots</th><th>% ruido</th><th>menor</th><th>mediana</th><th>mayor</th></tr></thead>
    <tbody id="cuerpo"></tbody>
  </table>
</div>

<div id="legend" class="panel">
  <b>Densidad de víctimas</b>
  <div class="bar"></div>
  <span style="float:left">Baja</span><span style="float:right">Alta</span><br>
  <span class="dot" style="width:12px;height:12px"></span> Hotspot (tamaño = nº de víctimas)<br>
  <span class="gris"></span> Ruido (sin hotspot)<br>
  <span id="leyendaRango"><span style="color:#c47f00;font-weight:bold">★</span> elegido · <span style="color:#c47f00;font-weight:bold">✓</span> dentro del rango pedido</span>
  <div class="credit" id="credito"></div>
</div>

<script>
const DATA = __DATOS__;
const PALETA = ['#d7191c','#2c7bb6','#7b3294','#e66101','#008837','#c51b8a','#01665e',
                '#8c510a','#4d4d4d','#b2182b','#2166ac','#762a83'];
const fmt = n => n.toLocaleString('es-MX');

const map = L.map('map', {preferCanvas:true});

// Mapas base sin llave de acceso (CARTO ya la exige y OpenStreetMap bloquea páginas abiertas
// con doble clic). Esri sirve sus mosaicos de libre uso con atribución.
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/';
const ATRIB = 'Mosaicos &copy; Esri · Datos: FGJ-CDMX';
const light = L.layerGroup([
  L.tileLayer(ESRI + 'Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
    {attribution:ATRIB, maxNativeZoom:16, maxZoom:19}),
  L.tileLayer(ESRI + 'Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
    {maxNativeZoom:16, maxZoom:19}),                       // nombres de calles y colonias
]);
const street = L.tileLayer(ESRI + 'World_Street_Map/MapServer/tile/{z}/{y}/{x}',
  {attribution:ATRIB, maxZoom:19});
light.addTo(map);
map.fitBounds(DATA.bounds);

document.getElementById('subtitulo').innerHTML =
  fmt(DATA.n) + ' víctimas analizadas · ' + DATA.filtro + '<br>' +
  (DATA.rango ? 'Rango pedido: ' + DATA.rango[0] + '–' + DATA.rango[1] + ' hotspots · ' : '') +
  'min_samples = ' + DATA.min_samples + '<br>generado el ' + DATA.fecha;
document.getElementById('titulo').textContent = DATA.titulo;
document.title = DATA.titulo + ' — GAM';
if (!DATA.rango) document.getElementById('leyendaRango').style.display = 'none';

// --- selectores
const selMcs = document.getElementById('selMcs');
const cuerpo = document.getElementById('cuerpo');
DATA.corridas.forEach((c, i) => {
  const o = document.createElement('option');
  o.value = i;
  const marca = c.elegido ? '★ ' : (c.en_rango ? '✓ ' : '');
  o.textContent = marca + c.min_cluster_size + ' / ' + (c.min_samples ?? DATA.min_samples) + ' · ' +
                  c.hotspots + ' hotspots · ' + c.pct_ruido + ' % ruido';
  selMcs.appendChild(o);
  const tr = document.createElement('tr');
  tr.className = 'fila' + (c.en_rango === false ? ' fuera' : '');
  tr.innerHTML = '<td class="marca">' + (c.elegido ? '★' : (c.en_rango ? '✓' : '')) + '</td><td>' + c.min_cluster_size + '</td><td>' + (c.min_samples ?? DATA.min_samples) + '</td><td>' + c.hotspots + '</td><td>' + c.pct_ruido +
                 '</td><td>' + fmt(c.menor) + '</td><td>' + fmt(c.mediana) + '</td><td>' + fmt(c.mayor) + '</td>';
  tr.onclick = () => { selMcs.value = i; dibujarCorrida(); };
  cuerpo.appendChild(tr);
});
selMcs.value = Math.max(0, DATA.corridas.findIndex(c => c.elegido));   // sin elegido: la primera

const selGrav = document.getElementById('selGrav');
Object.entries(DATA.gravedades).forEach(([peso, nombre]) => {
  const o = document.createElement('option');
  o.value = peso; o.textContent = peso + ' · ' + nombre;
  selGrav.appendChild(o);
});

// --- contorno de GAM
const limLayer = DATA.limite
  ? L.geoJSON(DATA.limite, {style:{color:'#1F3864', weight:2, fill:false, dashArray:'5 4'}})
  : L.layerGroup();
limLayer.addTo(map);

// --- mapa de calor (no depende de min_cluster_size)
let heat = null;

// leaflet-heat lee su lienzo muchas veces (getImageData). Avisarle al navegador al crear
// ese lienzo (willReadFrequently) lo hace más rápido y quita el aviso de la consola.
function mostrarCalor() {
  const original = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (tipo, opciones) {
    if (tipo === '2d') opciones = Object.assign({willReadFrequently: true}, opciones || {});
    return original.call(this, tipo, opciones);
  };
  try { heat.addTo(map); } finally { HTMLCanvasElement.prototype.getContext = original; }
}

function puntosFiltrados() {
  const g = parseInt(selGrav.value);
  const res = [];
  DATA.puntos.forEach((p, i) => { if (g === 0 || p[2] === g) res.push(i); });
  return res;
}
function dibujarCalor() {
  if (heat) map.removeLayer(heat);
  const pts = puntosFiltrados().map(i => [DATA.puntos[i][0], DATA.puntos[i][1], 0.6]);
  heat = L.heatLayer(pts, {radius:15, blur:12, maxZoom:16, max:8,
    gradient:{0.2:'#2c7bb6',0.4:'#abd9e9',0.6:'#ffffbf',0.8:'#fdae61',1.0:'#d7191c'}});
  if (document.getElementById('cbHeat').checked) mostrarCalor();
}

// --- hotspots de la corrida elegida
let hotLayer = L.layerGroup(), areaLayer = L.layerGroup(), ptLayer = L.layerGroup();
function gravTexto(g) { return g.toFixed(2) + ' (' + DATA.gravedades[Math.round(g)] + ')'; }

function dibujarCorrida() {
  const c = DATA.corridas[parseInt(selMcs.value)];
  [hotLayer, areaLayer].forEach(l => map.removeLayer(l));
  hotLayer = L.layerGroup(); areaLayer = L.layerGroup();

  c.nodos.forEach(h => {
    const r = 4 + Math.sqrt(h.n) * 0.45;
    const mk = L.circleMarker([h.lat, h.lon], {radius:r, color:'#7a0010', weight:1.5,
      fillColor:'#e8112d', fillOpacity:0.55});
    mk.bindPopup('<b>Hotspot ' + h.id + '</b><br>' + fmt(h.n) + ' víctimas' +
      '<br>Colonia: ' + h.colonia +
      '<br>Delito principal: ' + h.delito + ' (' + h.pct_delito + ' %)' +
      '<br>Gravedad media: ' + gravTexto(h.gravedad) +
      '<br>Radio (90 % de los puntos): ' + fmt(h.radio_m) + ' m' +
      '<br>Densidad: ' + fmt(h.densidad) + ' víct./km²' +
      '<br>Confianza media: ' + h.confianza +
      '<br>Coordenadas: ' + h.lat.toFixed(5) + ', ' + h.lon.toFixed(5));
    if (h.rank <= DATA.etiquetas_fijas) {
      mk.bindTooltip(h.id + ' ' + h.colonia, {permanent:true, direction:'right', offset:[6,0], className:'hotname'});
    } else {
      mk.bindTooltip(h.id + ' ' + h.colonia + ' · ' + fmt(h.n), {direction:'right', offset:[6,0]});
    }
    hotLayer.addLayer(mk);
    if (h.area) {
      L.polygon(h.area, {color:PALETA[(h.rank - 1) % PALETA.length], weight:1.5,
        fillOpacity:0.08}).addTo(areaLayer);
    }
  });
  if (document.getElementById('cbHot').checked) hotLayer.addTo(map);
  if (document.getElementById('cbArea').checked) areaLayer.addTo(map);
  if (document.getElementById('cbPts').checked) dibujarPuntos();

  document.querySelectorAll('#cuerpo tr').forEach((tr, i) =>
    tr.classList.toggle('activa', i === parseInt(selMcs.value)));
  document.getElementById('credito').textContent =
    'HDBSCAN · min_cluster_size ' + c.min_cluster_size + ' · min_samples ' + (c.min_samples ?? DATA.min_samples) +
    ' · ' + c.hotspots + ' hotspots · ' +
    fmt(c.ruido) + ' puntos de ruido (' + c.pct_ruido + ' %)';
}

function dibujarPuntos() {
  map.removeLayer(ptLayer); ptLayer = L.layerGroup();
  const c = DATA.corridas[parseInt(selMcs.value)];
  puntosFiltrados().forEach(i => {
    const p = DATA.puntos[i], et = c.etiquetas[i];
    L.circleMarker([p[0], p[1]], {radius: et ? 2.2 : 1.6, stroke:false,
      fillColor: et ? PALETA[(et - 1) % PALETA.length] : '#9e9e9e',
      fillOpacity: et ? 0.7 : 0.35}).addTo(ptLayer);
  });
  ptLayer.addTo(map);
}

// --- eventos
dibujarCalor();
dibujarCorrida();
selMcs.onchange = dibujarCorrida;
selGrav.onchange = () => { dibujarCalor(); if (document.getElementById('cbPts').checked) dibujarPuntos(); };
document.getElementById('cbHeat').onchange = e => { e.target.checked ? mostrarCalor() : map.removeLayer(heat); };
document.getElementById('cbHot').onchange = e => { e.target.checked ? hotLayer.addTo(map) : map.removeLayer(hotLayer); };
document.getElementById('cbArea').onchange = e => { e.target.checked ? areaLayer.addTo(map) : map.removeLayer(areaLayer); };
document.getElementById('cbLim').onchange = e => { e.target.checked ? limLayer.addTo(map) : map.removeLayer(limLayer); };
document.getElementById('cbLbl').onchange = e => { document.body.classList.toggle('nolabels', !e.target.checked); };
document.getElementById('cbPts').onchange = e => { e.target.checked ? dibujarPuntos() : map.removeLayer(ptLayer); };
document.getElementById('bLight').onchange = () => { map.removeLayer(street); light.addTo(map); };
document.getElementById('bStreet').onchange = () => { map.removeLayer(light); street.addTo(map); };
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()