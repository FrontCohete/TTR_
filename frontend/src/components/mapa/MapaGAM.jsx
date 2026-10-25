import { useEffect, useMemo, useRef, useState } from 'react'
import { GeoJSON, MapContainer, Pane, Polygon, ScaleControl, TileLayer, ZoomControl, useMap } from 'react-leaflet'
import { useColonias } from '../../api/consultas.js'
import { ENCUADRE_GAM, limitesLeaflet } from '../../lib/geo.js'
import { NOCHE } from '../../lib/colores.js'

// La clave de CARTO vive en frontend/.env (VITE_CARTO_KEY=...), que no se sube a Git.
// Sin clave se usan las teselas estándar de OpenStreetMap, que no la piden.
const CLAVE_CARTO = import.meta.env.VITE_CARTO_KEY
const TESELAS = CLAVE_CARTO
  ? `https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png?key=${CLAVE_CARTO}`
  : 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATRIBUCION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'

/** Rectángulo que cubre el mundo, para oscurecer todo lo que no es GAM */
const MUNDO = [
  [-85, -180],
  [85, -180],
  [85, 180],
  [-85, 180],
]

/**
 * Mapa base de Gustavo A. Madero.
 * - Teselas CARTO Voyager (con la clave de frontend/.env) u OpenStreetMap si no hay clave.
 * - Si no hay internet, dibuja las colonias como mapa base de respaldo.
 * - Oscurece el exterior de GAM y traza el contorno oficial.
 * Las capas de datos se pasan como hijos.
 */
export default function MapaGAM({
  limite,
  children,
  alListo,
  relleno = [24, 24],
  rellenoInferior = 0,
  interactivo = true,
  className,
  zoomMinimo = 11,
  mostrarEscala = true,
  mostrarZoom = true,
  ajustarAlCambiar,
  encuadre,
  rueda = true,
}) {
  const [sinTeselas, setSinTeselas] = useState(false)
  const conteo = useRef({ errores: 0, cargas: 0 })
  const coloniasBase = useColonias(sinTeselas)

  const limites = useMemo(() => (limite ? limitesLeaflet(limite) : ENCUADRE_GAM), [limite])
  const claveEncuadre = encuadre ? encuadre.flat().join(',') : null
  const ajuste = useMemo(() => encuadre ?? limites, [claveEncuadre, limites]) // eslint-disable-line react-hooks/exhaustive-deps
  const hueco = useMemo(() => {
    if (!limite?.features?.length) return null
    return limite.features[0].geometry.coordinates[0].map(([lon, lat]) => [lat, lon])
  }, [limite])

  return (
    <MapContainer
      bounds={ajuste}
      boundsOptions={{ padding: relleno }}
      zoomControl={false}
      attributionControl
      minZoom={zoomMinimo}
      maxZoom={18}
      zoomSnap={0.25}
      zoomDelta={0.5}
      wheelPxPerZoomLevel={90}
      maxBounds={[
        [limites[0][0] - 0.12, limites[0][1] - 0.16],
        [limites[1][0] + 0.12, limites[1][1] + 0.16],
      ]}
      maxBoundsViscosity={0.8}
      dragging={interactivo}
      scrollWheelZoom={interactivo && rueda}
      doubleClickZoom={interactivo}
      touchZoom={interactivo}
      boxZoom={interactivo}
      keyboard={interactivo}
      className={className}
      style={{ height: '100%', width: '100%' }}
    >
      <Ajustar
        limites={ajuste}
        relleno={relleno}
        rellenoInferior={rellenoInferior}
        clave={ajustarAlCambiar}
        alListo={alListo}
      />
      {!sinTeselas && (
        <TileLayer
          url={TESELAS}
          attribution={ATRIBUCION}
          subdomains="abcd"
          maxZoom={19}
          className="ttr-teselas"
          eventHandlers={{
            tileload: () => {
              conteo.current.cargas += 1
            },
            tileerror: () => {
              conteo.current.errores += 1
              if (conteo.current.errores >= 6 && conteo.current.cargas === 0) setSinTeselas(true)
            },
          }}
        />
      )}
      <Pane name="base" style={{ zIndex: 300 }}>
        {sinTeselas && coloniasBase.data && (
          <GeoJSON
            data={coloniasBase.data}
            interactive={false}
            style={{ color: '#ffffff', weight: 1.2, fillColor: '#ECEAE5', fillOpacity: 1 }}
          />
        )}
      </Pane>
      <Pane name="velo" style={{ zIndex: 340 }}>
        {hueco && (
          <Polygon
            positions={[MUNDO, hueco]}
            interactive={false}
            pathOptions={{ stroke: false, fillColor: NOCHE, fillOpacity: 0.3 }}
          />
        )}
      </Pane>
      <Pane name="puntos" style={{ zIndex: 360 }} />
      <Pane name="zonas" style={{ zIndex: 370 }} />
      <Pane name="contorno" style={{ zIndex: 380 }}>
        {hueco && (
          <Polygon
            positions={hueco}
            interactive={false}
            pathOptions={{ color: NOCHE, weight: 2.5, fill: false, opacity: 0.9 }}
          />
        )}
      </Pane>
      <Pane name="hotspots" style={{ zIndex: 400 }} />
      <Pane name="rutas" style={{ zIndex: 450 }} />
      {mostrarZoom && interactivo && <ZoomControl position="bottomright" zoomInTitle="Acercar" zoomOutTitle="Alejar" />}
      {mostrarEscala && <ScaleControl position="bottomleft" imperial={false} />}
      {children}
      {sinTeselas && <AvisoSinTeselas />}
    </MapContainer>
  )
}

/** Encuadra GAM al montar y cuando cambia `clave` o el espacio inferior (hoja en móvil) */
function Ajustar({ limites, relleno, rellenoInferior, clave, alListo }) {
  const map = useMap()
  useEffect(() => {
    alListo?.(map)
  }, [map]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    map.invalidateSize()
    map.fitBounds(limites, {
      paddingTopLeft: [relleno[0], relleno[1]],
      paddingBottomRight: [relleno[0], relleno[1] + rellenoInferior],
      animate: false,
    })
  }, [map, limites, rellenoInferior, clave]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const contenedor = map.getContainer()
    const obs = new ResizeObserver(() => map.invalidateSize({ pan: false }))
    obs.observe(contenedor)
    return () => obs.disconnect()
  }, [map])
  return null
}

function AvisoSinTeselas() {
  const [visible, setVisible] = useState(true)
  useEffect(() => {
    const t = setTimeout(() => setVisible(false), 7000)
    return () => clearTimeout(t)
  }, [])
  if (!visible) return null
  return (
    <div
      className="leaflet-top leaflet-right"
      style={{ pointerEvents: 'none', margin: '10px', maxWidth: 250 }}
      role="status"
    >
      <div
        style={{
          background: 'rgba(44,46,62,0.92)',
          color: 'var(--texto-inv)',
          borderRadius: 'var(--r-s)',
          padding: '6px 10px',
          fontSize: 'var(--t-xs)',
          boxShadow: 'var(--sombra-2)',
        }}
      >
        El mapa de calles no está disponible: se muestran las colonias como mapa base.
      </div>
    </div>
  )
}
