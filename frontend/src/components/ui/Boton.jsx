import { Link } from 'react-router'
import { LoaderCircle } from 'lucide-react'
import s from './Boton.module.css'

/**
 * Botón de TTR_.
 * variante: "primario" (acción principal, rojo señal) · "secundario" · "fantasma" · "oscuro" (sobre cromo)
 * tamano: "s" (32 px) · "m" (40 px) · "l" (48 px)
 * Con `a` se comporta como enlace interno (React Router).
 */
export default function Boton({
  variante = 'secundario',
  tamano = 'm',
  icono: Icono,
  iconoDerecha: IconoDerecha,
  cargando = false,
  soloIcono = false,
  anchoCompleto = false,
  a,
  className = '',
  children,
  disabled,
  ref,
  ...resto
}) {
  const clases = [
    s.boton,
    s[variante],
    s[`t${tamano}`],
    soloIcono ? s.soloIcono : '',
    anchoCompleto ? s.ancho : '',
    cargando ? s.cargando : '',
    className,
  ].join(' ')
  const tamIcono = tamano === 's' ? 16 : 18
  const contenido = (
    <>
      {cargando ? (
        <LoaderCircle size={tamIcono} className={s.giro} aria-hidden="true" />
      ) : (
        Icono && <Icono size={tamIcono} aria-hidden="true" strokeWidth={2} />
      )}
      {children && <span className={soloIcono ? 'solo-lectores' : s.texto}>{children}</span>}
      {IconoDerecha && !cargando && <IconoDerecha size={tamIcono} aria-hidden="true" strokeWidth={2} />}
    </>
  )
  if (a && !disabled) {
    return (
      <Link ref={ref} to={a} className={clases} {...resto}>
        {contenido}
      </Link>
    )
  }
  return (
    <button
      ref={ref}
      type="button"
      className={clases}
      disabled={disabled || cargando}
      aria-busy={cargando || undefined}
      {...resto}
    >
      {contenido}
    </button>
  )
}
