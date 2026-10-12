// Colores con significado. Los mismos valores viven en styles/tokens.css.

/**
 * Colores de los grafos 1 a 5. El backend guarda un color por grafo (tabla `grafo`);
 * se recomienda que use esta misma lista para que Analizar, Rutas y Simular coincidan.
 * Validados para daltonismo hasta 4 grafos; el número del grafo siempre acompaña al color.
 */
export const COLORES_GRAFO = ['#1F5FD0', '#B87A00', '#13907A', '#8E3B9E', '#4E6B1F']

export const colorGrafo = (numero, color) => color || COLORES_GRAFO[(numero - 1) % COLORES_GRAFO.length]

export const SENAL = '#EE2B47'
export const NOCHE = '#2C2E3E'
export const PIZARRA = '#34374C'

/** Gravedad del delito: peso 0 a 4 (cat_delito.peso_gravedad) */
export const GRAVEDAD = [
  { peso: 0, nombre: 'No aplica', color: '#9A9CAB' },
  { peso: 1, nombre: 'Baja', color: '#F5A3AF' },
  { peso: 2, nombre: 'Media', color: '#F06A7E' },
  { peso: 3, nombre: 'Alta', color: '#EE2B47' },
  { peso: 4, nombre: 'Crítica', color: '#A3122A' },
]

export const colorGravedad = (peso) => GRAVEDAD[Math.max(0, Math.min(4, Math.round(peso)))].color

/** Nombre de la gravedad para un índice promedio 0–4 */
export const nombreGravedad = (indice) => GRAVEDAD[Math.max(0, Math.min(4, Math.round(indice)))].nombre

function luminancia(hex) {
  const h = hex.replace('#', '')
  const canal = (i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * canal(0) + 0.7152 * canal(2) + 0.0722 * canal(4)
}

/**
 * Color de texto legible sobre un relleno: blanco si alcanza 4.5:1 (WCAG AA),
 * si no, el que tenga más contraste. Se usa en números sobre estaciones y círculos de color.
 */
export function textoSobre(hex) {
  if (!hex || !hex.startsWith('#')) return '#fff'
  const l = luminancia(hex)
  const conBlanco = 1.05 / (l + 0.05)
  const conNegro = (l + 0.05) / 0.05
  if (conBlanco >= 4.5) return '#fff'
  return conNegro > conBlanco ? '#000' : '#fff'
}

/** Mezcla `hex` sobre blanco con opacidad `a` y devuelve el color resultante en hex */
export function sobreBlanco(hex, a) {
  const h = hex.replace('#', '')
  const mezcla = (i) => Math.round(255 + (parseInt(h.slice(i, i + 2), 16) - 255) * a)
  return `#${[0, 2, 4].map((i) => mezcla(i).toString(16).padStart(2, '0')).join('')}`
}

/** Convierte "#RRGGBB" a "rgba(r,g,b,a)" */
export function conAlfa(hex, a) {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}
