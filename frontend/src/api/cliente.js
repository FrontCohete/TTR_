// Cliente HTTP mínimo para la API de FastAPI (prefijo /api).
// En desarrollo, Vite reenvía /api a http://localhost:8000 (ver vite.config.js).

export class ApiError extends Error {
  /**
   * @param {number} estado  Código HTTP (409, 422, 500…)
   * @param {string} mensaje Texto para mostrar a la persona usuaria
   * @param {unknown} [detalle] Cuerpo original de la respuesta
   */
  constructor(estado, mensaje, detalle) {
    super(mensaje)
    this.name = 'ApiError'
    this.estado = estado
    this.detalle = detalle
  }
}

const BASE = '/api'

/** Extrae un mensaje legible de una respuesta de error de FastAPI */
function mensajeDeError(estado, cuerpo) {
  const d = cuerpo?.detail ?? cuerpo?.mensaje ?? cuerpo
  if (typeof d === 'string') return d
  if (Array.isArray(d) && d[0]?.msg) return d.map((e) => e.msg).join('. ')
  if (estado === 404) return 'El recurso no existe.'
  if (estado >= 500) return 'El servidor tuvo un problema. Revisa la terminal del backend.'
  return `La solicitud falló (código ${estado}).`
}

/**
 * Hace una solicitud JSON a la API.
 * @param {string} ruta  Ruta sin el prefijo /api, por ejemplo "/analisis/vigente"
 * @param {{ metodo?: string, cuerpo?: unknown, signal?: AbortSignal }} [opciones]
 */
export async function solicitar(ruta, { metodo = 'GET', cuerpo, signal } = {}) {
  let respuesta
  try {
    respuesta = await fetch(`${BASE}${ruta}`, {
      method: metodo,
      headers: cuerpo !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined,
      signal,
    })
  } catch (e) {
    if (e?.name === 'AbortError') throw e
    throw new ApiError(0, 'No hay conexión con el backend. Verifica que FastAPI esté corriendo en el puerto 8000.')
  }
  if (respuesta.status === 204) return null
  const texto = await respuesta.text()
  let datos = null
  try {
    datos = texto ? JSON.parse(texto) : null
  } catch {
    datos = texto
  }
  if (!respuesta.ok) throw new ApiError(respuesta.status, mensajeDeError(respuesta.status, datos), datos)
  return datos
}

/**
 * Sube un archivo con multipart/form-data e informa el avance (0 a 1).
 * Se usa XMLHttpRequest porque fetch no reporta el progreso de subida.
 */
export function subirArchivo(ruta, archivo, { campo = 'archivo', alProgreso } = {}) {
  return new Promise((resolver, rechazar) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}${ruta}`)
    xhr.responseType = 'text'
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && alProgreso) alProgreso(e.loaded / e.total)
    }
    xhr.onload = () => {
      let datos = null
      try {
        datos = xhr.responseText ? JSON.parse(xhr.responseText) : null
      } catch {
        datos = xhr.responseText
      }
      if (xhr.status >= 200 && xhr.status < 300) resolver(datos)
      else rechazar(new ApiError(xhr.status, mensajeDeError(xhr.status, datos), datos))
    }
    xhr.onerror = () =>
      rechazar(
        new ApiError(0, 'No hay conexión con el backend. Verifica que FastAPI esté corriendo en el puerto 8000.'),
      )
    const formulario = new FormData()
    formulario.append(campo, archivo)
    xhr.send(formulario)
  })
}
