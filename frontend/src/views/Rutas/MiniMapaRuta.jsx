import { useMemo } from 'react'
import { Marker, Polyline } from 'react-leaflet'
import MapaGAM from '../../components/mapa/MapaGAM.jsx'
import { iconoEstacion } from '../../components/mapa/CapaHotspots.jsx'
import { useLimite } from '../../api/consultas.js'
import s from './Rutas.module.css'

/** Mapa pequeño con la mejor ruta de la generación que se está mostrando */
export default function MiniMapaRuta({ perm, info, color, cerrada, nodos }) {
  const limite = useLimite()
  const linea = useMemo(() => {
    if (!perm?.length || !info) return []
    const pts = perm
      .map((h) => info.get(h)?.centroide)
      .filter(Boolean)
      .map(([lon, lat]) => [lat, lon])
    if (cerrada && pts.length > 1) pts.push(pts[0])
    return pts
  }, [perm, info, cerrada])

  const encuadre = useMemo(() => {
    const pts = (nodos ?? []).map((h) => info?.get(h)?.centroide).filter(Boolean)
    if (pts.length < 2) return undefined
    const lats = pts.map((p) => p[1])
    const lons = pts.map((p) => p[0])
    return [
      [Math.min(...lats), Math.min(...lons)],
      [Math.max(...lats), Math.max(...lons)],
    ]
  }, [nodos, info])

  const estaciones = useMemo(() => (nodos ?? []).map((h) => ({ h, d: info?.get(h) })).filter((x) => x.d), [nodos, info])

  return (
    <figure className={s.miniMapa}>
      <figcaption className={s.graficaTitulo}>Mejor ruta de esta generación</figcaption>
      <div className={s.miniMapaArea}>
        <MapaGAM
          limite={limite.data}
          encuadre={encuadre}
          relleno={[22, 22]}
          mostrarEscala={false}
          mostrarZoom={false}
          zoomMinimo={10}
          rueda={false}
        >
          {linea.length > 1 && (
            <>
              <Polyline
                positions={linea}
                pane="rutas"
                pathOptions={{ color: '#fff', weight: 7, opacity: 0.9 }}
                interactive={false}
              />
              <Polyline
                positions={linea}
                pane="rutas"
                pathOptions={{ color, weight: 3.5, opacity: 1 }}
                interactive={false}
              />
            </>
          )}
          {estaciones.map(({ h, d }, i) => (
            <Marker
              key={h}
              position={[d.centroide[1], d.centroide[0]]}
              icon={iconoEstacion({ etiqueta: d.etiqueta, color, activa: perm?.[0] === h, tam: 18 })}
              interactive={false}
              keyboard={false}
              zIndexOffset={i}
            />
          ))}
        </MapaGAM>
      </div>
    </figure>
  )
}
