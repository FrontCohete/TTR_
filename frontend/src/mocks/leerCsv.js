// Lector de CSV SOLO para el modo simulado: lee el archivo por partes, guarda el
// encabezado y las primeras filas, y cuenta el total de filas y las de Gustavo A. Madero.
// En producción, la vista previa la genera el backend (POST /api/cargas).

const ceder = () => new Promise((r) => setTimeout(r, 0))
const esGam = (texto) => /gustavo a\.? madero/i.test(texto)

/** Convierte texto según su columna: números, fechas y horas quedan como en el xlsx */
function convertir(valor) {
  if (valor === '') return null
  if (/^-?\d+(\.\d+)?$/.test(valor)) return Number(valor)
  return valor
}

/**
 * @param {File} archivo
 * @param {{ maxFilas?: number, alProgreso?: (fraccion: number) => void }} [opciones]
 */
export async function leerVistaPreviaCsv(archivo, { maxFilas = 200, alProgreso } = {}) {
  const lector = archivo.stream().getReader()
  let decodificador = null
  let separador = null
  const filas = []
  let totalFilas = 0
  let filasGam = 0
  let leidos = 0

  // Estado del analizador (RFC 4180: comillas dobles, comillas escapadas "")
  let campo = ''
  let fila = []
  let textoFila = ''
  let enComillas = false

  const cerrarFila = () => {
    fila.push(campo)
    if (fila.length > 1 || fila[0] !== '') {
      if (totalFilas <= maxFilas) filas.push(fila)
      else if (esGam(textoFila)) filasGam++
      totalFilas++
    }
    campo = ''
    fila = []
    textoFila = ''
  }

  for (;;) {
    const { value, done } = await lector.read()
    if (done) break
    leidos += value.length
    if (!decodificador) {
      // UTF-8 si es válido; si no, Windows-1252 (CSV guardados desde Excel en español)
      try {
        new TextDecoder('utf-8', { fatal: true }).decode(value.subarray(0, Math.min(value.length, 65536)), {
          stream: true,
        })
        decodificador = new TextDecoder('utf-8')
      } catch {
        decodificador = new TextDecoder('windows-1252')
      }
    }
    let texto = decodificador.decode(value, { stream: true })
    if (separador == null) {
      texto = texto.replace(/^﻿/, '')
      const primera = texto.slice(0, texto.indexOf('\n') + 1 || undefined)
      separador = (primera.match(/;/g) || []).length > (primera.match(/,/g) || []).length ? ';' : ','
    }
    for (let i = 0; i < texto.length; i++) {
      const c = texto[i]
      if (totalFilas > maxFilas) textoFila += c
      if (enComillas) {
        if (c === '"') {
          if (texto[i + 1] === '"') {
            campo += '"'
            i++
            if (totalFilas > maxFilas) textoFila += '"'
          } else enComillas = false
        } else campo += c
        continue
      }
      if (c === '"' && campo === '') enComillas = true
      else if (c === separador) {
        fila.push(campo)
        campo = ''
      } else if (c === '\n') cerrarFila()
      else if (c !== '\r') campo += c
    }
    // Para las filas que no se guardan solo importa el texto; se evita acumular campos enormes
    if (totalFilas > maxFilas && !enComillas) campo = campo.length > 4096 ? '' : campo
    alProgreso?.(Math.min(1, leidos / archivo.size))
    await ceder()
  }
  if (campo !== '' || fila.length) cerrarFila()

  if (!filas.length) return { hoja: null, columnas: [], filas: [], totalFilas: 0, filasGam: 0 }
  const encabezado = filas[0].map((v, i) => (v.trim() === '' ? `columna_${i + 1}` : v.trim()))
  const datos = filas.slice(1, maxFilas + 1).map((f) => {
    const obj = {}
    encabezado.forEach((nombre, i) => {
      obj[nombre] = convertir((f[i] ?? '').trim())
    })
    return obj
  })
  filasGam += datos.filter((o) => Object.values(o).some((v) => typeof v === 'string' && esGam(v))).length
  return { hoja: null, columnas: encabezado, filas: datos, totalFilas: Math.max(0, totalFilas - 1), filasGam }
}
