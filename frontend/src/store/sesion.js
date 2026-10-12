// Estado de la sesión de trabajo (lo que la persona va decidiendo entre vistas).
// Se guarda en sessionStorage para sobrevivir a una recarga de página.
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

/** sessionStorage que no truena si el navegador lo bloquea */
const almacenSeguro = (() => {
  const memoria = new Map()
  const disponible = (() => {
    try {
      const k = '__ttr__'
      window.sessionStorage.setItem(k, '1')
      window.sessionStorage.removeItem(k)
      return true
    } catch {
      return false
    }
  })()
  return {
    getItem: (k) => {
      try {
        return disponible ? window.sessionStorage.getItem(k) : (memoria.get(k) ?? null)
      } catch {
        return memoria.get(k) ?? null
      }
    },
    setItem: (k, v) => {
      try {
        if (disponible) window.sessionStorage.setItem(k, v)
        else memoria.set(k, v)
      } catch {
        memoria.set(k, v)
      }
    },
    removeItem: (k) => {
      try {
        if (disponible) window.sessionStorage.removeItem(k)
      } catch {
        /* nada */
      }
      memoria.delete(k)
    },
  }
})()

/** Parámetros por defecto del algoritmo genético (POST /api/agentes) */
export const PARAMETROS_AG = {
  tam_poblacion: 50,
  n_generaciones: 200,
  tam_torneo: 3,
  prob_cruce: 0.9,
  prob_mutacion: 0.1,
  op_cruce: 'OX',
  op_mutacion: 'swap',
  semilla: 42,
  ruta_cerrada: true,
}

export const MAX_GRAFOS = 5

export const useSesion = create(
  persist(
    (set) => ({
      /** Respuesta de POST /api/cargas: vista previa del archivo elegido */
      cargaPrevia: null,
      /** Carga que se está procesando (ingesta + HDBSCAN) */
      idCargaEnProceso: null,
      /** Número de grafos elegido en Analizar */
      nGrafos: 3,
      /** Respuesta de POST /api/particiones + id_analisis al que pertenece */
      particion: null,
      parametros: PARAMETROS_AG,
      /** Agentes lanzados: [{ id_ejecucion, id_grafo, numero, color, n_nodos }] */
      ejecuciones: [],
      /** Partición a la que pertenecen los agentes */
      idParticionAgentes: null,

      ponerCargaPrevia: (cargaPrevia) => set({ cargaPrevia }),
      quitarCargaPrevia: () => set({ cargaPrevia: null }),
      iniciarProceso: (idCarga) => set({ idCargaEnProceso: idCarga }),
      terminarProceso: () => set({ idCargaEnProceso: null, cargaPrevia: null }),
      ponerNGrafos: (n) => set({ nGrafos: Math.max(1, Math.min(MAX_GRAFOS, n)) }),
      ponerParticion: (particion) => set({ particion }),
      ponerParametros: (cambios) => set((s) => ({ parametros: { ...s.parametros, ...cambios } })),
      restablecerParametros: () => set({ parametros: PARAMETROS_AG }),
      ponerEjecuciones: (ejecuciones, idParticion) => set({ ejecuciones, idParticionAgentes: idParticion }),
      /** Un análisis nuevo invalida la partición y los agentes anteriores */
      olvidarResultados: () => set({ particion: null, ejecuciones: [], idParticionAgentes: null }),
    }),
    {
      name: 'ttr-sesion',
      version: 1,
      storage: createJSONStorage(() => almacenSeguro),
    },
  ),
)

export { almacenSeguro }
