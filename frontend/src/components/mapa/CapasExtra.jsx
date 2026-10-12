import { useMemo } from 'react'
import { GeoJSON, Polygon, Tooltip } from 'react-leaflet'
import convex from '@turf/convex'
import { featureCollection, point } from '@turf/helpers'

/** Colonias como líneas finas; al pasar el cursor muestran su nombre */
export function CapaColonias({ colonias }) {
  if (!colonias) return null
  return (
    <GeoJSON
      key="colonias"
      data={colonias}
      pane="zonas"
      style={{ color: '#34374C', weight: 0.8, opacity: 0.45, fillOpacity: 0, fillColor: '#34374C' }}
      onEachFeature={(f, capa) => {
        capa.bindTooltip(f.properties.nombre, { sticky: true, className: 'ttr-tooltip', direction: 'top' })
        capa.on({
          mouseover: () => capa.setStyle({ fillOpacity: 0.07, weight: 1.6, opacity: 0.8 }),
          mouseout: () => capa.setStyle({ fillOpacity: 0, weight: 0.8, opacity: 0.45 }),
        })
      }}
    />
  )
}

/**
 * Territorio de cada grafo: envolvente convexa de las áreas de sus hotspots.
 * Muestra cómo Louvain divide la región de GAM.
 */
export function CapaZonasGrafo({ hotspots, particion }) {
  const zonas = useMemo(() => {
    if (!hotspots || !particion) return []
    const porId = new Map(hotspots.features.map((f) => [f.properties.id_hotspot, f]))
    return particion.grafos
      .map((g) => {
        const pts = []
        g.hotspots.forEach((id) => {
          const f = porId.get(id)
          if (!f) return
          const anillos = f.geometry.type === 'Polygon' ? f.geometry.coordinates : f.geometry.coordinates.flat()
          anillos.forEach((a) => a.forEach((c) => pts.push(point(c))))
        })
        if (pts.length < 3) return null
        const env = convex(featureCollection(pts))
        if (!env) return null
        return {
          numero: g.numero,
          color: g.color,
          n: g.hotspots.length,
          anillo: env.geometry.coordinates[0].map(([lon, lat]) => [lat, lon]),
        }
      })
      .filter(Boolean)
  }, [hotspots, particion])

  return zonas.map((z) => (
    <Polygon
      key={`z-${particion.id_particion}-${z.numero}`}
      pane="zonas"
      positions={z.anillo}
      pathOptions={{ color: z.color, weight: 2, dashArray: '6 6', opacity: 0.9, fillColor: z.color, fillOpacity: 0.06 }}
    >
      <Tooltip sticky className="ttr-tooltip">
        Grafo {z.numero} · {z.n} hotspots
      </Tooltip>
    </Polygon>
  ))
}
