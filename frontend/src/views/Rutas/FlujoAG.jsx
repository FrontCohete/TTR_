import { motion } from 'motion/react'
import { Check, LoaderCircle, Repeat } from 'lucide-react'
import { ETAPAS_AG, PRIMERA_ETAPA_CICLO } from './etapas.js'
import { fmtEntero } from '../../lib/formato.js'
import s from './Rutas.module.css'

/**
 * Flujo del algoritmo como una ejecución de Power Automate:
 * tarjetas de acción unidas por conectores, y un contenedor "Para cada generación"
 * que repite las etapas 3 a 7. La etapa activa se ilumina.
 */
export default function FlujoAG({ pos, total, metas, reproduciendo, alElegir, horizontal = false }) {
  const estadoDe = (i) => {
    if (pos.gen === 0) return i < pos.etapa ? 'hecha' : i === pos.etapa ? 'activa' : 'pendiente'
    if (i < PRIMERA_ETAPA_CICLO) return 'hecha'
    return i < pos.etapa ? 'hecha' : i === pos.etapa ? 'activa' : 'pendiente'
  }

  const tarjeta = (i) => {
    const e = ETAPAS_AG[i]
    const estado = estadoDe(i)
    const Icono = e.icono
    return (
      <li key={e.clave} className={s.pasoLi}>
        <button
          type="button"
          className={s.paso}
          data-estado={estado}
          aria-current={estado === 'activa' ? 'step' : undefined}
          onClick={() => alElegir(i)}
        >
          {estado === 'activa' && (
            <motion.span
              layoutId="flujo-activo"
              className={s.pasoResalte}
              transition={{ type: 'spring', stiffness: 500, damping: 42 }}
            />
          )}
          <span className={s.pasoIcono} aria-hidden="true">
            <Icono size={horizontal ? 15 : 17} />
          </span>
          <span className={s.pasoTextos}>
            <span className={s.pasoNombre}>
              <span className={s.pasoNumero}>{i + 1}</span>
              {horizontal ? e.corto : e.nombre}
            </span>
            {!horizontal && metas?.[i] && <span className={s.pasoMeta}>{metas[i]}</span>}
          </span>
          <span className={s.pasoEstado} aria-hidden="true">
            {estado === 'hecha' && <Check size={13} strokeWidth={3} />}
            {estado === 'activa' && reproduciendo && <LoaderCircle size={14} strokeWidth={2.5} className={s.giro} />}
          </span>
          <span className="solo-lectores">
            {estado === 'hecha' ? '(completada)' : estado === 'activa' ? '(en curso)' : '(pendiente)'}
          </span>
        </button>
      </li>
    )
  }

  if (horizontal) {
    return (
      <nav className={s.flujoHorizontal} aria-label="Etapas del algoritmo genético">
        <ol>{ETAPAS_AG.map((_, i) => tarjeta(i))}</ol>
      </nav>
    )
  }

  return (
    <nav className={s.flujo} aria-label="Etapas del algoritmo genético">
      <ol className={s.flujoLista}>
        {tarjeta(0)}
        <li className={s.conector} aria-hidden="true" />
        {tarjeta(1)}
        <li className={s.conector} aria-hidden="true" />
      </ol>
      <div className={s.ciclo} data-activo={pos.gen > 0}>
        <div className={s.cicloCabeza}>
          <Repeat size={15} aria-hidden="true" />
          <span>Para cada generación</span>
          <span className={s.cicloContador}>
            {pos.gen > 0 ? `${fmtEntero(pos.gen)} de ${fmtEntero(total)}` : `1 a ${fmtEntero(total)}`}
          </span>
        </div>
        <ol className={s.flujoLista}>
          {[2, 3, 4, 5, 6].map((i, k) => [
            k > 0 && <li key={`c${i}`} className={s.conector} aria-hidden="true" />,
            tarjeta(i),
          ])}
        </ol>
        <p className={s.cicloPie}>
          <Repeat size={13} aria-hidden="true" /> La generación nueva reemplaza a la anterior y el ciclo se repite.
        </p>
      </div>
    </nav>
  )
}
