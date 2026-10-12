import { useSyncExternalStore } from 'react'

/** Devuelve true si la media query se cumple; se actualiza al cambiar el tamaño. */
export function useMedia(consulta) {
  return useSyncExternalStore(
    (avisar) => {
      const mql = window.matchMedia(consulta)
      mql.addEventListener('change', avisar)
      return () => mql.removeEventListener('change', avisar)
    },
    () => window.matchMedia(consulta).matches,
    () => false,
  )
}

/** Puntos de quiebre de TTR_: móvil < 768 ≤ tableta < 1200 ≤ escritorio */
export const useEsMovil = () => useMedia('(max-width: 767px)')
export const useEsEscritorio = () => useMedia('(min-width: 1200px)')
export const useMovimientoReducido = () => useMedia('(prefers-reduced-motion: reduce)')
