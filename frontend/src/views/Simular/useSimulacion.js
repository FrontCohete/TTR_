import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { haversine } from '../../lib/geo.js'

/** Duración de la animación a velocidad 1× para la ruta más larga (segundos reales) */
export const DURACION_BASE_S = 24
/** Velocidad supuesta del agente para el reloj simulado (km/h) */
export const VELOCIDAD_KMH = 30

/** Prepara una ruta GeoJSON: distancias acumuladas por vértice */
function preparar(feature) {
  const coords = feature.geometry.coordinates
  const acumulada = [0]
  for (let i = 1; i < coords.length; i++) acumulada.push(acumulada[i - 1] + haversine(coords[i - 1], coords[i]))
  return { coords, acumulada, largo: acumulada[acumulada.length - 1] }
}

/** Posición [lat, lon] a d metros del inicio, y el índice del tramo */
export function posicionEn(ruta, d) {
  const { coords, acumulada, largo } = ruta
  if (d <= 0) return { latlng: [coords[0][1], coords[0][0]], tramo: 0, visitados: 1 }
  if (d >= largo) {
    const u = coords[coords.length - 1]
    return { latlng: [u[1], u[0]], tramo: coords.length - 2, visitados: coords.length, fin: true }
  }
  let k = 0
  while (k < acumulada.length - 2 && acumulada[k + 1] <= d) k++
  const t = (d - acumulada[k]) / (acumulada[k + 1] - acumulada[k] || 1)
  const [x1, y1] = coords[k]
  const [x2, y2] = coords[k + 1]
  return { latlng: [y1 + (y2 - y1) * t, x1 + (x2 - x1) * t], tramo: k, visitados: k + 1 }
}

/**
 * Motor de la simulación: todos los agentes salen juntos y avanzan a la misma velocidad.
 * El cuadro a cuadro (requestAnimationFrame) mueve los marcadores directamente en Leaflet;
 * React solo se actualiza unas 10 veces por segundo para los textos y barras.
 */
export function useSimulacion(rutas, { alTerminarAgente } = {}) {
  const preparadas = useMemo(() => rutas.map((r) => (r ? preparar(r) : null)), [rutas])
  const largoMax = useMemo(() => Math.max(1, ...preparadas.map((p) => p?.largo ?? 0)), [preparadas])

  const [corriendo, setCorriendo] = useState(false)
  const [velocidad, setVelocidad] = useState(1)
  const [recorrido, setRecorrido] = useState(0) // metros recorridos por cada agente
  const refRecorrido = useRef(0)
  const suscriptores = useRef(new Set())
  const terminados = useRef(new Set())
  const refAlTerminar = useRef(alTerminarAgente)
  refAlTerminar.current = alTerminarAgente

  /** Los componentes del mapa se suscriben para moverse en cada cuadro */
  const suscribir = useCallback((fn) => {
    suscriptores.current.add(fn)
    fn(refRecorrido.current)
    return () => suscriptores.current.delete(fn)
  }, [])

  const emitir = useCallback((d) => {
    suscriptores.current.forEach((fn) => fn(d))
  }, [])

  useEffect(() => {
    if (!corriendo) return
    let anterior = performance.now()
    let ultimoEstado = 0
    let id
    const metrosPorSegundo = (largoMax / DURACION_BASE_S) * velocidad
    const cuadro = (ahora) => {
      const dt = Math.min(0.1, (ahora - anterior) / 1000)
      anterior = ahora
      const d = Math.min(largoMax, refRecorrido.current + dt * metrosPorSegundo)
      refRecorrido.current = d
      emitir(d)
      preparadas.forEach((p, i) => {
        if (p && d >= p.largo && !terminados.current.has(i)) {
          terminados.current.add(i)
          refAlTerminar.current?.(i, p.largo, (p.largo / largoMax) * DURACION_BASE_S)
        }
      })
      if (ahora - ultimoEstado > 100 || d >= largoMax) {
        ultimoEstado = ahora
        setRecorrido(d)
      }
      if (d >= largoMax) {
        setCorriendo(false)
        return
      }
      id = requestAnimationFrame(cuadro)
    }
    id = requestAnimationFrame(cuadro)
    return () => cancelAnimationFrame(id)
  }, [corriendo, velocidad, largoMax, preparadas, emitir])

  const reiniciar = useCallback(() => {
    refRecorrido.current = 0
    terminados.current = new Set()
    setRecorrido(0)
    emitir(0)
  }, [emitir])

  const irA = useCallback(
    (fraccion) => {
      const d = Math.max(0, Math.min(1, fraccion)) * largoMax
      refRecorrido.current = d
      setRecorrido(d)
      emitir(d)
    },
    [largoMax, emitir],
  )

  const terminado = recorrido >= largoMax && largoMax > 1
  return {
    preparadas,
    largoMax,
    recorrido,
    progreso: recorrido / largoMax,
    corriendo,
    terminado,
    velocidad,
    setVelocidad,
    alternar: () => {
      if (terminado) {
        reiniciar()
        setCorriendo(true)
      } else setCorriendo((v) => !v)
    },
    pausar: () => setCorriendo(false),
    reiniciar: () => {
      setCorriendo(false)
      reiniciar()
    },
    irA,
    suscribir,
    /** Segundos de recorrido real a VELOCIDAD_KMH */
    tiempoSimulado: recorrido / ((VELOCIDAD_KMH * 1000) / 3600),
  }
}
