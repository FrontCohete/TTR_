import { Fragment } from 'react'
import { motion } from 'motion/react'
import { CornerDownLeft } from 'lucide-react'
import { textoSobre } from '../../lib/colores.js'
import s from './TiraRuta.module.css'

/**
 * Una ruta (permutación) dibujada como el diagrama de una línea de transporte:
 * cada hotspot es una estación y el orden de izquierda a derecha es el orden de visita.
 *
 * origen: por posición, "a" (vino del padre A) o "b" (del padre B) para mostrar el cruce
 * resaltadas: posiciones a marcar (mutación, segmento, etc.)
 * segmento: [c1, c2) posiciones dentro de los puntos de corte
 * tramos: distancias en metros entre estaciones consecutivas (y el regreso si es cerrada)
 */
export default function TiraRuta({
  perm,
  info,
  color = 'var(--ttr-pizarra)',
  origen,
  resaltadas,
  segmento,
  tramos,
  cerrada = false,
  tam = 'm',
  animar = false,
  etiqueta,
  valor,
  tenue = false,
  descripcion,
}) {
  if (!perm) return null
  const enSegmento = (i) => segmento && i >= segmento[0] && i < segmento[1]
  const texto =
    descripcion ??
    `Ruta: ${perm.map((h) => info?.get(h)?.codigo ?? h).join(', ')}${cerrada ? ', y regreso al inicio' : ''}`
  return (
    <div className={`${s.fila} ${s[tam]} ${tenue ? s.tenue : ''}`} style={{ '--c': color, '--tc': textoSobre(color) }}>
      {etiqueta != null && <span className={s.etiqueta}>{etiqueta}</span>}
      <div className={s.desplazable}>
        <ol className={`${s.tira} ${tramos ? s.conTramos : ''}`} aria-label={texto}>
          {perm.map((h, i) => {
            const d = info?.get(h)
            const o = origen?.[i]
            const marcada = resaltadas?.has?.(i)
            return (
              <Fragment key={h}>
                {i > 0 && (
                  <li
                    className={`${s.tramo} ${enSegmento(i) && enSegmento(i - 1) ? s.tramoSegmento : ''}`}
                    aria-hidden="true"
                  >
                    {tramos && <span className={s.km}>{(tramos[i - 1] / 1000).toFixed(1)}</span>}
                  </li>
                )}
                <motion.li
                  layout={animar ? 'position' : false}
                  transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                  className={`${s.estacion} ${o === 'a' ? s.deA : o === 'b' ? s.deB : ''} ${marcada ? s.marcada : ''} ${
                    enSegmento(i) ? s.enSegmento : ''
                  }`}
                  title={d ? `${d.codigo}${d.colonia ? ` · ${d.colonia}` : ''}` : String(h)}
                >
                  {d ? String(d.etiqueta).padStart(2, '0') : h}
                </motion.li>
              </Fragment>
            )
          })}
          {cerrada && perm.length > 1 && (
            <li className={`${s.tramo} ${s.regreso}`} aria-hidden="true">
              {tramos && <span className={s.km}>{(tramos[perm.length - 1] / 1000).toFixed(1)}</span>}
              <CornerDownLeft size={tam === 's' ? 12 : 14} className={s.iconoRegreso} />
            </li>
          )}
        </ol>
      </div>
      {valor != null && <span className={s.valor}>{valor}</span>}
    </div>
  )
}
