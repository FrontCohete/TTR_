import { useCallback, useEffect, useRef, useState } from 'react'
import { VELOCIDADES, anterior, finDeGeneracion, siguiente } from './etapas.js'

/**
 * Reproductor del algoritmo genético: como un video que avanza etapa por etapa.
 * El backend ya ejecutó todo; aquí solo se decide qué generación y qué etapa se muestran.
 *
 * Modos: "paso" (manual), "lenta", "normal" y "auto" (recorre generación por generación).
 */
export function useReproductor(totalGeneraciones, clave) {
  const [posiciones, setPosiciones] = useState({})
  const [modo, setModo] = useState('paso')
  const [reproduciendo, setReproduciendo] = useState(false)
  const pos = posiciones[clave] ?? { gen: 0, etapa: 0 }
  const refPos = useRef(pos)
  refPos.current = pos

  const ir = useCallback((nueva) => setPosiciones((p) => ({ ...p, [clave]: nueva })), [clave])

  const avanzar = useCallback(() => {
    const total = totalGeneraciones ?? 0
    const actual = refPos.current
    let nueva
    if (modo === 'auto') {
      // En automático se salta de evaluación en evaluación: una generación por cuadro
      if (actual.gen === 0 && actual.etapa === 0) nueva = { gen: 0, etapa: 1 }
      else if (actual.gen === 0) nueva = total >= 1 ? finDeGeneracion(1) : null
      else if (actual.etapa !== 6) nueva = finDeGeneracion(actual.gen)
      else nueva = actual.gen < total ? finDeGeneracion(actual.gen + 1) : null
    } else {
      nueva = siguiente(actual, total)
    }
    if (nueva) ir(nueva)
    return !!nueva
  }, [ir, modo, totalGeneraciones])

  const retroceder = useCallback(() => {
    const nueva = anterior(refPos.current)
    if (nueva) ir(nueva)
  }, [ir])

  // Temporizador de reproducción
  useEffect(() => {
    if (!reproduciendo) return
    const ms = VELOCIDADES[modo].ms
    if (!ms) {
      setReproduciendo(false)
      return
    }
    const t = setTimeout(() => {
      if (!avanzar()) setReproduciendo(false)
    }, ms)
    return () => clearTimeout(t)
  }, [reproduciendo, modo, pos, avanzar])

  // Al cambiar de agente se pausa
  useEffect(() => {
    setReproduciendo(false)
  }, [clave])

  const total = totalGeneraciones ?? 0
  const alFinal = pos.gen >= total && pos.etapa === (total === 0 ? 1 : 6)
  const alInicio = pos.gen === 0 && pos.etapa === 0

  return {
    pos,
    modo,
    reproduciendo,
    alFinal,
    alInicio,
    cambiarModo: (m) => {
      setModo(m)
      if (m === 'paso') setReproduciendo(false)
    },
    alternar: () => {
      if (alFinal) {
        ir({ gen: 0, etapa: 0 })
        setReproduciendo(true)
        return
      }
      setReproduciendo((v) => !v)
    },
    pausar: () => setReproduciendo(false),
    pasoSiguiente: () => {
      setReproduciendo(false)
      siguienteManual()
    },
    pasoAnterior: () => {
      setReproduciendo(false)
      retroceder()
    },
    reiniciar: () => {
      setReproduciendo(false)
      ir({ gen: 0, etapa: 0 })
    },
    irAlFinal: () => {
      setReproduciendo(false)
      ir(finDeGeneracion(total))
    },
    irAGeneracion: (g) => ir(finDeGeneracion(Math.max(0, Math.min(total, g)))),
    irAEtapa: (etapa) => {
      setReproduciendo(false)
      const g = refPos.current.gen
      if (etapa <= 1) ir({ gen: 0, etapa })
      else ir({ gen: Math.max(1, g), etapa })
    },
  }

  function siguienteManual() {
    const nueva = siguiente(refPos.current, total)
    if (nueva) ir(nueva)
  }
}
