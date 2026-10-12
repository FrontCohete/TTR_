import { CircleAlert, CircleCheck, Info, TriangleAlert } from 'lucide-react'
import s from './Aviso.module.css'

const ICONOS = { info: Info, ok: CircleCheck, aviso: TriangleAlert, error: CircleAlert }
const CLASES = { info: 'info', ok: 'ok', aviso: 'advertencia', error: 'error' }

/** Mensaje en línea. Siempre lleva ícono + texto: el color nunca va solo. */
export default function Aviso({ tipo = 'info', titulo, children, accion, className = '', compacto = false }) {
  const Icono = ICONOS[tipo]
  return (
    <div
      className={`${s.caja} ${s[CLASES[tipo]]} ${compacto ? s.compacto : ''} ${className}`}
      role={tipo === 'error' ? 'alert' : 'status'}
    >
      <Icono size={18} className={s.icono} aria-hidden="true" />
      <div className={s.cuerpo}>
        {titulo && <p className={s.titulo}>{titulo}</p>}
        {children && <div className={s.texto}>{children}</div>}
      </div>
      {accion && <div className={s.accion}>{accion}</div>}
    </div>
  )
}
