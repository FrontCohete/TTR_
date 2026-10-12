import { useMemo } from 'react'

/**
 * Silueta de Gustavo A. Madero en SVG (sin mapa base): contorno, colonias y hotspots.
 * Sirve como "placa" de estado en Inicio. Usa las geometrías reales del backend.
 */
export default function SiluetaGAM({ limite, colonias, hotspots, alto = 320, className = '', titulo }) {
  const datos = useMemo(() => {
    if (!limite?.features?.length) return null
    const anillo = limite.features[0].geometry.coordinates[0]
    let minX = Infinity
    let maxX = -Infinity
    let minY = Infinity
    let maxY = -Infinity
    for (const [x, y] of anillo) {
      if (x < minX) minX = x
      if (x > maxX) maxX = x
      if (y < minY) minY = y
      if (y > maxY) maxY = y
    }
    const k = Math.cos(((minY + maxY) / 2) * (Math.PI / 180))
    const escala = 1000 / ((maxX - minX) * k)
    const px = ([x, y]) => [((x - minX) * k * escala).toFixed(1), ((maxY - y) * escala).toFixed(1)]
    const ancho = 1000
    const altoVB = (maxY - minY) * escala
    const ruta = (anillos) => anillos.map((a) => 'M' + a.map((p) => px(p).join(',')).join('L') + 'Z').join('')
    const contorno = ruta([anillo])
    const lineasColonias = colonias?.features
      ? colonias.features
          .map((f) => {
            const g = f.geometry
            const anillos = g.type === 'Polygon' ? g.coordinates : g.coordinates.flat()
            return ruta(anillos)
          })
          .join('')
      : null
    const puntos = (hotspots?.features ?? []).map((f) => {
      const [cx, cy] = px(f.properties.centroide)
      return {
        id: f.properties.id_hotspot,
        cx,
        cy,
        r: 6 + Math.sqrt(f.properties.n_puntos) / 3.2,
        codigo: f.properties.codigo,
      }
    })
    return { ancho, altoVB, contorno, lineasColonias, puntos }
  }, [limite, colonias, hotspots])

  if (!datos) return <div style={{ height: alto }} aria-hidden="true" />
  return (
    <svg
      viewBox={`-12 -12 ${datos.ancho + 24} ${datos.altoVB + 24}`}
      style={{ width: '100%', height: alto }}
      className={className}
      role="img"
      aria-label={titulo ?? `Mapa de Gustavo A. Madero con ${datos.puntos.length} hotspots`}
      preserveAspectRatio="xMidYMid meet"
    >
      <path d={datos.contorno} fill="rgba(255,249,242,0.05)" stroke="none" />
      {datos.lineasColonias && (
        <path d={datos.lineasColonias} fill="none" stroke="rgba(255,249,242,0.16)" strokeWidth="1.1" />
      )}
      <path d={datos.contorno} fill="none" stroke="rgba(255,249,242,0.85)" strokeWidth="3" strokeLinejoin="round" />
      {datos.puntos.map((p) => (
        <circle
          key={p.id}
          cx={p.cx}
          cy={p.cy}
          r={p.r}
          fill="#EE2B47"
          fillOpacity="0.9"
          stroke="#2C2E3E"
          strokeWidth="3"
        >
          <title>{p.codigo}</title>
        </circle>
      ))}
    </svg>
  )
}
