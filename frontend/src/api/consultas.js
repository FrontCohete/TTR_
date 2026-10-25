// Hooks de TanStack Query: caché, reintentos y consulta periódica en un solo lugar.
import { useQuery, useQueries } from '@tanstack/react-query'
import { api } from './index.js'

const FIJO = { staleTime: Infinity, gcTime: Infinity }

// ---------- Catálogos del mapa (no cambian) ----------
export const useLimite = () => useQuery({ queryKey: ['mapa', 'limite'], queryFn: api.obtenerLimite, ...FIJO })

export const useColonias = (habilitado = true) =>
  useQuery({ queryKey: ['mapa', 'colonias'], queryFn: api.obtenerColonias, enabled: habilitado, ...FIJO })

// ---------- Cargas ----------
export const useCargas = () => useQuery({ queryKey: ['cargas'], queryFn: api.listarCargas })

/** Estado de una carga. Mientras se procesa, se consulta cada segundo. */
export const useCarga = (idCarga) =>
  useQuery({
    queryKey: ['carga', idCarga],
    queryFn: () => api.obtenerCarga(idCarga),
    enabled: idCarga != null,
    refetchInterval: (q) => {
      const estado = q.state.data?.estado
      return estado === 'recibido' || estado === 'procesando' ? 1000 : false
    },
    refetchIntervalInBackground: true,
  })

// ---------- Análisis vigente ----------
export const useAnalisisVigente = () =>
  useQuery({
    queryKey: ['analisis', 'vigente'],
    queryFn: api.obtenerAnalisisVigente,
    retry: (n, e) => e?.estado !== 404 && n < 2,
  })

export const useHotspots = (idAnalisis) =>
  useQuery({
    queryKey: ['analisis', idAnalisis, 'hotspots'],
    queryFn: api.obtenerHotspots,
    enabled: idAnalisis != null,
    ...FIJO,
  })

export const usePuntos = (idAnalisis, habilitado = true) =>
  useQuery({
    queryKey: ['analisis', idAnalisis, 'puntos'],
    queryFn: api.obtenerPuntos,
    enabled: idAnalisis != null && habilitado,
    ...FIJO,
  })

// ---------- Agentes (algoritmo genético) ----------
const terminado = (estado) => estado === 'terminado' || estado === 'error'

/** Estado de varios agentes a la vez; consulta cada segundo hasta que todos terminan. */
export const useAgentes = (ids) =>
  useQueries({
    queries: ids.map((id) => ({
      queryKey: ['agente', id],
      queryFn: () => api.obtenerAgente(id),
      refetchInterval: (q) => (terminado(q.state.data?.estado) ? false : 1000),
    })),
  })

export const useGeneraciones = (idEjecucion, habilitado) =>
  useQuery({
    queryKey: ['agente', idEjecucion, 'generaciones'],
    queryFn: () => api.obtenerGeneraciones(idEjecucion),
    enabled: idEjecucion != null && habilitado,
    ...FIJO,
  })

export const useIndividuos = (idGeneracion) =>
  useQuery({
    queryKey: ['generacion', idGeneracion, 'individuos'],
    queryFn: () => api.obtenerIndividuos(idGeneracion),
    enabled: idGeneracion != null,
    placeholderData: (previo) => previo,
    ...FIJO,
  })

export const useRutas = (ids, habilitado = true) =>
  useQueries({
    queries: ids.map((id) => ({
      queryKey: ['agente', id, 'ruta'],
      queryFn: () => api.obtenerRuta(id),
      enabled: habilitado,
      ...FIJO,
    })),
  })

/**
 * Ruta del agente dibujada por calles (OSRM, etapa 6). El backend la pide una vez y la guarda.
 * Si el servidor de ruteo no responde (503) no se reintenta: Simular usa la línea recta.
 */
export const useRutasCalles = (ids, habilitado = true) =>
  useQueries({
    queries: ids.map((id) => ({
      queryKey: ['agente', id, 'ruta-calles'],
      queryFn: () => api.obtenerRutaCalles(id),
      enabled: habilitado,
      retry: (n, e) => ![404, 409, 503].includes(e?.estado) && n < 1,
      ...FIJO,
    })),
  })

// ---------- Mantenimiento (Inicio) ----------
/** Qué hay en la base y si se puede «Empezar de cero». Solo se consulta con la sección abierta. */
export const useMantenimiento = (habilitado = true) =>
  useQuery({ queryKey: ['mantenimiento'], queryFn: api.obtenerMantenimiento, enabled: habilitado })
