// Formatos en español de México: separador de miles con coma, decimales con punto.

const entero = new Intl.NumberFormat('es-MX', { maximumFractionDigits: 0 })
const decimal1 = new Intl.NumberFormat('es-MX', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const decimal2 = new Intl.NumberFormat('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const porciento = new Intl.NumberFormat('es-MX', { style: 'percent', maximumFractionDigits: 1 })
const fechaCorta = new Intl.DateTimeFormat('es-MX', { day: 'numeric', month: 'short', year: 'numeric' })
const fechaHora = new Intl.DateTimeFormat('es-MX', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

export const fmtEntero = (n) => (n == null || Number.isNaN(n) ? '—' : entero.format(n))
export const fmt1 = (n) => (n == null || Number.isNaN(n) ? '—' : decimal1.format(n))
export const fmt2 = (n) => (n == null || Number.isNaN(n) ? '—' : decimal2.format(n))
export const fmtPct = (n) => (n == null || Number.isNaN(n) ? '—' : porciento.format(n))

/** Distancia en metros → "14.23 km" o "820 m" */
export function fmtDistancia(m, { decimales = 2 } = {}) {
  if (m == null || Number.isNaN(m)) return '—'
  if (Math.abs(m) < 1000) return `${entero.format(m)} m`
  const km = m / 1000
  return `${decimales === 1 ? decimal1.format(km) : decimal2.format(km)} km`
}

/** Bytes → "14.2 MB" */
export function fmtBytes(b) {
  if (b == null) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1024 ** 2) return `${decimal1.format(b / 1024)} KB`
  return `${decimal1.format(b / 1024 ** 2)} MB`
}

export function fmtFecha(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? String(iso) : fechaCorta.format(d)
}

export function fmtFechaHora(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? String(iso) : fechaHora.format(d)
}

/** Segundos → "00:27:41" */
export function fmtReloj(seg) {
  const s = Math.max(0, Math.round(seg))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  return [h, m, r].map((v) => String(v).padStart(2, '0')).join(':')
}

/** Diferencia con signo: +4, −2 */
export function fmtDelta(n) {
  if (n == null || Number.isNaN(n) || n === 0) return '±0'
  return n > 0 ? `+${entero.format(n)}` : `−${entero.format(Math.abs(n))}`
}

/** "1 agente" / "3 agentes" */
export const plural = (n, uno, varios) => `${fmtEntero(n)} ${n === 1 ? uno : varios}`
