import { useEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import { Marker, Polyline, Tooltip } from 'react-leaflet'
import { iconoEstacion } from '../../components/mapa/CapaHotspots.jsx'
import { posicionEn } from './useSimulacion.js'
import { textoSobre } from '../../lib/colores.js'

/** Arreglo vacío estable: si fuera `[]` en cada render, react-leaflet borraría el recorrido */
const VACIO = []

const iconoAgente = (numero, color, detenido) =>
  L.divIcon({
    className: 'ttr-icono-limpio',
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    html: `<div class="ttr-agente" style="--c:${color};--tc:${textoSobre(color)}" data-detenido="${detenido}">${numero}</div>`,
  })

/**
 * Un agente en el mapa: su ruta como línea de transporte (tenue la parte pendiente,
 * sólida la recorrida), sus estaciones y el marcador que se mueve.
 */
export default function CapaAgente({ ruta, preparada, numero, color, info, sim, visitados }) {
  const refMarcador = useRef(null)
  const refRecorrido = useRef(null)
  const completa = useMemo(() => preparada.coords.map(([lon, lat]) => [lat, lon]), [preparada])
  const orden = ruta.properties.hotspots ?? []
  const detenido = !sim.corriendo

  // Movimiento cuadro a cuadro sin pasar por React
  useEffect(
    () =>
      sim.suscribir((d) => {
        const p = posicionEn(preparada, d)
        refMarcador.current?.setLatLng(p.latlng)
        if (refRecorrido.current) {
          const hecho = completa.slice(0, p.tramo + 1)
          hecho.push(p.latlng)
          refRecorrido.current.setLatLngs(d <= 0 ? [] : hecho)
        }
      }),
    [sim.suscribir, preparada, completa], // eslint-disable-line react-hooks/exhaustive-deps
  )

  const icono = useMemo(() => iconoAgente(numero, color, detenido), [numero, color, detenido])

  return (
    <>
      <Polyline
        positions={completa}
        pane="rutas"
        interactive={false}
        pathOptions={{ color, weight: 3, opacity: 0.4, dashArray: '2 7', lineCap: 'round' }}
      />
      <Polyline
        ref={refRecorrido}
        positions={VACIO}
        pane="rutas"
        interactive={false}
        pathOptions={{ color: '#fff', weight: 9, opacity: 0.95 }}
      />
      <RecorridoColor color={color} sim={sim} preparada={preparada} completa={completa} />
      {orden.map((h, i) => {
        const d = info.get(h)
        if (!d) return null
        const visitada = i < visitados
        return (
          <Marker
            key={h}
            position={[d.centroide[1], d.centroide[0]]}
            icon={iconoEstacion({ etiqueta: d.etiqueta, color, activa: visitada, tam: i === 0 ? 28 : 22 })}
            keyboard={false}
            zIndexOffset={i === 0 ? 200 : 0}
          >
            <Tooltip className="ttr-tooltip" direction="top" offset={[0, -12]}>
              {i === 0 ? 'Salida: ' : `Parada ${i + 1}: `}
              {d.codigo}
              {d.colonia ? `, ${d.colonia}` : ''}
            </Tooltip>
          </Marker>
        )
      })}
      <Marker
        ref={refMarcador}
        position={completa[0]}
        icon={icono}
        zIndexOffset={1000}
        keyboard={false}
        title={`Agente ${numero}`}
      />
    </>
  )
}

/** Línea de color sobre el casco blanco: se actualiza junto con el recorrido */
function RecorridoColor({ color, sim, preparada, completa }) {
  const ref = useRef(null)
  useEffect(
    () =>
      sim.suscribir((d) => {
        if (!ref.current) return
        const p = posicionEn(preparada, d)
        const hecho = completa.slice(0, p.tramo + 1)
        hecho.push(p.latlng)
        ref.current.setLatLngs(d <= 0 ? [] : hecho)
      }),
    [sim.suscribir, preparada, completa], // eslint-disable-line react-hooks/exhaustive-deps
  )
  return (
    <Polyline
      ref={ref}
      positions={VACIO}
      pane="rutas"
      interactive={false}
      pathOptions={{ color, weight: 5, opacity: 1, lineCap: 'round', lineJoin: 'round' }}
    />
  )
}
