import { useId, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import s from './Seccion.module.css'

/** Bloque de un panel con título. Si `plegable`, el título abre y cierra el contenido. */
export default function Seccion({
  titulo,
  icono: Icono,
  accion,
  children,
  plegable = false,
  abiertaInicial = true,
  nota,
}) {
  const [abierta, setAbierta] = useState(abiertaInicial)
  const id = useId()
  const encabezado = (
    <>
      {Icono && <Icono size={16} aria-hidden="true" className={s.icono} />}
      <span className={s.titulo}>{titulo}</span>
      {nota && <span className={s.nota}>{nota}</span>}
    </>
  )
  return (
    <section className={s.seccion} aria-labelledby={`${id}-t`}>
      <div className={s.cabeza}>
        {plegable ? (
          <button
            type="button"
            id={`${id}-t`}
            className={s.alternar}
            aria-expanded={abierta}
            aria-controls={`${id}-c`}
            onClick={() => setAbierta((v) => !v)}
          >
            {encabezado}
            <ChevronDown size={16} aria-hidden="true" className={`${s.chevron} ${abierta ? s.girado : ''}`} />
          </button>
        ) : (
          <h2 id={`${id}-t`} className={s.h}>
            {encabezado}
          </h2>
        )}
        {accion && <div className={s.accion}>{accion}</div>}
      </div>
      {plegable ? (
        <AnimatePresence initial={false}>
          {abierta && (
            <motion.div
              id={`${id}-c`}
              key="c"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.24, ease: [0.2, 0, 0, 1] }}
              className={s.plegado}
            >
              <div className={s.cuerpo}>{children}</div>
            </motion.div>
          )}
        </AnimatePresence>
      ) : (
        <div className={s.cuerpo}>{children}</div>
      )}
    </section>
  )
}
