import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import { Marker, Polygon, Popup, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { SENAL, conAlfa, nombreGravedad, textoSobre } from '../../lib/colores.js'
import { fmtEntero, fmt1, fmtDistancia } from '../../lib/formato.js'
import s from './CapaHotspots.module.css'

const anillos = (geom) =>
  geom.type === 'Polygon'
    ? geom.coordinates.map((a) => a.map(([lon, lat]) => [lat, lon]))
    : geom.coordinates.map((p) => p.map((a) => a.map(([lon, lat]) => [lat, lon])))

/** Ícono de estación: círculo blanco con aro de color y el número del hotspot */
export function iconoEstacion({
  etiqueta,
  color = SENAL,
  activa = false,
  tenue = false,
  conCodigo = false,
  codigo,
  tam = 24,
}) {
  return L.divIcon({
    className: 'ttr-icono-limpio',
    iconSize: [tam, tam],
    iconAnchor: [tam / 2, tam / 2],
    popupAnchor: [0, -tam / 2],
    html: `<div class="ttr-estacion" style="--c:${color};--tc:${textoSobre(color)}" data-activa="${activa}" data-tenue="${tenue}">${String(etiqueta).padStart(2, '0')}${
      conCodigo ? `<span class="ttr-etiqueta">${codigo}</span>` : ''
    }</div>`,
  })
}

/**
 * Hotspots del análisis: área (polígono) + estación en el centroide con su etiqueta.
 * grafoDe: Map id_hotspot → { numero, color } cuando ya existe una partición.
 */
export default function CapaHotspots({ hotspots, grafoDe, seleccionado, alSeleccionar, mostrarAreas = true }) {
  const map = useMap()
  const [zoom, setZoom] = useState(map.getZoom())
  useMapEvents({ zoomend: () => setZoom(map.getZoom()) })
  const refs = useRef(new Map())

  // Al elegir desde la lista se abre la ficha del hotspot
  useEffect(() => {
    if (seleccionado == null) return
    const m = refs.current.get(seleccionado)
    if (m) m.openPopup()
  }, [seleccionado])

  const conCodigo = zoom >= 14
  const tam = zoom >= 14 ? 26 : zoom >= 13 ? 24 : 20

  const features = hotspots?.features ?? []
  const estilos = useMemo(
    () =>
      new Map(
        features.map((f) => {
          const g = grafoDe?.get(f.properties.id_hotspot)
          const color = g?.color ?? SENAL
          return [f.properties.id_hotspot, { color, g }]
        }),
      ),
    [features, grafoDe],
  )

  return (
    <>
      {mostrarAreas &&
        features.map((f) => {
          const p = f.properties
          const { color } = estilos.get(p.id_hotspot)
          const activo = seleccionado === p.id_hotspot
          return (
            <Polygon
              key={`a-${p.id_hotspot}`}
              pane="hotspots"
              positions={anillos(f.geometry)}
              pathOptions={{
                color,
                weight: activo ? 3 : 1.6,
                opacity: 0.95,
                fillColor: color,
                fillOpacity: activo ? 0.3 : 0.16,
              }}
              eventHandlers={{ click: () => alSeleccionar?.(p.id_hotspot) }}
            >
              <Tooltip sticky className="ttr-tooltip" direction="top" offset={[0, -6]}>
                {p.codigo}
                {p.colonia ? ` · ${p.colonia}` : ''}
              </Tooltip>
            </Polygon>
          )
        })}
      {features.map((f) => {
        const p = f.properties
        const { color, g } = estilos.get(p.id_hotspot)
        const [lon, lat] = p.centroide
        return (
          <Marker
            key={`m-${p.id_hotspot}`}
            position={[lat, lon]}
            ref={(m) => {
              if (m) refs.current.set(p.id_hotspot, m)
              else refs.current.delete(p.id_hotspot)
            }}
            icon={iconoEstacion({
              etiqueta: p.etiqueta,
              codigo: p.codigo,
              color,
              activa: seleccionado === p.id_hotspot,
              conCodigo,
              tam,
            })}
            keyboard
            title={`${p.codigo}${p.colonia ? `, ${p.colonia}` : ''}`}
            alt={`Hotspot ${p.codigo}`}
            eventHandlers={{
              click: () => alSeleccionar?.(p.id_hotspot),
              popupclose: () => {
                if (seleccionado === p.id_hotspot) alSeleccionar?.(null)
              },
            }}
          >
            <Popup className="ttr-popup" closeButton autoPanPadding={[40, 40]}>
              <FichaHotspot p={p} grafo={g} color={color} />
            </Popup>
          </Marker>
        )
      })}
    </>
  )
}

export function FichaHotspot({ p, grafo, color = SENAL }) {
  return (
    <div className={s.ficha}>
      <div className={s.fichaCabeza} style={{ background: conAlfa(color, 0.1) }}>
        <span className={s.fichaCodigo} style={{ borderColor: color }}>
          {String(p.etiqueta).padStart(2, '0')}
        </span>
        <div>
          <p className={s.fichaTitulo}>{p.codigo}</p>
          <p className={s.fichaSub}>{p.colonia ?? 'Sin colonia registrada'}</p>
        </div>
      </div>
      <dl className={s.fichaDatos}>
        <div>
          <dt>Puntos</dt>
          <dd className="num">{fmtEntero(p.n_puntos)}</dd>
        </div>
        <div>
          <dt>Gravedad media</dt>
          <dd>
            <span className="num">{fmt1(p.indice_gravedad)}</span>{' '}
            <span className={s.fichaNivel}>{nombreGravedad(p.indice_gravedad)}</span>
          </dd>
        </div>
        <div>
          <dt>Radio</dt>
          <dd className="num">{fmtDistancia(p.radio_m, { decimales: 1 })}</dd>
        </div>
        {grafo && (
          <div>
            <dt>Grafo</dt>
            <dd>
              <span className={s.fichaGrafo} style={{ background: grafo.color, color: textoSobre(grafo.color) }}>
                {grafo.numero}
              </span>
            </dd>
          </div>
        )}
      </dl>
      <p className={s.fichaDelito}>
        <span>Delito más frecuente</span>
        {p.delito_predominante}
      </p>
    </div>
  )
}
