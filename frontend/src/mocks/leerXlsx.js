// Lector ligero de xlsx SOLO para el modo simulado.
// Lee el encabezado y las primeras filas de la primera hoja sin cargar el archivo completo
// en memoria como tabla: descomprime la hoja por partes y se detiene al juntar las filas.
// En producción, la vista previa la genera el backend (POST /api/cargas).
import { unzipSync, Unzip, UnzipInflate, strFromU8 } from 'fflate'

const ENTIDADES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }
const desescapar = (s) =>
  s.replace(/&(#x?[0-9a-fA-F]+|amp|lt|gt|quot|apos);/g, (_, e) => {
    if (e[0] === '#') return String.fromCodePoint(e[1] === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10))
    return ENTIDADES[e]
  })

/** "AB" → 27 (base 0) */
function indiceColumna(ref) {
  let n = 0
  for (const ch of ref) {
    const c = ch.charCodeAt(0)
    if (c < 65 || c > 90) break
    n = n * 26 + (c - 64)
  }
  return n - 1
}

function textoDeSi(si) {
  let t = ''
  const re = /<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g
  let m
  while ((m = re.exec(si))) t += m[1]
  return desescapar(t)
}

function leerCadenasCompartidas(xml) {
  const lista = []
  const re = /<si>([\s\S]*?)<\/si>|<si\/>/g
  let m
  while ((m = re.exec(xml))) lista.push(m[1] ? textoDeSi(m[1]) : '')
  return lista
}

const reCelda = /<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g

function leerFila(xmlFila, compartidas) {
  const celdas = []
  reCelda.lastIndex = 0
  let m
  let siguiente = 0
  while ((m = reCelda.exec(xmlFila))) {
    const attrs = m[1]
    const cuerpo = m[2] ?? ''
    const ref = /\br="([A-Z]+)\d+"/.exec(attrs)
    const col = ref ? indiceColumna(ref[1]) : siguiente
    siguiente = col + 1
    const tipo = /\bt="(\w+)"/.exec(attrs)?.[1]
    let valor = null
    if (tipo === 'inlineStr') {
      valor = textoDeSi(cuerpo)
    } else {
      const v = /<v>([\s\S]*?)<\/v>/.exec(cuerpo)?.[1]
      if (v != null) {
        if (tipo === 's') valor = compartidas[Number(v)] ?? ''
        else if (tipo === 'str' || tipo === 'd' || tipo === 'e') valor = desescapar(v)
        else if (tipo === 'b') valor = v === '1'
        else valor = Number(v)
      }
    }
    celdas[col] = valor
  }
  return celdas
}

const serialAFecha = (n) => new Date(Math.round((n - 25569) * 86400000)).toISOString().slice(0, 10)
const fraccionAHora = (n) => {
  const s = Math.round((n % 1) * 86400)
  return [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60].map((v) => String(v).padStart(2, '0')).join(':')
}

/** Corrige fechas y horas que Excel guarda como números */
function normalizar(nombre, valor) {
  if (typeof valor !== 'number') return valor
  const n = nombre.toLowerCase()
  if (n.includes('fecha') && valor > 20000 && valor < 80000) return serialAFecha(valor)
  if (n.includes('hora') && valor >= 0 && valor < 1) return fraccionAHora(valor)
  return valor
}

const ceder = () => new Promise((r) => setTimeout(r, 0))

/**
 * @param {File} archivo
 * @param {{ maxFilas?: number, alProgreso?: (fraccion: number) => void }} [opciones]
 * @returns {Promise<{ hoja: string, columnas: string[], filas: object[], totalFilas: number, filasGam: number }>}
 */
export async function leerVistaPreviaXlsx(archivo, { maxFilas = 200, alProgreso } = {}) {
  const bytes = new Uint8Array(await archivo.arrayBuffer())
  if (bytes[0] !== 0x50 || bytes[1] !== 0x4b) throw new Error('NO_XLSX')

  let meta
  try {
    meta = unzipSync(bytes, {
      filter: (f) => ['xl/workbook.xml', 'xl/_rels/workbook.xml.rels', 'xl/sharedStrings.xml'].includes(f.name),
    })
  } catch {
    throw new Error('NO_XLSX')
  }
  if (!meta['xl/workbook.xml']) throw new Error('NO_XLSX')

  const libro = strFromU8(meta['xl/workbook.xml'])
  let nombreHoja = 'Hoja 1'
  let rutaHoja = 'xl/worksheets/sheet1.xml'
  const etiquetaHoja = /<sheet\b[^>]*>/.exec(libro)?.[0]
  if (etiquetaHoja) {
    const nombre = /\bname="([^"]*)"/.exec(etiquetaHoja)?.[1]
    const rid = /\br:id="([^"]+)"/.exec(etiquetaHoja)?.[1]
    if (nombre) nombreHoja = desescapar(nombre)
    const rels = meta['xl/_rels/workbook.xml.rels'] ? strFromU8(meta['xl/_rels/workbook.xml.rels']) : ''
    const relacion = [...rels.matchAll(/<Relationship\b[^>]*>/g)]
      .map((m) => m[0])
      .find((r) => r.includes(`Id="${rid}"`))
    const destino = relacion && /\bTarget="([^"]+)"/.exec(relacion)?.[1]
    if (destino) rutaHoja = destino.startsWith('/') ? destino.slice(1) : `xl/${destino.replace(/^\.\//, '')}`
  }
  const compartidas = meta['xl/sharedStrings.xml']
    ? leerCadenasCompartidas(strFromU8(meta['xl/sharedStrings.xml']))
    : []

  // Marcas para reconocer filas de Gustavo A. Madero sin interpretar toda la fila:
  // texto en línea, o el índice de la cadena compartida que lo contiene.
  const marcasGam = ['GUSTAVO A. MADERO', 'Gustavo A. Madero', 'GUSTAVO A MADERO', 'Gustavo A Madero']
  compartidas.forEach((t, i) => {
    if (/gustavo a\.? madero/i.test(t)) marcasGam.push(`t="s"><v>${i}</v>`)
  })
  const esGam = (xml) => marcasGam.some((m) => xml.includes(m))

  // Descompresión por partes de la hoja: guarda las primeras filas y cuenta el resto
  const filasXml = []
  let totalFilas = 0
  let filasGam = 0
  let resto = ''
  let error = null
  let encontrada = false
  const decodificador = new TextDecoder('utf-8')
  const unzip = new Unzip()
  unzip.register(UnzipInflate)
  unzip.onfile = (f) => {
    if (f.name !== rutaHoja) return
    encontrada = true
    f.ondata = (err, trozo, final) => {
      if (err) {
        error = err
        return
      }
      resto += decodificador.decode(trozo, { stream: !final })
      let ini = 0
      let fin
      while ((fin = resto.indexOf('</row>', ini)) !== -1) {
        const fila = resto.slice(resto.lastIndexOf('<row', fin), fin)
        if (totalFilas <= maxFilas) filasXml.push(fila)
        if (totalFilas > 0 && esGam(fila)) filasGam++
        totalFilas++
        ini = fin + 6
      }
      resto = resto.slice(ini)
    }
    f.start()
  }
  const PASO = 1 << 19
  for (let i = 0; i < bytes.length; i += PASO) {
    unzip.push(bytes.subarray(i, i + PASO), i + PASO >= bytes.length)
    if (error) throw new Error('NO_XLSX')
    alProgreso?.(Math.min(1, (i + PASO) / bytes.length))
    await ceder()
  }
  if (!encontrada) throw new Error('NO_XLSX')

  if (filasXml.length === 0) return { hoja: nombreHoja, columnas: [], filas: [], totalFilas: 0, filasGam: 0 }
  const encabezado = leerFila(filasXml[0], compartidas).map((v, i) =>
    v == null || v === '' ? `columna_${i + 1}` : String(v).trim(),
  )
  const filas = filasXml.slice(1, maxFilas + 1).map((x) => {
    const celdas = leerFila(x, compartidas)
    const obj = {}
    encabezado.forEach((nombre, i) => {
      obj[nombre] = normalizar(nombre, celdas[i] ?? null)
    })
    return obj
  })
  return { hoja: nombreHoja, columnas: encabezado, filas, totalFilas: Math.max(0, totalFilas - 1), filasGam }
}
