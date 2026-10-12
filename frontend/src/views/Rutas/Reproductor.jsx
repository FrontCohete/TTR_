import { useEffect } from 'react'
import { Pause, Play, RotateCcw, SkipForward, StepBack, StepForward } from 'lucide-react'
import Boton from '../../components/ui/Boton.jsx'
import Segmentado from '../../components/ui/Segmentado.jsx'
import { VELOCIDADES } from './etapas.js'
import { fmtEntero } from '../../lib/formato.js'
import s from './Rutas.module.css'

/**
 * Controles del reproductor: paso a paso, lenta, normal o automático.
 * Teclado: espacio reproduce o pausa; ← y → retroceden o avanzan una etapa.
 */
export default function Reproductor({ r, total, compacto = false }) {
  useEffect(() => {
    const alTeclear = (e) => {
      if (e.target.closest('input, textarea, select, [role="radiogroup"], [role="tablist"]')) return
      if (e.key === ' ' && !e.target.closest('button')) {
        e.preventDefault()
        if (r.modo === 'paso') r.pasoSiguiente()
        else r.alternar()
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        r.pasoSiguiente()
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        r.pasoAnterior()
      }
    }
    window.addEventListener('keydown', alTeclear)
    return () => window.removeEventListener('keydown', alTeclear)
  }, [r])

  const manual = r.modo === 'paso'
  const opciones = Object.entries(VELOCIDADES).map(([valor, v]) => ({ valor, etiqueta: v.etiqueta }))

  return (
    <div className={s.reproductor} role="group" aria-label="Controles de reproducción del algoritmo">
      <div className={s.controles}>
        <Boton
          variante="oscuro"
          soloIcono
          icono={RotateCcw}
          onClick={r.reiniciar}
          disabled={r.alInicio}
          title="Volver a la generación 0"
        >
          Reiniciar
        </Boton>
        <Boton
          variante="oscuro"
          soloIcono
          icono={StepBack}
          onClick={r.pasoAnterior}
          disabled={r.alInicio}
          title="Etapa anterior (←)"
        >
          Etapa anterior
        </Boton>
        {manual ? (
          <Boton
            variante="primario"
            icono={StepForward}
            onClick={r.pasoSiguiente}
            disabled={r.alFinal}
            className={s.botonPrincipal}
            title="Siguiente etapa (→ o espacio)"
          >
            Siguiente paso
          </Boton>
        ) : (
          <Boton
            variante="primario"
            icono={r.reproduciendo ? Pause : Play}
            onClick={r.alternar}
            className={s.botonPrincipal}
            title="Reproducir o pausar (espacio)"
          >
            {r.reproduciendo ? 'Pausar' : r.alFinal ? 'Repetir' : 'Reproducir'}
          </Boton>
        )}
        {!manual && (
          <Boton
            variante="oscuro"
            soloIcono
            icono={StepForward}
            onClick={r.pasoSiguiente}
            disabled={r.alFinal}
            title="Etapa siguiente (→)"
          >
            Etapa siguiente
          </Boton>
        )}
        <Boton
          variante="oscuro"
          soloIcono
          icono={SkipForward}
          onClick={r.irAlFinal}
          disabled={r.alFinal}
          title="Ir a la última generación"
        >
          Ir al final
        </Boton>
      </div>

      <div className={s.velocidad}>
        <span className={s.velocidadEtiqueta} id="etq-velocidad">
          Ejecución
        </span>
        <Segmentado
          etiqueta="Modo de ejecución"
          oscuro
          tamano={compacto ? 's' : 'm'}
          valor={r.modo}
          alCambiar={r.cambiarModo}
          opciones={opciones}
        />
      </div>

      <label className={s.linea}>
        <span className={s.lineaTexto}>
          Generación <strong className="num">{fmtEntero(r.pos.gen)}</strong>
          <span className={s.lineaTotal}> de {fmtEntero(total)}</span>
        </span>
        <input
          type="range"
          min={0}
          max={total}
          step={1}
          value={r.pos.gen}
          onChange={(e) => {
            r.pausar()
            r.irAGeneracion(Number(e.target.value))
          }}
          className={s.deslizador}
          style={{ '--avance': `${total ? (r.pos.gen / total) * 100 : 0}%` }}
          aria-valuetext={`Generación ${r.pos.gen} de ${total}`}
        />
      </label>
    </div>
  )
}
