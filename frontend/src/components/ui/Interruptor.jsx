import { useId } from 'react'
import s from './Interruptor.module.css'

/** Interruptor encendido/apagado con etiqueta y descripción opcional */
export default function Interruptor({ activo, alCambiar, etiqueta, descripcion, muestra, deshabilitado = false }) {
  const id = useId()
  return (
    <label className={`${s.fila} ${deshabilitado ? s.deshabilitado : ''}`} htmlFor={id}>
      {muestra && (
        <span className={s.muestra} aria-hidden="true">
          {muestra}
        </span>
      )}
      <span className={s.textos}>
        <span className={s.etiqueta}>{etiqueta}</span>
        {descripcion && <span className={s.descripcion}>{descripcion}</span>}
      </span>
      <span className={s.control}>
        <input
          id={id}
          type="checkbox"
          role="switch"
          checked={activo}
          disabled={deshabilitado}
          onChange={(e) => alCambiar(e.target.checked)}
          className={s.input}
        />
        <span className={s.pista} aria-hidden="true">
          <span className={s.perilla} />
        </span>
      </span>
    </label>
  )
}
