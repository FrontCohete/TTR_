import { Outlet, useLocation } from 'react-router'
import { motion } from 'motion/react'
import { FlaskConical } from 'lucide-react'
import Marca from './Marca.jsx'
import LineaEtapas from './LineaEtapas.jsx'
import { USAR_MOCKS } from '../../api/index.js'
import s from './Marco.module.css'

/** Estructura común: barra superior con la línea de etapas + vista actual */
export default function Marco() {
  const { pathname } = useLocation()
  return (
    <div className={s.marco}>
      <a
        href="#contenido"
        className={s.saltar}
        onClick={(e) => {
          e.preventDefault()
          document.getElementById('contenido')?.focus()
        }}
      >
        Saltar al contenido
      </a>
      <header className={s.barra}>
        <div className={s.izquierda}>
          <Marca />
          <span className={s.lugar}>Gustavo A. Madero</span>
        </div>
        <div className={s.centro}>
          <LineaEtapas />
        </div>
        <div className={s.derecha}>
          {USAR_MOCKS && (
            <span
              className={s.simulado}
              title="La interfaz usa datos de src/mocks. Para conectar el backend, cambia usarDatosSimulados a false en src/config.js."
            >
              <FlaskConical size={14} aria-hidden="true" />
              <span className={s.textoSimulado}>Datos simulados</span>
            </span>
          )}
        </div>
      </header>
      <motion.main
        id="contenido"
        key={pathname}
        className={s.contenido}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.26, ease: [0.2, 0, 0, 1] }}
        tabIndex={-1}
      >
        <Outlet />
      </motion.main>
    </div>
  )
}
