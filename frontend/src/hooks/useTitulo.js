import { useEffect } from 'react'

/** Título de la pestaña del navegador por vista: "Analizar · TTR_" */
export function useTitulo(titulo) {
  useEffect(() => {
    document.title = titulo ? `${titulo} · TTR_` : 'TTR_'
  }, [titulo])
}
