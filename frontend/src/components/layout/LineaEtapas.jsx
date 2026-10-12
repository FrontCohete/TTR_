import { NavLink, useLocation } from 'react-router'
import { motion } from 'motion/react'
import { useSesion } from '../../store/sesion.js'
import { useAnalisisVigente } from '../../api/consultas.js'
import s from './LineaEtapas.module.css'

export const ETAPAS = [
  { ruta: '/', nombre: 'Inicio' },
  { ruta: '/analizar', nombre: 'Analizar' },
  { ruta: '/rutas', nombre: 'Rutas' },
  { ruta: '/simular', nombre: 'Simular' },
]

/**
 * Navegación principal dibujada como una línea de transporte:
 * cada vista es una estación y el tramo recorrido se pinta en rojo señal.
 * Las estaciones se bloquean hasta que existe lo que necesitan.
 */
export default function LineaEtapas() {
  const { pathname } = useLocation()
  const procesando = useSesion((st) => st.idCargaEnProceso != null)
  const hayAgentes = useSesion((st) => st.ejecuciones.length > 0)
  const analisis = useAnalisisVigente()
  const hayAnalisis = !!analisis.data

  const actual = Math.max(
    0,
    ETAPAS.findIndex((e) => (e.ruta === '/' ? pathname === '/' : pathname.startsWith(e.ruta))),
  )

  const motivo = (i) => {
    if (i === 0) return null
    if (procesando) return 'Espera a que termine el procesamiento del dataset'
    if (i === 1 && !hayAnalisis) return 'Carga un dataset para generar el primer análisis'
    if (i >= 2 && !hayAgentes) return 'Genera agentes desde Analizar'
    return null
  }

  const avance = actual / (ETAPAS.length - 1)

  return (
    <nav className={s.nav} aria-label="Etapas del análisis">
      <div className={s.contenedor}>
        <span className={s.via} aria-hidden="true">
          <motion.span
            className={s.recorrido}
            initial={false}
            animate={{ scaleX: avance }}
            transition={{ duration: 0.42, ease: [0.2, 0, 0, 1] }}
          />
        </span>
        <ol className={s.linea}>
          {ETAPAS.map((e, i) => {
            const bloqueo = motivo(i)
            const estado = i < actual ? 'pasada' : i === actual ? 'actual' : 'futura'
            const interior = (
              <>
                <span className={s.estacion} aria-hidden="true" />
                <span className={s.nombre}>{e.nombre}</span>
              </>
            )
            return (
              <li key={e.ruta} className={s.parada} data-estado={estado}>
                {bloqueo ? (
                  <span className={`${s.enlace} ${s.bloqueado}`} aria-disabled="true" title={bloqueo}>
                    {interior}
                    <span className="solo-lectores">({bloqueo})</span>
                  </span>
                ) : (
                  <NavLink
                    to={e.ruta}
                    end={e.ruta === '/'}
                    className={s.enlace}
                    aria-current={i === actual ? 'page' : undefined}
                  >
                    {interior}
                  </NavLink>
                )}
              </li>
            )
          })}
        </ol>
      </div>
    </nav>
  )
}
