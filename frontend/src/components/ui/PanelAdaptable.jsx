import { useEffect, useRef, useState } from 'react'
import { animate, motion, useDragControls, useMotionValue } from 'motion/react'
import { useEsMovil } from '../../hooks/useMedia.js'
import s from './PanelAdaptable.module.css'

/**
 * Panel de control de las vistas con mapa.
 * - Tableta y escritorio: columna lateral derecha.
 * - Móvil: hoja inferior que se arrastra desde la manija (o se abre con un toque).
 *
 * resumen: lo que se ve con la hoja recogida en móvil (y como encabezado en escritorio)
 * pie: acciones fijas al fondo (botones principales)
 */
export default function PanelAdaptable({ etiqueta, resumen, pie, children, alturaRecogida = 168 }) {
  const esMovil = useEsMovil()
  if (!esMovil) {
    return (
      <aside className={s.lateral} aria-label={etiqueta}>
        <div className={s.desplazable}>
          {resumen && <div className={s.resumen}>{resumen}</div>}
          {children}
        </div>
        {pie && <div className={s.pie}>{pie}</div>}
      </aside>
    )
  }
  return (
    <HojaInferior etiqueta={etiqueta} resumen={resumen} pie={pie} alturaRecogida={alturaRecogida}>
      {children}
    </HojaInferior>
  )
}

function HojaInferior({ etiqueta, resumen, pie, children, alturaRecogida }) {
  const [abierta, setAbierta] = useState(false)
  const [alto, setAlto] = useState(() => Math.round(window.innerHeight * 0.86))
  const controles = useDragControls()
  const y = useMotionValue(0)
  const ref = useRef(null)
  const recogida = Math.max(0, alto - alturaRecogida)

  useEffect(() => {
    const medir = () => setAlto(Math.round(window.innerHeight * 0.86))
    window.addEventListener('resize', medir)
    return () => window.removeEventListener('resize', medir)
  }, [])

  useEffect(() => {
    const ctrl = animate(y, abierta ? 0 : recogida, { type: 'spring', stiffness: 420, damping: 42 })
    // Los controles del mapa se acomodan sobre la hoja recogida (abierta, el mapa queda cubierto)
    document.documentElement.style.setProperty('--hoja-visible', `${alturaRecogida}px`)
    return () => ctrl.stop()
  }, [abierta, recogida, alto, alturaRecogida, y])

  useEffect(() => () => document.documentElement.style.removeProperty('--hoja-visible'), [])

  return (
    <motion.aside
      ref={ref}
      className={s.hoja}
      aria-label={etiqueta}
      style={{ y, height: alto }}
      drag="y"
      dragListener={false}
      dragControls={controles}
      dragConstraints={{ top: 0, bottom: recogida }}
      dragElastic={0.06}
      onDragEnd={(_, info) => {
        const actual = y.get()
        if (info.velocity.y < -300) setAbierta(true)
        else if (info.velocity.y > 300) setAbierta(false)
        else setAbierta(actual < recogida / 2)
        animate(y, actual < recogida / 2 ? 0 : recogida, { type: 'spring', stiffness: 420, damping: 42 })
      }}
    >
      <button
        type="button"
        className={s.manija}
        aria-expanded={abierta}
        aria-label={abierta ? 'Recoger panel' : 'Expandir panel'}
        onPointerDown={(e) => controles.start(e)}
        onClick={() => setAbierta((v) => !v)}
      >
        <span className={s.barra} />
      </button>
      {resumen && <div className={s.resumenHoja}>{resumen}</div>}
      {pie && <div className={s.pieHoja}>{pie}</div>}
      <div className={s.contenidoHoja} aria-hidden={!abierta} inert={!abierta ? true : undefined}>
        {children}
      </div>
    </motion.aside>
  )
}
