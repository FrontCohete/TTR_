import { motion } from 'motion/react'
import { Check, LoaderCircle } from 'lucide-react'
import { fmtEntero } from '../../lib/formato.js'
import s from './Inicio.module.css'

const ETAPAS = [
  { clave: 'limpieza', nombre: 'Limpieza', detalle: 'Se descartan filas sin coordenadas o fuera de GAM' },
  { clave: 'insercion', nombre: 'Inserción', detalle: 'Los puntos nuevos se guardan en la base' },
  { clave: 'hdbscan', nombre: 'HDBSCAN', detalle: 'Se recalculan los hotspots con todos los puntos' },
]

/** Avance de la ingesta y del clustering (GET /api/cargas/{id}, cada segundo) */
export default function ProgresoProceso({ carga, nombre }) {
  const completado = carga?.estado === 'completado'
  const indice = completado
    ? ETAPAS.length
    : Math.max(
        0,
        ETAPAS.findIndex((e) => e.clave === carga?.etapa),
      )
  const avance = completado ? 100 : (carga?.avance ?? 0)

  return (
    <section className={s.proceso} aria-labelledby="titulo-proceso">
      <div className={s.procesoCabeza}>
        <h2 id="titulo-proceso" className={s.h2}>
          {completado ? 'Análisis listo' : 'Procesando dataset'}
        </h2>
        <p className={s.subtexto}>{nombre}</p>
      </div>

      <ol className={s.procesoLinea}>
        {ETAPAS.map((e, i) => {
          const estado = i < indice ? 'hecha' : i === indice ? 'actual' : 'pendiente'
          return (
            <li key={e.clave} className={s.procesoParada} data-estado={estado}>
              <span className={s.procesoEstacion} aria-hidden="true">
                {estado === 'hecha' && <Check size={14} strokeWidth={3} />}
                {estado === 'actual' && <LoaderCircle size={14} strokeWidth={3} className={s.giro} />}
              </span>
              <span className={s.procesoNombre}>{e.nombre}</span>
              <span className={s.procesoDetalle}>{e.detalle}</span>
              <span className="solo-lectores">
                {estado === 'hecha' ? 'terminada' : estado === 'actual' ? 'en curso' : 'pendiente'}
              </span>
            </li>
          )
        })}
      </ol>

      <div
        className={s.procesoBarra}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={avance}
        aria-label="Avance del procesamiento"
      >
        <motion.span
          className={s.procesoRelleno}
          initial={false}
          animate={{ scaleX: avance / 100 }}
          transition={{ duration: 0.6, ease: [0.2, 0, 0, 1] }}
        />
      </div>
      <dl className={s.procesoDatos}>
        <div>
          <dt>Avance</dt>
          <dd className="num">{avance}%</dd>
        </div>
        <div>
          <dt>Puntos nuevos de GAM</dt>
          <dd className="num">{fmtEntero(carga?.puntos_gam_nuevos ?? 0)}</dd>
        </div>
        <div>
          <dt>Duplicados descartados</dt>
          <dd className="num">{fmtEntero(carga?.puntos_duplicados ?? 0)}</dd>
        </div>
      </dl>
    </section>
  )
}
