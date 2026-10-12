import { Link } from 'react-router'
import s from './Marca.module.css'

/** Logotipo de texto: "TTR" + guion bajo que parpadea como cursor de terminal */
export default function Marca({ tamano = 'm', enlace = true }) {
  const contenido = (
    <span className={`${s.marca} ${s[tamano]}`} aria-label="TTR_">
      <span aria-hidden="true">TTR</span>
      <span className={s.cursor} aria-hidden="true" />
    </span>
  )
  if (!enlace) return contenido
  return (
    <Link to="/" className={s.enlace} aria-label="TTR_, ir a Inicio">
      {contenido}
    </Link>
  )
}
