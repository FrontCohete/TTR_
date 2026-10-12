import { useMemo, useState } from 'react'
import { fmtDistancia } from '../../lib/formato.js'
import s from './Rutas.module.css'

/**
 * Distancia de cada individuo de la población, una barra por individuo.
 * Más baja = mejor ruta. La mejor se pinta en rojo señal; las resaltadas, en el color del agente.
 */
export default function BarrasAptitud({
  individuos,
  color,
  resaltadas,
  alto = 120,
  titulo = 'Distancia de cada ruta de la población',
}) {
  const [sobre, setSobre] = useState(null)
  const datos = useMemo(() => {
    if (!individuos?.length) return null
    let min = Infinity
    let max = -Infinity
    let mejor = 0
    individuos.forEach((ind, i) => {
      if (ind.distancia < min) {
        min = ind.distancia
        mejor = i
      }
      if (ind.distancia > max) max = ind.distancia
    })
    const base = min * 0.86
    return { min, max, base, mejor }
  }, [individuos])

  if (!datos) return null
  const n = individuos.length
  const ancho = 100 / n
  const actual = sobre != null ? individuos[sobre] : individuos[datos.mejor]

  return (
    <figure className={s.barras}>
      <figcaption className={s.barrasTitulo}>
        <span>{titulo}</span>
        <span className={s.barrasDato}>
          {sobre != null ? `Ruta #${actual.posicion}` : `Mejor ruta #${actual.posicion}`}:{' '}
          {fmtDistancia(actual.distancia)}
        </span>
      </figcaption>
      <div className={s.barrasArea} style={{ height: alto }} onMouseLeave={() => setSobre(null)}>
        <span className={s.barrasEje}>
          <span>{fmtDistancia(datos.max, { decimales: 1 })}</span>
          <span>{fmtDistancia(datos.base, { decimales: 1 })}</span>
        </span>
        <svg
          viewBox={`0 0 100 100`}
          preserveAspectRatio="none"
          className={s.barrasSvg}
          role="img"
          aria-label={`${titulo}. Mejor ${fmtDistancia(datos.min)}, peor ${fmtDistancia(datos.max)}.`}
        >
          {individuos.map((ind, i) => {
            const h = ((ind.distancia - datos.base) / (datos.max - datos.base || 1)) * 96 + 4
            const esMejor = i === datos.mejor
            const marcada = resaltadas?.has(i)
            const relleno = esMejor ? 'var(--senal)' : marcada ? color : 'rgba(52,55,76,0.32)'
            return (
              <rect
                key={i}
                x={i * ancho + ancho * 0.14}
                y={100 - h}
                width={ancho * 0.72}
                height={h}
                rx={0.6}
                fill={relleno}
                opacity={sobre != null && sobre !== i ? 0.55 : 1}
                onMouseEnter={() => setSobre(i)}
              />
            )
          })}
        </svg>
      </div>
    </figure>
  )
}
