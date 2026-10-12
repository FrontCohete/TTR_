// Servidor simulado: implementa el contrato de la API (README §7) en el navegador.
// Los datos geográficos son REALES: contorno de GAM (INEGI), 179 colonias y los puntos
// de víctimas FGJ 2022–2024 de Gustavo A. Madero, con hotspots calculados con HDBSCAN
// y particiones con Louvain (scripts en Python, fuera de este proyecto).
// Lo simulado es el comportamiento del servidor: tiempos, estados e identificadores.
import { ApiError } from '../api/cliente.js'
import { almacenSeguro } from '../store/sesion.js'
import { COLORES_GRAFO } from '../lib/colores.js'
import { haversine } from '../lib/geo.js'
import { ejecutarAG } from './genetico.js'

import urlLimite from './data/limite.json?url'
import urlColonias from './data/colonias.json?url'
import urlHotspotsA2 from './data/hotspots_a2.json?url'
import urlHotspotsA3 from './data/hotspots_a3.json?url'
import urlPuntosA2 from './data/puntos_a2.json?url'
import urlPuntosA3 from './data/puntos_a3.json?url'
import urlParticionesA2 from './data/particiones_a2.json?url'
import urlParticionesA3 from './data/particiones_a3.json?url'

// ------------------------------------------------------------------ datos estáticos
const URLS = {
  limite: urlLimite,
  colonias: urlColonias,
  hotspots_a2: urlHotspotsA2,
  hotspots_a3: urlHotspotsA3,
  puntos_a2: urlPuntosA2,
  puntos_a3: urlPuntosA3,
  particiones_a2: urlParticionesA2,
  particiones_a3: urlParticionesA3,
}
const cacheJson = new Map()
const json = (clave) => {
  if (!cacheJson.has(clave)) {
    cacheJson.set(
      clave,
      fetch(URLS[clave]).then((r) => {
        if (!r.ok) throw new ApiError(500, `No se pudo leer el archivo simulado ${clave}.json`)
        return r.json()
      }),
    )
  }
  return cacheJson.get(clave)
}

/** Resultado de HDBSCAN precalculado para cada conjunto de datos */
const CONJUNTOS = {
  a2: { n_puntos: 49147, n_hotspots: 30, n_ruido: 19326, min_cluster_size: 380, min_samples: 10 },
  a3: { n_puntos: 63007, n_hotspots: 34, n_ruido: 27538, min_cluster_size: 487, min_samples: 10 },
}

const COLUMNAS_REQUERIDAS = ['fecha_hecho', 'hora_hecho', 'delito', 'alcaldia_hecho', 'latitud', 'longitud']
const COLUMNAS_UTILES = ['categoria_delito', 'sexo', 'edad', 'colonia_catalogo', 'alcaldia_catalogo']

// ------------------------------------------------------------------ estado persistente
const CLAVE = 'ttr-mock-v1'
const ESTADO_INICIAL = () => ({
  sec: { carga: 3, analisis: 3, particion: 1, grafo: 1, ejecucion: 1, simulacion: 1 },
  cargas: [
    {
      id_carga: 1,
      nombre_archivo: 'victimasFGJ_2022.xlsx',
      fecha_carga: '2026-09-28T10:14:00-06:00',
      filas_leidas: 252359,
      filas_validas: 237659,
      puntos_gam_nuevos: 24774,
      puntos_duplicados: 0,
      estado: 'completado',
      mensaje_error: null,
      huella: 'victimasFGJ_2022.xlsx',
    },
    {
      id_carga: 2,
      nombre_archivo: 'victimasFGJ_2023.xlsx',
      fecha_carga: '2026-10-01T17:42:00-06:00',
      filas_leidas: 254940,
      filas_validas: 239401,
      puntos_gam_nuevos: 24373,
      puntos_duplicados: 0,
      estado: 'completado',
      mensaje_error: null,
      huella: 'victimasFGJ_2023.xlsx',
    },
  ],
  analisis: [
    {
      id_analisis: 1,
      conjunto: null,
      fecha: '2026-09-28T10:16:00-06:00',
      n_puntos: 24774,
      n_hotspots: 33,
      n_ruido: 10371,
      min_cluster_size: 192,
      min_samples: 10,
      previo: null,
      vigente: false,
    },
    { id_analisis: 2, conjunto: 'a2', fecha: '2026-10-01T17:44:00-06:00', ...CONJUNTOS.a2, previo: 1, vigente: true },
  ],
  procesos: {},
  particiones: [],
  ejecuciones: [],
  simulaciones: [],
})

let estado = (() => {
  try {
    const guardado = almacenSeguro.getItem(CLAVE)
    if (guardado) return JSON.parse(guardado)
  } catch {
    /* estado dañado: se reinicia */
  }
  return ESTADO_INICIAL()
})()
const guardar = () => almacenSeguro.setItem(CLAVE, JSON.stringify(estado))

/** Borra el estado simulado (útil para volver al inicio de la demostración) */
export function reiniciarSimulacion() {
  estado = ESTADO_INICIAL()
  guardar()
}

// ------------------------------------------------------------------ utilidades
const esperar = (min = 220, max = 560) => new Promise((r) => setTimeout(r, min + Math.random() * (max - min)))
const ahoraIso = () => {
  const d = new Date()
  const off = -d.getTimezoneOffset()
  const s = off >= 0 ? '+' : '-'
  const pad = (n) => String(Math.floor(Math.abs(n))).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}${s}${pad(off / 60)}:${pad(off % 60)}`
}
const sigId = (tipo) => {
  const id = estado.sec[tipo]
  estado.sec[tipo] += 1
  return id
}
const vigente = () => estado.analisis.find((a) => a.vigente)
const copia = (x) => (x == null ? x : JSON.parse(JSON.stringify(x)))

// ================================================================== Vista Inicio
const EXTENSIONES = /\.(csv|xlsx|xls)$/i
/** Nombre sin extensión: victimasFGJ_2023.csv y victimasFGJ_2023.xlsx cuentan como el mismo archivo */
const huellaDe = (nombre) => nombre.replace(EXTENSIONES, '').toLowerCase()

export async function subirCarga(archivo, { alProgreso } = {}) {
  const huella = huellaDe(archivo.name)
  const repetida = estado.cargas.find(
    (c) => huellaDe(c.huella) === huella && (c.estado === 'completado' || c.estado === 'procesando'),
  )
  if (repetida) {
    await esperar(300, 500)
    throw new ApiError(
      409,
      `Se cargó el ${new Date(repetida.fecha_carga).toLocaleDateString('es-MX', { day: 'numeric', month: 'long' })} como carga ${repetida.id_carga} y sus puntos ya están en la base. Elige un archivo distinto.`,
    )
  }
  const extension = EXTENSIONES.exec(archivo.name)?.[1]?.toLowerCase()
  if (!extension) {
    await esperar(200, 300)
    throw new ApiError(422, 'Solo se aceptan archivos .csv, .xlsx o .xls.')
  }

  // .xls (Excel 97-2003) es un formato binario antiguo: en modo simulado no se lee,
  // se acepta tal cual y la vista previa queda a cargo del backend real.
  if (extension === 'xls') {
    await esperar(400, 700)
    const id = sigId('carga')
    estado.cargas.push({
      id_carga: id,
      nombre_archivo: archivo.name,
      fecha_carga: ahoraIso(),
      filas_leidas: null,
      filas_validas: null,
      filas_gam: 1,
      puntos_gam_nuevos: 0,
      puntos_duplicados: 0,
      estado: 'recibido',
      mensaje_error: null,
      huella: archivo.name,
      faltantes: [],
    })
    guardar()
    return {
      id_carga: id,
      nombre_archivo: archivo.name,
      formato: 'xls',
      filas_leidas: null,
      columnas: { encontradas: [...COLUMNAS_REQUERIDAS], faltantes: [], todas: [] },
      vista_previa: [],
      vista_previa_disponible: false,
      resumen: { filas_gam: null, sin_coordenadas: null },
    }
  }

  let lectura
  try {
    if (extension === 'csv') {
      const { leerVistaPreviaCsv } = await import('./leerCsv.js')
      lectura = await leerVistaPreviaCsv(archivo, { maxFilas: 200, alProgreso })
    } else {
      const { leerVistaPreviaXlsx } = await import('./leerXlsx.js')
      lectura = await leerVistaPreviaXlsx(archivo, { maxFilas: 200, alProgreso })
    }
  } catch {
    throw new ApiError(
      422,
      extension === 'csv'
        ? 'No se pudo leer el CSV. Verifica que sea texto separado por comas o punto y coma.'
        : 'No se pudo leer el archivo. Verifica que sea un libro de Excel (.xlsx) sin contraseña.',
    )
  }
  const normal = (s) => s.toLowerCase().trim()
  const presentes = new Set(lectura.columnas.map(normal))
  const encontradas = [...COLUMNAS_REQUERIDAS, ...COLUMNAS_UTILES].filter((c) => presentes.has(c))
  const faltantes = COLUMNAS_REQUERIDAS.filter((c) => !presentes.has(c))

  const muestra = lectura.filas
  const sinCoord = muestra.filter(
    (f) => f.latitud == null || f.longitud == null || f.latitud === '' || f.longitud === '',
  ).length
  const proporcionSinCoord = muestra.length ? sinCoord / muestra.length : 0

  const id = sigId('carga')
  const carga = {
    id_carga: id,
    nombre_archivo: archivo.name,
    fecha_carga: ahoraIso(),
    filas_leidas: lectura.totalFilas,
    filas_validas: Math.round(lectura.totalFilas * (1 - proporcionSinCoord)),
    filas_gam: lectura.filasGam,
    puntos_gam_nuevos: 0,
    puntos_duplicados: 0,
    estado: 'recibido',
    mensaje_error: null,
    huella,
    faltantes,
  }
  estado.cargas.push(carga)
  guardar()
  return {
    id_carga: id,
    nombre_archivo: archivo.name,
    formato: extension,
    hoja: lectura.hoja,
    filas_leidas: lectura.totalFilas,
    columnas: { encontradas, faltantes, todas: lectura.columnas },
    vista_previa: muestra.slice(0, 20),
    resumen: {
      filas_gam: lectura.filasGam,
      sin_coordenadas: Math.round(lectura.totalFilas * proporcionSinCoord),
    },
  }
}

const DURACION_PROCESO = 7000

export async function procesarCarga(idCarga) {
  await esperar(150, 300)
  const carga = estado.cargas.find((c) => c.id_carga === Number(idCarga))
  if (!carga) throw new ApiError(404, 'La carga no existe.')
  if (carga.faltantes?.length) throw new ApiError(422, `Faltan columnas obligatorias: ${carga.faltantes.join(', ')}.`)
  if (carga.estado !== 'recibido') throw new ApiError(409, 'Esta carga ya se procesó.')
  carga.estado = 'procesando'
  estado.procesos[carga.id_carga] = { inicio: Date.now() }
  guardar()
  return { id_carga: carga.id_carga, estado: 'procesando' }
}

function finalizarProceso(carga) {
  const anterior = vigente()
  if (!carga.filas_gam) {
    carga.estado = 'error'
    carga.mensaje_error =
      'El archivo no tiene registros de Gustavo A. Madero con coordenadas. No se generó un análisis nuevo.'
    delete estado.procesos[carga.id_carga]
    guardar()
    return
  }
  const conjunto = 'a3'
  const datos = CONJUNTOS[conjunto]
  const nuevos = anterior?.conjunto === 'a3' ? 0 : Math.min(carga.filas_gam, datos.n_puntos - (anterior?.n_puntos ?? 0))
  carga.puntos_gam_nuevos = nuevos
  carga.puntos_duplicados = Math.max(0, (carga.filas_gam ?? 0) - nuevos)
  carga.estado = 'completado'
  const idAnalisis = sigId('analisis')
  estado.analisis.forEach((a) => {
    a.vigente = false
  })
  estado.analisis.push({
    id_analisis: idAnalisis,
    conjunto,
    fecha: ahoraIso(),
    ...datos,
    previo: anterior?.id_analisis ?? null,
    vigente: true,
  })
  carga.id_analisis = idAnalisis
  delete estado.procesos[carga.id_carga]
  guardar()
}

export async function obtenerCarga(idCarga) {
  await esperar(60, 140)
  const carga = estado.cargas.find((c) => c.id_carga === Number(idCarga))
  if (!carga) throw new ApiError(404, 'La carga no existe.')
  const proceso = estado.procesos[carga.id_carga]
  let etapa = null
  let avance = carga.estado === 'completado' ? 100 : 0
  if (carga.estado === 'procesando' && proceso) {
    const t = (Date.now() - proceso.inicio) / DURACION_PROCESO
    if (t >= 1) {
      finalizarProceso(carga)
      avance = 100
    } else {
      avance = Math.round(t * 100)
      etapa = t < 0.28 ? 'limpieza' : t < 0.7 ? 'insercion' : 'hdbscan'
      if (etapa !== 'limpieza') {
        const f = Math.min(1, (t - 0.28) / 0.42)
        carga.puntos_gam_nuevos = Math.round(f * (carga.filas_gam ?? 0))
      }
    }
  }
  return {
    id_carga: carga.id_carga,
    nombre_archivo: carga.nombre_archivo,
    estado: carga.estado,
    etapa,
    avance,
    puntos_gam_nuevos: carga.puntos_gam_nuevos,
    puntos_duplicados: carga.puntos_duplicados,
    id_analisis: carga.id_analisis ?? null,
    mensaje_error: carga.mensaje_error,
  }
}

export async function listarCargas() {
  await esperar(120, 260)
  return estado.cargas
    .filter((c) => c.estado !== 'recibido')
    .map(({ huella, faltantes, filas_gam, ...c }) => c)
    .sort((a, b) => b.id_carga - a.id_carga)
}

// ================================================================== Vista Analizar
export async function obtenerLimite() {
  await esperar(80, 160)
  return json('limite')
}

export async function obtenerColonias() {
  await esperar(120, 240)
  return json('colonias')
}

export async function obtenerAnalisisVigente() {
  await esperar(120, 260)
  const a = vigente()
  if (!a) throw new ApiError(404, 'Todavía no hay un análisis vigente. Carga un dataset para generarlo.')
  const previo = estado.analisis.find((x) => x.id_analisis === a.previo)
  return {
    id_analisis: a.id_analisis,
    fecha: a.fecha,
    n_puntos: a.n_puntos,
    n_hotspots: a.n_hotspots,
    n_ruido: a.n_ruido,
    n_hotspots_previo: previo?.n_hotspots ?? null,
    min_cluster_size: a.min_cluster_size,
    min_samples: a.min_samples,
  }
}

export async function obtenerPuntos() {
  await esperar(300, 600)
  const a = vigente()
  if (!a) throw new ApiError(404, 'No hay análisis vigente.')
  return json(`puntos_${a.conjunto}`)
}

export async function obtenerHotspots() {
  await esperar(160, 320)
  const a = vigente()
  if (!a) throw new ApiError(404, 'No hay análisis vigente.')
  return json(`hotspots_${a.conjunto}`)
}

export async function crearParticion(nGrafos) {
  await esperar(500, 900)
  const n = Number(nGrafos)
  if (!Number.isInteger(n) || n < 1 || n > 5) throw new ApiError(422, 'El número de grafos debe estar entre 1 y 5.')
  const a = vigente()
  if (!a) throw new ApiError(409, 'No hay análisis vigente para repartir.')
  const todas = await json(`particiones_${a.conjunto}`)
  const p = todas[String(n)]
  const idParticion = sigId('particion')
  const grafos = p.grafos.map((g) => ({
    id_grafo: sigId('grafo'),
    numero: g.numero,
    color: COLORES_GRAFO[g.numero - 1],
    n_nodos: g.n_nodos,
    hotspots: g.hotspots,
  }))
  estado.particiones.forEach((x) => {
    if (x.id_analisis === a.id_analisis) x.vigente = false
  })
  const registro = {
    id_particion: idParticion,
    id_analisis: a.id_analisis,
    n_grafos: n,
    modularidad: p.modularidad,
    resolucion: p.resolucion,
    grafos,
    vigente: true,
  }
  estado.particiones.push(registro)
  guardar()
  return copia({ id_particion: idParticion, n_grafos: n, modularidad: p.modularidad, grafos })
}

export async function obtenerHotspotsParticion(idParticion) {
  await esperar()
  const p = estado.particiones.find((x) => x.id_particion === Number(idParticion))
  if (!p) throw new ApiError(404, 'La partición no existe.')
  const a = estado.analisis.find((x) => x.id_analisis === p.id_analisis)
  const fc = await json(`hotspots_${a.conjunto}`)
  const grafoDe = new Map()
  p.grafos.forEach((g) => g.hotspots.forEach((h) => grafoDe.set(h, g)))
  return {
    type: 'FeatureCollection',
    features: fc.features.map((f) => {
      const g = grafoDe.get(f.properties.id_hotspot)
      return { ...f, properties: { ...f.properties, numero_grafo: g?.numero ?? null, color: g?.color ?? null } }
    }),
  }
}

// ================================================================== Vista Rutas
const resultadosAG = new Map()

async function contextoEjecucion(ej) {
  const p = estado.particiones.find((x) => x.id_particion === ej.id_particion)
  const a = estado.analisis.find((x) => x.id_analisis === p.id_analisis)
  const fc = await json(`hotspots_${a.conjunto}`)
  const centroides = new Map(fc.features.map((f) => [f.properties.id_hotspot, f.properties]))
  return { centroides }
}

async function resultado(ej) {
  if (!resultadosAG.has(ej.id_ejecucion)) {
    resultadosAG.set(
      ej.id_ejecucion,
      (async () => {
        const { centroides } = await contextoEjecucion(ej)
        const cache = new Map()
        const distancia = (a, b) => {
          const k = a < b ? `${a}-${b}` : `${b}-${a}`
          if (!cache.has(k)) cache.set(k, haversine(centroides.get(a).centroide, centroides.get(b).centroide))
          return cache.get(k)
        }
        const r = ejecutarAG({ nodos: ej.hotspots, distancia, parametros: ej.parametros })
        return { ...r, centroides }
      })(),
    )
  }
  return resultadosAG.get(ej.id_ejecucion)
}

const DEMORA_AG = (indice) => 1400 + indice * 650

export async function crearAgentes(idParticion, parametros) {
  await esperar(400, 700)
  const p = estado.particiones.find((x) => x.id_particion === Number(idParticion))
  if (!p) throw new ApiError(404, 'La partición no existe.')
  const reglas = [
    [parametros.tam_poblacion >= 2, 'La población debe tener al menos 2 individuos.'],
    [parametros.n_generaciones >= 1, 'Debe haber al menos 1 generación.'],
    [
      parametros.tam_torneo >= 2 && parametros.tam_torneo <= parametros.tam_poblacion,
      'El torneo debe tener entre 2 participantes y el tamaño de la población.',
    ],
    [parametros.prob_cruce >= 0 && parametros.prob_cruce <= 1, 'La probabilidad de cruce debe estar entre 0 y 1.'],
    [
      parametros.prob_mutacion >= 0 && parametros.prob_mutacion <= 1,
      'La probabilidad de mutación debe estar entre 0 y 1.',
    ],
  ]
  const falla = reglas.find(([ok]) => !ok)
  if (falla) throw new ApiError(422, falla[1])
  const creadas = p.grafos.map((g, i) => {
    const ej = {
      id_ejecucion: sigId('ejecucion'),
      id_particion: p.id_particion,
      id_grafo: g.id_grafo,
      numero: g.numero,
      color: g.color,
      hotspots: g.hotspots,
      parametros: { ...parametros },
      inicio: Date.now(),
      demora: DEMORA_AG(i),
    }
    estado.ejecuciones.push(ej)
    return ej
  })
  guardar()
  return {
    ejecuciones: creadas.map((e) => ({
      id_ejecucion: e.id_ejecucion,
      id_grafo: e.id_grafo,
      numero: e.numero,
      estado: 'ejecutando',
    })),
  }
}

const buscarEjecucion = (id) => {
  const ej = estado.ejecuciones.find((x) => x.id_ejecucion === Number(id))
  if (!ej) throw new ApiError(404, 'La ejecución no existe.')
  return ej
}
const estaTerminada = (ej) => Date.now() - ej.inicio >= ej.demora

export async function obtenerAgente(idEjecucion) {
  await esperar(80, 180)
  const ej = buscarEjecucion(idEjecucion)
  const base = {
    id_ejecucion: ej.id_ejecucion,
    id_grafo: ej.id_grafo,
    numero: ej.numero,
    color: ej.color,
    n_nodos: ej.hotspots.length,
    parametros: ej.parametros,
  }
  if (!estaTerminada(ej)) {
    return {
      ...base,
      estado: 'ejecutando',
      avance: Math.round(((Date.now() - ej.inicio) / ej.demora) * 100),
      mejor_distancia: null,
      ruta_optima: null,
    }
  }
  const r = await resultado(ej)
  return {
    ...base,
    estado: 'terminado',
    avance: 100,
    mejor_distancia: r.mejor_distancia,
    ruta_optima: r.ruta_optima,
    generacion_mejor: r.generacion_mejor,
  }
}

export async function obtenerGeneraciones(idEjecucion) {
  await esperar(160, 320)
  const ej = buscarEjecucion(idEjecucion)
  if (!estaTerminada(ej)) throw new ApiError(409, 'El algoritmo de este agente todavía está corriendo.')
  const r = await resultado(ej)
  return r.generaciones.map((g) => ({
    id_generacion: ej.id_ejecucion * 10000 + g.numero,
    numero: g.numero,
    mejor_fitness: g.mejor_fitness,
    fitness_promedio: g.fitness_promedio,
    peor_fitness: g.peor_fitness,
    mejor_permutacion: g.mejor_permutacion,
  }))
}

export async function obtenerIndividuos(idGeneracion) {
  await esperar(90, 200)
  const id = Number(idGeneracion)
  const ej = buscarEjecucion(Math.floor(id / 10000))
  const r = await resultado(ej)
  const g = r.generaciones[id % 10000]
  if (!g) throw new ApiError(404, 'La generación no existe.')
  return copia({ id_generacion: id, numero: g.numero, individuos: g.individuos, operaciones: g.operaciones })
}

// ================================================================== Vista Simular
export async function obtenerRuta(idEjecucion) {
  await esperar(150, 300)
  const ej = buscarEjecucion(idEjecucion)
  if (!estaTerminada(ej)) throw new ApiError(409, 'El agente todavía no tiene ruta.')
  const r = await resultado(ej)
  const orden = r.ruta_optima
  const coords = orden.map((h) => r.centroides.get(h).centroide)
  if (ej.parametros.ruta_cerrada && coords.length > 1) coords.push(coords[0])
  return {
    type: 'Feature',
    geometry: { type: 'LineString', coordinates: coords },
    properties: {
      id_ejecucion: ej.id_ejecucion,
      numero_grafo: ej.numero,
      color: ej.color,
      distancia_m: r.mejor_distancia,
      orden: orden.map((h) => r.centroides.get(h).codigo),
      hotspots: orden,
      ruta_cerrada: !!ej.parametros.ruta_cerrada,
      generacion_mejor: r.generacion_mejor,
    },
  }
}

export async function registrarSimulacion({ id_ejecucion, distancia_total, duracion_s }) {
  await esperar(80, 160)
  const reg = { id_simulacion: sigId('simulacion'), id_ejecucion, fecha: ahoraIso(), distancia_total, duracion_s }
  estado.simulaciones.push(reg)
  guardar()
  return reg
}
