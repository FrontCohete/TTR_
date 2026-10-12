// Algoritmo genético de referencia para el modo simulado.
// Registra cada operación (selección, torneo, cruce, mutación) con la misma forma que
// devolverá GET /api/generaciones/{id}/individuos, para que la vista Rutas pueda reproducirla.
// El backend real (genetico.py) debe producir datos con esta misma estructura.

/** Generador pseudoaleatorio reproducible (mulberry32) */
export function crearAzar(semilla = 42) {
  let a = semilla >>> 0
  const azar = () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  azar.entero = (n) => Math.floor(azar() * n)
  return azar
}

function barajar(arr, azar) {
  const a = arr.slice()
  for (let i = a.length - 1; i > 0; i--) {
    const j = azar.entero(i + 1)
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

/** Dos puntos de corte [c1, c2) que dejan un segmento de 1 a n−1 genes */
function puntosDeCorte(n, azar) {
  for (;;) {
    let c1 = azar.entero(n + 1)
    let c2 = azar.entero(n + 1)
    if (c1 === c2) continue
    if (c1 > c2) [c1, c2] = [c2, c1]
    if (c1 === 0 && c2 === n) continue
    return [c1, c2]
  }
}

/** Cruce de orden (OX): copia el segmento del padre A y completa con el orden del padre B */
export function cruceOX(a, b, [c1, c2]) {
  const n = a.length
  const hijo = new Array(n).fill(null)
  const usados = new Set()
  for (let i = c1; i < c2; i++) {
    hijo[i] = a[i]
    usados.add(a[i])
  }
  let pos = c2 % n
  for (let k = 0; k < n; k++) {
    const gen = b[(c2 + k) % n]
    if (usados.has(gen)) continue
    hijo[pos] = gen
    usados.add(gen)
    pos = (pos + 1) % n
  }
  return hijo
}

/** Cruce parcialmente mapeado (PMX) */
export function crucePMX(a, b, [c1, c2]) {
  const n = a.length
  const hijo = new Array(n).fill(null)
  for (let i = c1; i < c2; i++) hijo[i] = a[i]
  const enSegmento = new Map()
  for (let i = c1; i < c2; i++) enSegmento.set(a[i], i)
  for (let i = c1; i < c2; i++) {
    const gen = b[i]
    if (enSegmento.has(gen)) continue
    let pos = i
    while (pos >= c1 && pos < c2) pos = b.indexOf(a[pos])
    hijo[pos] = gen
  }
  for (let i = 0; i < n; i++) if (hijo[i] == null) hijo[i] = b[i]
  return hijo
}

/**
 * Ejecuta el algoritmo genético para el problema de la ruta más corta sobre un grafo.
 * @param {object} p
 * @param {number[]} p.nodos        ids de los hotspots del grafo
 * @param {(a:number,b:number)=>number} p.distancia  distancia en metros entre dos hotspots
 * @param {object} p.parametros     tam_poblacion, n_generaciones, tam_torneo, prob_cruce,
 *                                  prob_mutacion, op_cruce, op_mutacion, semilla, ruta_cerrada
 */
export function ejecutarAG({ nodos, distancia, parametros }) {
  const {
    tam_poblacion: P,
    n_generaciones: G,
    tam_torneo: K,
    prob_cruce: pc,
    prob_mutacion: pm,
    op_cruce = 'OX',
    op_mutacion = 'swap',
    semilla = 42,
    ruta_cerrada = true,
  } = parametros
  const azar = crearAzar(semilla)
  const n = nodos.length

  const aptitud = (perm) => {
    let d = 0
    for (let i = 0; i < perm.length - 1; i++) d += distancia(perm[i], perm[i + 1])
    if (ruta_cerrada && perm.length > 1) d += distancia(perm[perm.length - 1], perm[0])
    return d
  }

  const resumir = (numero, individuos, operaciones) => {
    let mejor = individuos[0]
    let peor = individuos[0]
    let suma = 0
    for (const ind of individuos) {
      if (ind.distancia < mejor.distancia) mejor = ind
      if (ind.distancia > peor.distancia) peor = ind
      suma += ind.distancia
    }
    return {
      numero,
      mejor_fitness: mejor.distancia,
      fitness_promedio: suma / individuos.length,
      peor_fitness: peor.distancia,
      mejor_permutacion: mejor.permutacion,
      individuos,
      operaciones,
    }
  }

  // Generación 0: permutaciones al azar
  let poblacion = Array.from({ length: P }, (_, i) => {
    const permutacion = n > 1 ? barajar(nodos, azar) : nodos.slice()
    return {
      posicion: i,
      permutacion,
      distancia: aptitud(permutacion),
      origen: 'aleatorio',
      padre_1: null,
      padre_2: null,
    }
  })
  const generaciones = [resumir(0, poblacion, null)]

  const torneo = (hijo) => {
    const participantes = Array.from({ length: Math.min(K, P) }, () => azar.entero(P))
    let ganador = participantes[0]
    for (const p of participantes) if (poblacion[p].distancia < poblacion[ganador].distancia) ganador = p
    return { participantes, ganador, hijo }
  }

  for (let g = 1; g <= G; g++) {
    const seleccion_azar = []
    const torneos = []
    const cruces = []
    const mutaciones = []
    const nueva = []
    for (let i = 0; i < P; i++) {
      // Selección al azar + torneo (dos veces: un torneo por padre)
      const t1 = torneo(i)
      const t2 = torneo(i)
      torneos.push(t1, t2)
      seleccion_azar.push(...t1.participantes, ...t2.participantes)
      const a = poblacion[t1.ganador].permutacion
      const b = poblacion[t2.ganador].permutacion

      // Cruce por permutación
      let hijo
      let corte = null
      const aplicado = n > 2 && azar() < pc
      if (aplicado) {
        corte = puntosDeCorte(n, azar)
        hijo = op_cruce === 'PMX' ? crucePMX(a, b, corte) : cruceOX(a, b, corte)
      } else {
        hijo = a.slice()
      }
      cruces.push({ padres: [t1.ganador, t2.ganador], puntos_corte: corte, hijo: i, aplicado })

      // Mutación por permutación
      let origen = 'cruce'
      if (n > 1 && azar() < pm) {
        let p1 = azar.entero(n)
        let p2 = azar.entero(n)
        while (p2 === p1) p2 = azar.entero(n)
        if (p1 > p2) [p1, p2] = [p2, p1]
        if (op_mutacion === 'inversion') {
          hijo = [...hijo.slice(0, p1), ...hijo.slice(p1, p2 + 1).reverse(), ...hijo.slice(p2 + 1)]
        } else {
          hijo = hijo.slice()
          ;[hijo[p1], hijo[p2]] = [hijo[p2], hijo[p1]]
        }
        mutaciones.push({ individuo: i, posiciones: [p1, p2], tipo: op_mutacion })
        origen = 'mutacion'
      }
      nueva.push({
        posicion: i,
        permutacion: hijo,
        distancia: aptitud(hijo),
        origen,
        padre_1: t1.ganador,
        padre_2: t2.ganador,
      })
    }
    poblacion = nueva
    generaciones.push(resumir(g, nueva, { seleccion_azar, torneos, cruces, mutaciones }))
  }

  // Mejor ruta histórica (la que recorre el agente en Simular)
  let mejor = generaciones[0]
  for (const gen of generaciones) if (gen.mejor_fitness < mejor.mejor_fitness) mejor = gen
  return {
    generaciones,
    mejor_distancia: mejor.mejor_fitness,
    ruta_optima: mejor.mejor_permutacion,
    generacion_mejor: mejor.numero,
  }
}
