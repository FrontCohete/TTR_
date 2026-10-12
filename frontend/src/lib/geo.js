// Utilidades geográficas.
// Recordatorio: GeoJSON usa [longitud, latitud]; Leaflet usa [latitud, longitud].

/** [lon, lat] (GeoJSON) → [lat, lon] (Leaflet) */
export const aLeaflet = ([lon, lat]) => [lat, lon]

/** Distancia en metros entre dos puntos [lon, lat] (fórmula de haversine) */
export function haversine([lon1, lat1], [lon2, lat2]) {
  const R = 6371008.8
  const rad = Math.PI / 180
  const dLat = (lat2 - lat1) * rad
  const dLon = (lon2 - lon1) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

/** Caja envolvente [[latMin, lonMin], [latMax, lonMax]] de una FeatureCollection */
export function limitesLeaflet(fc) {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  const visitar = (c) => {
    if (typeof c[0] === 'number') {
      if (c[0] < minX) minX = c[0]
      if (c[0] > maxX) maxX = c[0]
      if (c[1] < minY) minY = c[1]
      if (c[1] > maxY) maxY = c[1]
      return
    }
    c.forEach(visitar)
  }
  fc.features.forEach((f) => visitar(f.geometry.coordinates))
  return [
    [minY, minX],
    [maxY, maxX],
  ]
}

/** Encuadre aproximado de GAM, por si el contorno aún no carga */
export const ENCUADRE_GAM = [
  [19.44, -99.2],
  [19.6, -99.04],
]
export const CENTRO_GAM = [19.505, -99.115]
