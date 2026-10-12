import { LoaderCircle } from 'lucide-react'

/** Indicador mientras se descarga el código de una vista */
export default function CargandoVista({ texto = 'Abriendo vista…' }) {
  return (
    <div
      role="status"
      style={{
        display: 'grid',
        placeItems: 'center',
        height: '100%',
        color: 'var(--texto-3)',
        gap: 8,
        alignContent: 'center',
        fontSize: 'var(--t-s)',
      }}
    >
      <LoaderCircle size={22} style={{ animation: 'girar-vista 0.9s linear infinite' }} aria-hidden="true" />
      <span>{texto}</span>
      <style>{'@keyframes girar-vista{to{transform:rotate(360deg)}}'}</style>
    </div>
  )
}
