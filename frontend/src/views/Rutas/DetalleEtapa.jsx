import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ChevronLeft, ChevronRight, LoaderCircle, RotateCcw, Trophy } from 'lucide-react'
import TiraRuta from './TiraRuta.jsx'
import BarrasAptitud from './BarrasAptitud.jsx'
import { ETAPAS_AG } from './etapas.js'
import { NOCHE, sobreBlanco, textoSobre } from '../../lib/colores.js'
import Boton from '../../components/ui/Boton.jsx'
import { fmtDistancia, fmtEntero, fmtPct, plural } from '../../lib/formato.js'
import s from './Rutas.module.css'

/** Navegador ‹ 3 de 50 › para recorrer operaciones de una misma etapa */
function Navegador({ indice, total, alCambiar, etiqueta }) {
  if (total <= 1) return null
  return (
    <div className={s.navegador} role="group" aria-label={etiqueta}>
      <Boton
        tamano="s"
        variante="fantasma"
        soloIcono
        icono={ChevronLeft}
        onClick={() => alCambiar((indice - 1 + total) % total)}
      >
        Anterior
      </Boton>
      <span className={s.navegadorTexto}>
        {etiqueta} <strong className="num">{fmtEntero(indice + 1)}</strong> de{' '}
        <span className="num">{fmtEntero(total)}</span>
      </span>
      <Boton
        tamano="s"
        variante="fantasma"
        soloIcono
        icono={ChevronRight}
        onClick={() => alCambiar((indice + 1) % total)}
      >
        Siguiente
      </Boton>
    </div>
  )
}

const tramosDe = (perm, distancia, cerrada) => {
  const t = []
  for (let i = 0; i < perm.length - 1; i++) t.push(distancia(perm[i], perm[i + 1]))
  if (cerrada && perm.length > 1) t.push(distancia(perm[perm.length - 1], perm[0]))
  return t
}

/** Los dos torneos (A y B) que eligieron a los padres del hijo en la posición h */
const torneosDe = (ops, h) => ops.torneos.filter((t) => t.hijo === h)

/**
 * Elitismo: las rutas con origen "elite" pasan intactas de la generación anterior, sin torneo,
 * cruce ni mutación. Por eso el navegador de hijos recorre solo `operaciones.cruces`.
 */
function NotaElite({ actual }) {
  const elites = actual.individuos.filter((x) => x.origen === 'elite')
  if (!elites.length) return null
  const lista = elites.map((e) => `#${e.posicion}`).join(', ')
  const previas = elites.map((e) => `#${e.padre_1}`).join(', ')
  return (
    <p className={s.notaPequena}>
      {elites.length === 1 ? `La ruta ${lista} no se forma así: es la ` : `Las rutas ${lista} no se forman así: son la `}
      <strong>élite</strong>, {elites.length === 1 ? 'una copia intacta de la mejor ruta' : 'copias intactas de las mejores rutas'}{' '}
      de la generación anterior ({previas}).
    </p>
  )
}

/** Deshace la mutación para obtener el hijo tal como salió del cruce */
const antesDeMutar = (perm, mut) => {
  const [a, b] = mut.posiciones
  if (mut.tipo === 'inversion') return [...perm.slice(0, a), ...perm.slice(a, b + 1).reverse(), ...perm.slice(b + 1)]
  const r = perm.slice()
  ;[r[a], r[b]] = [r[b], r[a]]
  return r
}

export default function DetalleEtapa({
  pos,
  actual,
  previa,
  resumen,
  resumenPrevio,
  info,
  color,
  parametros,
  distancia,
  cerrada,
  nNodos,
  numeroGrafo,
  rapido = false,
}) {
  const etapa = ETAPAS_AG[pos.etapa]
  const [hijo, setHijo] = useState(0)
  const [mutacion, setMutacion] = useState(0)
  useEffect(() => {
    setMutacion(0)
  }, [pos.gen])

  const listo = actual && actual.numero === pos.gen && (pos.gen === 0 || (previa && previa.numero === pos.gen - 1))
  const P = parametros?.tam_poblacion ?? 0
  // Índice dentro de los hijos con torneo y cruce (la élite no cuenta)
  const nHijos = actual?.operaciones?.cruces?.length ?? 0
  const k = Math.min(hijo, Math.max(0, nHijos - 1))

  let contenido
  if (rapido) {
    contenido = <Rapido resumen={resumen} resumenPrevio={resumenPrevio} info={info} color={color} cerrada={cerrada} />
  } else if (!listo) {
    contenido = (
      <div className={s.detalleCargando} role="status">
        <LoaderCircle size={18} className={s.giro} aria-hidden="true" /> Cargando la generación {fmtEntero(pos.gen)}…
      </div>
    )
  } else if (pos.etapa === 0) {
    contenido = (
      <Permutacion
        actual={actual}
        info={info}
        color={color}
        cerrada={cerrada}
        nNodos={nNodos}
        P={P}
        numeroGrafo={numeroGrafo}
      />
    )
  } else if (pos.etapa === 1) {
    contenido = <Evaluacion actual={actual} info={info} color={color} distancia={distancia} cerrada={cerrada} />
  } else if (pos.etapa === 2) {
    contenido = (
      <SeleccionAzar
        actual={actual}
        previa={previa}
        hijo={k}
        setHijo={setHijo}
        color={color}
        K={parametros.tam_torneo}
      />
    )
  } else if (pos.etapa === 3) {
    contenido = (
      <Torneo
        actual={actual}
        previa={previa}
        hijo={k}
        setHijo={setHijo}
        info={info}
        color={color}
        cerrada={cerrada}
      />
    )
  } else if (pos.etapa === 4) {
    contenido = (
      <Cruce
        actual={actual}
        previa={previa}
        hijo={k}
        setHijo={setHijo}
        info={info}
        color={color}
        cerrada={cerrada}
        parametros={parametros}
      />
    )
  } else if (pos.etapa === 5) {
    contenido = (
      <Mutacion
        actual={actual}
        indice={mutacion}
        setIndice={setMutacion}
        info={info}
        color={color}
        cerrada={cerrada}
        parametros={parametros}
      />
    )
  } else {
    contenido = (
      <EvaluacionGen
        actual={actual}
        resumen={resumen}
        resumenPrevio={resumenPrevio}
        info={info}
        color={color}
        cerrada={cerrada}
      />
    )
  }

  return (
    <section className={s.detalle} aria-labelledby="titulo-etapa" aria-live="polite">
      <header className={s.detalleCabeza}>
        <span className={s.detalleIcono} aria-hidden="true">
          <etapa.icono size={20} />
        </span>
        <div>
          <p className={s.detalleSup}>
            {pos.gen === 0 ? 'Generación 0 (población inicial)' : `Generación ${fmtEntero(pos.gen)}`}, etapa{' '}
            {pos.etapa + 1} de 7
          </p>
          <h2 id="titulo-etapa" className={s.detalleTitulo}>
            {etapa.nombre}
          </h2>
        </div>
      </header>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={rapido ? 'rapido' : `${pos.gen}-${pos.etapa}-${listo}`}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: [0.2, 0, 0, 1] }}
          className={s.detalleCuerpo}
        >
          {contenido}
        </motion.div>
      </AnimatePresence>
    </section>
  )
}

// ---------------------------------------------------------------- Modo automático
function Rapido({ resumen, resumenPrevio, info, color, cerrada }) {
  if (!resumen) return null
  const delta = resumenPrevio ? resumen.mejor_fitness - resumenPrevio.mejor_fitness : null
  return (
    <>
      <p className={s.explicacion}>
        En automático el algoritmo corre generación tras generación y solo se muestra el resultado de cada una. Pausa o
        cambia a paso a paso para ver la selección, el torneo, el cruce y la mutación.
      </p>
      <dl className={s.estadisticas}>
        <div>
          <dt>Mejor</dt>
          <dd className="num">{fmtDistancia(resumen.mejor_fitness)}</dd>
          {delta != null && delta !== 0 && (
            <dd className={`${s.cambio} ${delta < 0 ? s.mejora : s.empeora}`}>
              {`${delta < 0 ? '−' : '+'}${fmtDistancia(Math.abs(delta))} vs. anterior`}
            </dd>
          )}
        </div>
        <div>
          <dt>Promedio</dt>
          <dd className="num">{fmtDistancia(resumen.fitness_promedio)}</dd>
        </div>
        <div>
          <dt>Peor</dt>
          <dd className="num">{fmtDistancia(resumen.peor_fitness)}</dd>
        </div>
      </dl>
      <div className={s.destacado}>
        <p className={s.destacadoTitulo}>Mejor ruta de la generación</p>
        <TiraRuta perm={resumen.mejor_permutacion} info={info} color={color} cerrada={cerrada} animar />
      </div>
    </>
  )
}

// ---------------------------------------------------------------- 1 · Permutación
function Permutacion({ actual, info, color, cerrada, nNodos, P, numeroGrafo }) {
  const [todas, setTodas] = useState(false)
  const lista = todas ? actual.individuos : actual.individuos.slice(0, 8)
  return (
    <>
      <p className={s.explicacion}>
        Cada individuo es una <strong>ruta</strong>: un orden posible para visitar los {fmtEntero(nNodos)} hotspots del
        grafo {numeroGrafo}. Se generan {fmtEntero(P)} permutaciones al azar; esa es la población inicial.
      </p>
      <div className={`${s.listaTiras} ${todas ? s.listaTirasLarga : ''}`}>
        {lista.map((ind, i) => (
          <motion.div
            key={ind.posicion}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2, delay: Math.min(i, 8) * 0.03 }}
          >
            <TiraRuta
              perm={ind.permutacion}
              info={info}
              color={color}
              cerrada={cerrada}
              tam="s"
              etiqueta={`#${ind.posicion}`}
            />
          </motion.div>
        ))}
      </div>
      <Boton tamano="s" variante="fantasma" onClick={() => setTodas((v) => !v)}>
        {todas ? 'Mostrar solo las primeras 8' : `Mostrar las ${fmtEntero(actual.individuos.length)} rutas`}
      </Boton>
    </>
  )
}

// ---------------------------------------------------------------- 2 · Función objetivo
function Evaluacion({ actual, info, color, distancia, cerrada }) {
  const mejor = actual.individuos.reduce((m, x) => (x.distancia < m.distancia ? x : m), actual.individuos[0])
  return (
    <>
      <p className={s.explicacion}>
        La aptitud de una ruta es su <strong>distancia total</strong>: la suma de los tramos en línea recta entre
        hotspots consecutivos{cerrada ? ', más el regreso al primero' : ''}. Menos distancia es mejor.
      </p>
      <p className={s.formula} aria-label="Fórmula de la función objetivo">
        f(π) = d(π<sub>1</sub>, π<sub>2</sub>) + d(π<sub>2</sub>, π<sub>3</sub>) + … +{' '}
        {cerrada ? (
          <>
            d(π<sub>n</sub>, π<sub>1</sub>)
          </>
        ) : (
          <>
            d(π<sub>n−1</sub>, π<sub>n</sub>)
          </>
        )}
      </p>
      <div className={s.destacado}>
        <p className={s.destacadoTitulo}>
          Mejor ruta inicial, #{mejor.posicion}: <strong>{fmtDistancia(mejor.distancia)}</strong>
        </p>
        <TiraRuta
          perm={mejor.permutacion}
          info={info}
          color={color}
          cerrada={cerrada}
          tramos={tramosDe(mejor.permutacion, distancia, cerrada)}
        />
        <p className={s.notaPequena}>Los números bajo la línea son los kilómetros de cada tramo.</p>
      </div>
      <BarrasAptitud individuos={actual.individuos} color={color} />
    </>
  )
}

// ---------------------------------------------------------------- 3 · Selección al azar
function SeleccionAzar({ actual, previa, hijo, setHijo, color, K }) {
  const ops = actual.operaciones
  const [tA, tB] = torneosDe(ops, ops.cruces[hijo].hijo)
  const enA = new Set(tA.participantes)
  const enB = new Set(tB.participantes)
  const min = Math.min(...previa.individuos.map((x) => x.distancia))
  const max = Math.max(...previa.individuos.map((x) => x.distancia))
  return (
    <>
      <p className={s.explicacion}>
        Para formar cada hijo se toman <strong>dos grupos de {K} rutas al azar</strong> de la generación{' '}
        {fmtEntero(previa.numero)}. Cada grupo competirá en un torneo. Una misma ruta puede salir elegida varias veces.
      </p>
      <Navegador indice={hijo} total={ops.cruces.length} alCambiar={setHijo} etiqueta="Hijo" />
      <div className={s.poblacion} role="list" aria-label={`Población de la generación ${previa.numero}`}>
        {previa.individuos.map((ind, i) => {
          const a = enA.has(i)
          const b = enB.has(i)
          const tono = 1 - (ind.distancia - min) / (max - min || 1)
          const fondo = sobreBlanco(NOCHE, 0.08 + tono * 0.74)
          return (
            <span
              key={i}
              role="listitem"
              className={`${s.ficha} ${a ? s.fichaA : ''} ${b ? s.fichaB : ''}`}
              style={{ '--c': color, '--fondo': fondo, '--tc': textoSobre(fondo) }}
              title={`Ruta #${i}: ${fmtDistancia(ind.distancia)}`}
            >
              {i}
              {(a || b) && <span className={s.fichaMarca}>{a && b ? 'AB' : a ? 'A' : 'B'}</span>}
            </span>
          )
        })}
      </div>
      <div className={s.gruposAzar}>
        <p>
          <span className={s.marcaA} style={{ background: color, color: textoSobre(color) }}>
            A
          </span>{' '}
          Grupo del torneo A: {tA.participantes.map((x) => `#${x}`).join(', ')}
        </p>
        <p>
          <span className={s.marcaB}>B</span> Grupo del torneo B: {tB.participantes.map((x) => `#${x}`).join(', ')}
        </p>
      </div>
      <p className={s.notaPequena}>El tono de cada ficha indica su distancia: más oscuro, ruta más corta.</p>
      <NotaElite actual={actual} />
    </>
  )
}

// ---------------------------------------------------------------- 4 · Torneo
function Torneo({ actual, previa, hijo, setHijo, info, color, cerrada }) {
  const ops = actual.operaciones
  const h = ops.cruces[hijo].hijo
  const torneos = torneosDe(ops, h)
  return (
    <>
      <p className={s.explicacion}>
        En cada torneo <strong>gana la ruta más corta</strong> del grupo. Los dos ganadores serán los padres del hijo #
        {h}.
      </p>
      <Navegador indice={hijo} total={ops.cruces.length} alCambiar={setHijo} etiqueta="Hijo" />
      <div className={s.torneos}>
        {torneos.map((t, k) => (
          <div key={k} className={s.torneo}>
            <p className={s.torneoTitulo}>
              <span
                className={k === 0 ? s.marcaA : s.marcaB}
                style={k === 0 ? { background: color, color: textoSobre(color) } : undefined}
              >
                {k === 0 ? 'A' : 'B'}
              </span>
              Torneo {k === 0 ? 'A' : 'B'}
            </p>
            <ul className={s.participantes}>
              {t.participantes.map((p, j) => {
                const ind = previa.individuos[p]
                const gana = p === t.ganador && t.participantes.indexOf(p) === j
                return (
                  <li key={j} className={`${s.participante} ${gana ? s.ganador : ''}`}>
                    <span className={s.participanteId}>#{p}</span>
                    <span className={s.participanteDist}>{fmtDistancia(ind.distancia)}</span>
                    {gana && (
                      <span className={s.gana}>
                        <Trophy size={14} aria-hidden="true" /> Gana
                      </span>
                    )}
                  </li>
                )
              })}
            </ul>
            <TiraRuta
              perm={previa.individuos[t.ganador].permutacion}
              info={info}
              color={k === 0 ? color : 'var(--ttr-noche)'}
              cerrada={cerrada}
              tam="s"
            />
          </div>
        ))}
      </div>
      <NotaElite actual={actual} />
    </>
  )
}

// ---------------------------------------------------------------- 5 · Cruce
function Cruce({ actual, previa, hijo, setHijo, info, color, cerrada, parametros }) {
  const nHijos = actual.operaciones.cruces.length
  const c = actual.operaciones.cruces[hijo]
  const h = c.hijo
  const A = previa.individuos[c.padres[0]].permutacion
  const B = previa.individuos[c.padres[1]].permutacion
  const mut = actual.operaciones.mutaciones.find((m) => m.individuo === h)
  const resultado = mut ? antesDeMutar(actual.individuos[h].permutacion, mut) : actual.individuos[h].permutacion
  const aplicados = actual.operaciones.cruces.filter((x) => x.aplicado !== false && x.puntos_corte).length
  const origen = c.puntos_corte
    ? resultado.map((_, i) => (i >= c.puntos_corte[0] && i < c.puntos_corte[1] ? 'a' : 'b'))
    : resultado.map(() => 'a')
  const esPMX = parametros.op_cruce === 'PMX'

  return (
    <>
      <p className={s.explicacion}>
        {esPMX ? (
          <>
            <strong>Cruce parcialmente mapeado (PMX):</strong> el hijo copia el segmento del padre A entre los puntos de
            corte y acomoda el resto según el padre B, usando el segmento como tabla de equivalencias para no repetir
            hotspots.
          </>
        ) : (
          <>
            <strong>Cruce de orden (OX):</strong> el hijo copia el segmento del padre A entre los puntos de corte y
            completa los lugares vacíos con los hotspots que faltan, en el orden en que aparecen en el padre B.
          </>
        )}
      </p>
      <Navegador indice={hijo} total={nHijos} alCambiar={setHijo} etiqueta="Hijo" />
      {c.puntos_corte ? (
        <div className={s.cruce}>
          <TiraRuta
            perm={A}
            info={info}
            color={color}
            cerrada={cerrada}
            segmento={c.puntos_corte}
            etiqueta="A"
            valor={`#${c.padres[0]}`}
          />
          <TiraRuta
            perm={B}
            info={info}
            color="var(--ttr-noche)"
            cerrada={cerrada}
            etiqueta="B"
            valor={`#${c.padres[1]}`}
          />
          <div className={s.flechaCruce} aria-hidden="true" />
          <TiraRuta
            perm={resultado}
            info={info}
            color={color}
            cerrada={cerrada}
            origen={origen}
            etiqueta="Hijo"
            valor={`#${h}`}
            animar
          />
          <p className={s.leyendaCruce}>
            <span className={s.muestraA} style={{ background: color }} /> Del padre A (posiciones{' '}
            {c.puntos_corte[0] + 1} a {c.puntos_corte[1]})
            <span className={s.muestraB} /> Del padre B, en su orden
          </p>
        </div>
      ) : (
        <div className={s.cruce}>
          <TiraRuta perm={A} info={info} color={color} cerrada={cerrada} etiqueta="A" valor={`#${c.padres[0]}`} />
          <p className={s.sinOperacion}>
            Este hijo no se cruzó (la probabilidad de cruce es {fmtPct(parametros.prob_cruce)}): copia tal cual al padre
            A.
          </p>
        </div>
      )}
      <p className={s.notaPequena}>
        En esta generación se cruzaron {fmtEntero(aplicados)} de {fmtEntero(nHijos)} hijos.
      </p>
      <NotaElite actual={actual} />
    </>
  )
}

// ---------------------------------------------------------------- 6 · Mutación
function Mutacion({ actual, indice, setIndice, info, color, cerrada, parametros }) {
  const muts = actual.operaciones.mutaciones
  const [mostrarDespues, setMostrarDespues] = useState(false)
  const m = muts[Math.min(indice, muts.length - 1)]
  useEffect(() => {
    setMostrarDespues(false)
    const t = setTimeout(() => setMostrarDespues(true), 650)
    return () => clearTimeout(t)
  }, [indice, actual.numero])

  const esInversion = parametros.op_mutacion === 'inversion'
  const explicacion = (
    <p className={s.explicacion}>
      {esInversion ? (
        <>
          <strong>Mutación por inversión:</strong> con probabilidad {fmtPct(parametros.prob_mutacion)} se invierte el
          orden de un tramo de la ruta.
        </>
      ) : (
        <>
          <strong>Mutación por intercambio:</strong> con probabilidad {fmtPct(parametros.prob_mutacion)} dos hotspots de
          la ruta cambian de lugar.
        </>
      )}{' '}
      Así la población no se vuelve idéntica y puede explorar rutas nuevas.
    </p>
  )
  if (!muts.length) {
    return (
      <>
        {explicacion}
        <p className={s.sinOperacion}>En esta generación ningún hijo mutó.</p>
      </>
    )
  }
  const despues = actual.individuos[m.individuo].permutacion
  const antes = antesDeMutar(despues, m)
  const [a, b] = m.posiciones
  const marcadas = new Set(esInversion ? Array.from({ length: b - a + 1 }, (_, k) => a + k) : [a, b])
  return (
    <>
      {explicacion}
      <Navegador
        indice={Math.min(indice, muts.length - 1)}
        total={muts.length}
        alCambiar={setIndice}
        etiqueta="Mutación"
      />
      <div className={s.mutacion}>
        <p className={s.destacadoTitulo}>
          Hijo #{m.individuo}:{' '}
          {esInversion
            ? `se invierte de la posición ${a + 1} a la ${b + 1}`
            : `se intercambian las posiciones ${a + 1} y ${b + 1}`}
        </p>
        <TiraRuta
          perm={mostrarDespues ? despues : antes}
          info={info}
          color={color}
          cerrada={cerrada}
          resaltadas={marcadas}
          animar
          etiqueta={mostrarDespues ? 'Después' : 'Antes'}
        />
        <Boton
          tamano="s"
          variante="fantasma"
          icono={RotateCcw}
          onClick={() => {
            setMostrarDespues(false)
            setTimeout(() => setMostrarDespues(true), 500)
          }}
        >
          Repetir animación
        </Boton>
      </div>
      <p className={s.notaPequena}>
        En esta generación {plural(muts.length, 'hijo mutó', 'hijos mutaron')} de {fmtEntero(actual.operaciones.cruces.length)}.
        {actual.individuos.some((x) => x.origen === 'elite') && ' La élite nunca muta.'}
      </p>
    </>
  )
}

// ---------------------------------------------------------------- 7 · Evaluación de la generación
function EvaluacionGen({ actual, resumen, resumenPrevio, info, color, cerrada }) {
  const mejor = actual.individuos.reduce((m, x) => (x.distancia < m.distancia ? x : m), actual.individuos[0])
  const delta = resumenPrevio ? resumen.mejor_fitness - resumenPrevio.mejor_fitness : null
  const origenes = useMemo(() => {
    const c = { cruce: 0, mutacion: 0, aleatorio: 0, elite: 0 }
    actual.individuos.forEach((x) => (c[x.origen] = (c[x.origen] ?? 0) + 1))
    return c
  }, [actual])
  return (
    <>
      <p className={s.explicacion}>
        Se calcula la distancia de las {fmtEntero(actual.individuos.length)} rutas ({fmtEntero(origenes.cruce)} por
        cruce, {fmtEntero(origenes.mutacion)} con mutación
        {origenes.elite ? ` y ${fmtEntero(origenes.elite)} élite, copiada de la generación anterior` : ''}). Esta
        población es la base de la siguiente generación.
      </p>
      <dl className={s.estadisticas}>
        <div>
          <dt>Mejor</dt>
          <dd className="num">{fmtDistancia(resumen.mejor_fitness)}</dd>
          {delta != null && (
            <dd className={`${s.cambio} ${delta < 0 ? s.mejora : delta > 0 ? s.empeora : ''}`}>
              {delta === 0
                ? 'Igual que la anterior'
                : `${delta < 0 ? '−' : '+'}${fmtDistancia(Math.abs(delta))} vs. anterior`}
            </dd>
          )}
        </div>
        <div>
          <dt>Promedio</dt>
          <dd className="num">{fmtDistancia(resumen.fitness_promedio)}</dd>
        </div>
        <div>
          <dt>Peor</dt>
          <dd className="num">{fmtDistancia(resumen.peor_fitness)}</dd>
        </div>
      </dl>
      <div className={s.destacado}>
        <p className={s.destacadoTitulo}>Mejor ruta de la generación, #{mejor.posicion}</p>
        <TiraRuta perm={mejor.permutacion} info={info} color={color} cerrada={cerrada} />
        {mejor.origen === 'elite' && (
          <p className={s.notaPequena}>
            Es la élite: ningún hijo nuevo superó a la mejor ruta de la generación anterior, así que se conserva.
          </p>
        )}
      </div>
      <BarrasAptitud individuos={actual.individuos} color={color} />
    </>
  )
}