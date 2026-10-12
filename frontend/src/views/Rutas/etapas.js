import { ArrowLeftRight, ChartLine, Dices, GitMerge, Ruler, Shuffle, Trophy } from 'lucide-react'

/**
 * Las 7 etapas del algoritmo genético, en el orden en que se reproducen.
 * Las dos primeras ocurren solo en la generación 0; las otras cinco se repiten en cada generación.
 */
export const ETAPAS_AG = [
  { clave: 'permutacion', nombre: 'Permutación', corto: 'Permutación', icono: Shuffle },
  { clave: 'evaluacion', nombre: 'Función objetivo', corto: 'Evaluación', icono: Ruler },
  { clave: 'seleccion', nombre: 'Selección al azar', corto: 'Al azar', icono: Dices },
  { clave: 'torneo', nombre: 'Selección por torneo', corto: 'Torneo', icono: Trophy },
  { clave: 'cruce', nombre: 'Cruzamiento por permutación', corto: 'Cruce', icono: GitMerge },
  { clave: 'mutacion', nombre: 'Mutación por permutación', corto: 'Mutación', icono: ArrowLeftRight },
  { clave: 'evaluacion_gen', nombre: 'Evaluación de la generación', corto: 'Evaluación', icono: ChartLine },
]

export const PRIMERA_ETAPA_CICLO = 2
export const ULTIMA_ETAPA = 6

/** Siguiente posición del reproductor, o null si ya terminó */
export function siguiente({ gen, etapa }, total) {
  if (gen === 0 && etapa === 0) return { gen: 0, etapa: 1 }
  if (gen === 0) return total >= 1 ? { gen: 1, etapa: PRIMERA_ETAPA_CICLO } : null
  if (etapa < ULTIMA_ETAPA) return { gen, etapa: etapa + 1 }
  return gen < total ? { gen: gen + 1, etapa: PRIMERA_ETAPA_CICLO } : null
}

/** Posición anterior, o null si está al inicio */
export function anterior({ gen, etapa }) {
  if (gen === 0 && etapa === 0) return null
  if (gen === 0) return { gen: 0, etapa: 0 }
  if (etapa > PRIMERA_ETAPA_CICLO) return { gen, etapa: etapa - 1 }
  return gen === 1 ? { gen: 0, etapa: 1 } : { gen: gen - 1, etapa: ULTIMA_ETAPA }
}

/** Posición "resumen" de una generación (su evaluación) */
export const finDeGeneracion = (gen) => (gen === 0 ? { gen: 0, etapa: 1 } : { gen, etapa: ULTIMA_ETAPA })

export const VELOCIDADES = {
  paso: { etiqueta: 'Paso a paso', ms: null },
  lenta: { etiqueta: 'Lenta', ms: 2400 },
  normal: { etiqueta: 'Normal', ms: 1000 },
  auto: { etiqueta: 'Automático', ms: 60 },
}
