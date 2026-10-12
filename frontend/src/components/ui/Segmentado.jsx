import { useId, useRef } from 'react'
import { motion } from 'motion/react'
import s from './Segmentado.module.css'

/**
 * Control segmentado (grupo de opciones excluyentes) accesible con teclado.
 * opciones: [{ valor, etiqueta, icono?, descripcion?, deshabilitada? }]
 */
export default function Segmentado({
  opciones,
  valor,
  alCambiar,
  etiqueta,
  oscuro = false,
  tamano = 'm',
  anchoCompleto = false,
}) {
  const id = useId()
  const refs = useRef([])
  const indice = opciones.findIndex((o) => o.valor === valor)

  const mover = (dir) => {
    const n = opciones.length
    let i = indice
    for (let k = 0; k < n; k++) {
      i = (i + dir + n) % n
      if (!opciones[i].deshabilitada) break
    }
    alCambiar(opciones[i].valor)
    refs.current[i]?.focus()
  }

  return (
    <div
      role="radiogroup"
      aria-label={etiqueta}
      className={`${s.grupo} ${oscuro ? s.oscuro : ''} ${s[`t${tamano}`]} ${anchoCompleto ? s.ancho : ''}`}
      onKeyDown={(e) => {
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
          e.preventDefault()
          mover(1)
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
          e.preventDefault()
          mover(-1)
        }
      }}
    >
      {opciones.map((o, i) => {
        const activo = o.valor === valor
        const Icono = o.icono
        return (
          <button
            key={String(o.valor)}
            ref={(el) => (refs.current[i] = el)}
            type="button"
            role="radio"
            aria-checked={activo}
            tabIndex={activo ? 0 : -1}
            disabled={o.deshabilitada}
            title={o.descripcion}
            className={`${s.opcion} ${activo ? s.activa : ''}`}
            onClick={() => alCambiar(o.valor)}
          >
            {activo && (
              <motion.span
                layoutId={`seg-${id}`}
                className={s.indicador}
                transition={{ type: 'spring', stiffness: 520, damping: 40 }}
              />
            )}
            <span className={s.contenido}>
              {Icono && <Icono size={tamano === 's' ? 14 : 16} aria-hidden="true" />}
              {o.etiqueta}
            </span>
          </button>
        )
      })}
    </div>
  )
}
