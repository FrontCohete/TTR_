import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/index.js'
import { ArrowLeft, LoaderCircle, Navigation, Network, TriangleAlert } from 'lucide-react'
import { useAgentes, useAnalisisVigente, useGeneraciones, useHotspots, useIndividuos } from '../../api/consultas.js'
import { useSesion } from '../../store/sesion.js'
import { useTitulo } from '../../hooks/useTitulo.js'
import { useEsEscritorio, useEsMovil } from '../../hooks/useMedia.js'
import { haversine } from '../../lib/geo.js'
import { colorGrafo, textoSobre } from '../../lib/colores.js'
import { fmtDistancia, fmtEntero, fmtPct, plural } from '../../lib/formato.js'
import Boton from '../../components/ui/Boton.jsx'
import FlujoAG from './FlujoAG.jsx'
import DetalleEtapa from './DetalleEtapa.jsx'
import Reproductor from './Reproductor.jsx'
import GraficaAptitud from './GraficaAptitud.jsx'
import MiniMapaRuta from './MiniMapaRuta.jsx'
import { useReproductor } from './useReproductor.js'
import s from './Rutas.module.css'

export default function Rutas() {
  useTitulo('Rutas')
  const ejecuciones = useSesion((st) => st.ejecuciones)
  if (!ejecuciones.length) return <SinAgentes />
  return <VistaRutas ejecuciones={ejecuciones} />
}

function SinAgentes() {
  return (
    <div className={s.vacio}>
      <div className={s.vacioCaja}>
        <span className={s.vacioIcono} aria-hidden="true">
          <Network size={26} />
        </span>
        <h1 className={s.vacioTitulo}>Aún no hay agentes</h1>
        <p className={s.vacioTexto}>
          Los agentes se crean en Analizar: elige cuántos grafos quieres y pulsa “Generar agentes”. Cada grafo tendrá su
          propio algoritmo genético.
        </p>
        <Boton variante="primario" icono={ArrowLeft} a="/analizar">
          Ir a Analizar
        </Boton>
      </div>
    </div>
  )
}

function VistaRutas({ ejecuciones }) {
  const navegar = useNavigate()
  const esMovil = useEsMovil()
  const esEscritorio = useEsEscritorio()
  const analisis = useAnalisisVigente()
  const hotspots = useHotspots(analisis.data?.id_analisis)
  const consultasAgentes = useAgentes(ejecuciones.map((e) => e.id_ejecucion))
  const [activo, setActivo] = useState(ejecuciones[0].id_ejecucion)

  const indiceActivo = Math.max(
    0,
    ejecuciones.findIndex((e) => e.id_ejecucion === activo),
  )
  const ej = ejecuciones[indiceActivo]
  const agente = consultasAgentes[indiceActivo]?.data
  const terminado = agente?.estado === 'terminado'
  const color = colorGrafo(ej.numero, ej.color)
  const parametros = agente?.parametros
  const cerrada = parametros?.ruta_cerrada !== false

  const generaciones = useGeneraciones(ej.id_ejecucion, terminado)
  const total = generaciones.data ? generaciones.data.length - 1 : (parametros?.n_generaciones ?? 0)
  const r = useReproductor(generaciones.data ? total : 0, ej.id_ejecucion)
  const { gen } = r.pos

  const idGen = (g) => generaciones.data?.[g]?.id_generacion
  const enAutomatico = r.modo === 'auto' && r.reproduciendo
  const actual = useIndividuos(terminado && !enAutomatico ? idGen(gen) : null)
  const necesitaPrevia = gen > 0 && r.pos.etapa >= 2 && r.pos.etapa <= 5
  const previa = useIndividuos(terminado && necesitaPrevia && !enAutomatico ? idGen(gen - 1) : null)
  // En automático no hace falta el detalle de cada individuo: basta el resumen de la generación
  const rapido = enAutomatico

  // Se adelanta la descarga de la siguiente generación para que la reproducción no parpadee
  const clienteConsultas = useQueryClient()
  useEffect(() => {
    if (!terminado || enAutomatico) return
    const siguienteId = idGen(gen + 1)
    if (siguienteId != null) {
      clienteConsultas.prefetchQuery({
        queryKey: ['generacion', siguienteId, 'individuos'],
        queryFn: () => api.obtenerIndividuos(siguienteId),
        staleTime: Infinity,
      })
    }
  }, [gen, terminado, enAutomatico, generaciones.data]) // eslint-disable-line react-hooks/exhaustive-deps

  const info = useMemo(() => {
    const m = new Map()
    hotspots.data?.features.forEach((f) => m.set(f.properties.id_hotspot, f.properties))
    return m
  }, [hotspots.data])

  const distancia = useMemo(() => {
    const cache = new Map()
    return (a, b) => {
      const k = a < b ? `${a}-${b}` : `${b}-${a}`
      if (!cache.has(k)) {
        const pa = info.get(a)?.centroide
        const pb = info.get(b)?.centroide
        cache.set(k, pa && pb ? haversine(pa, pb) : 0)
      }
      return cache.get(k)
    }
  }, [info])

  const resumen = generaciones.data?.[gen]
  const resumenPrevio = gen > 0 ? generaciones.data?.[gen - 1] : null
  const mejorHistorico = useMemo(() => {
    if (!generaciones.data) return null
    let m = generaciones.data[0]
    for (let g = 0; g <= gen; g++) if (generaciones.data[g].mejor_fitness < m.mejor_fitness) m = generaciones.data[g]
    return m
  }, [generaciones.data, gen])
  const inicial = generaciones.data?.[0]

  const metas = useMemo(() => {
    const P = parametros?.tam_poblacion
    const ops = actual.data?.numero === gen ? actual.data.operaciones : null
    const n = ej.n_nodos ?? ej.hotspots?.length
    // Con élite, los hijos que pasan por torneo y cruce son P − n_elite
    const H = ops ? ops.cruces.length : P ? P - Math.min(parametros.n_elite ?? 0, P - 1) : 0
    return [
      P ? `${fmtEntero(P)} rutas de ${n} hotspots` : null,
      inicial ? `Mejor inicial: ${fmtDistancia(inicial.mejor_fitness)}` : null,
      P ? `${fmtEntero(H * 2)} grupos de ${parametros.tam_torneo}` : null,
      P ? `${fmtEntero(H * 2)} ganadores, ${fmtEntero(H)} parejas` : null,
      ops
        ? `${fmtEntero(ops.cruces.filter((c) => c.puntos_corte).length)} de ${fmtEntero(H)} con ${parametros.op_cruce}`
        : parametros
          ? `Operador ${parametros.op_cruce}`
          : null,
      ops
        ? plural(ops.mutaciones.length, 'mutación', 'mutaciones')
        : parametros
          ? `Probabilidad ${fmtPct(parametros.prob_mutacion)}`
          : null,
      resumen && gen > 0 ? `Mejor: ${fmtDistancia(resumen.mejor_fitness)}` : null,
    ]
  }, [parametros, actual.data, gen, ej, inicial, resumen])

  const todosTerminados = consultasAgentes.every((q) => q.data?.estado === 'terminado')
  const mejoraTotal = inicial && mejorHistorico ? 1 - mejorHistorico.mejor_fitness / inicial.mejor_fitness : null

  return (
    <div className={s.rutas}>
      <h1 className="solo-lectores">Rutas: algoritmo genético de cada agente</h1>
      <header className={s.cabeza}>
        <div className={s.tabs} role="tablist" aria-label="Agentes">
          {ejecuciones.map((e, i) => {
            const q = consultasAgentes[i]?.data
            const c = colorGrafo(e.numero, e.color)
            const sel = e.id_ejecucion === activo
            return (
              <button
                key={e.id_ejecucion}
                role="tab"
                type="button"
                aria-selected={sel}
                className={`${s.tab} ${sel ? s.tabActiva : ''}`}
                style={{ '--c': c, '--tc': textoSobre(c) }}
                onClick={() => setActivo(e.id_ejecucion)}
              >
                <span className={s.tabNumero}>{e.numero}</span>
                <span className={s.tabTextos}>
                  <span className={s.tabNombre}>Agente {e.numero}</span>
                  <span className={s.tabMeta}>
                    {q?.estado === 'terminado' ? (
                      fmtDistancia(q.mejor_distancia)
                    ) : q?.estado === 'error' ? (
                      'Con error'
                    ) : (
                      <>
                        <LoaderCircle size={11} className={s.giro} aria-hidden="true" /> Calculando
                        {q?.avance != null ? ` ${q.avance}%` : '…'}
                      </>
                    )}
                  </span>
                </span>
              </button>
            )
          })}
        </div>
        <Boton
          variante="primario"
          icono={Navigation}
          disabled={!todosTerminados}
          onClick={() => navegar('/simular')}
          title={todosTerminados ? 'Ver a los agentes recorrer sus rutas' : 'Espera a que terminen todos los agentes'}
          className={s.botonSimular}
        >
          {esMovil ? 'Simular' : 'Simular recorrido'}
        </Boton>
      </header>

      {!terminado ? (
        <div className={s.esperando} role="status">
          {agente?.estado === 'error' ? (
            <>
              <TriangleAlert size={22} aria-hidden="true" />
              <p>El algoritmo del agente {ej.numero} falló. Vuelve a Analizar y genera los agentes de nuevo.</p>
            </>
          ) : (
            <>
              <LoaderCircle size={22} className={s.giro} aria-hidden="true" />
              <p>
                El backend está ejecutando el algoritmo genético del agente {ej.numero}
                {agente?.avance != null ? ` (${agente.avance}%)` : ''}. La reproducción empieza en cuanto termine.
              </p>
            </>
          )}
        </div>
      ) : (
        <div className={s.cuerpo}>
          {!esMovil && (
            <div className={s.columnaFlujo}>
              <FlujoAG pos={r.pos} total={total} metas={metas} reproduciendo={r.reproduciendo} alElegir={r.irAEtapa} />
            </div>
          )}
          <div className={s.columnaCentro}>
            {esMovil && (
              <FlujoAG
                pos={r.pos}
                total={total}
                metas={metas}
                reproduciendo={r.reproduciendo}
                alElegir={r.irAEtapa}
                horizontal
              />
            )}
            <DetalleEtapa
              pos={r.pos}
              actual={actual.data}
              previa={previa.data}
              resumen={resumen}
              resumenPrevio={resumenPrevio}
              info={info}
              color={color}
              parametros={parametros}
              distancia={distancia}
              cerrada={cerrada}
              nNodos={ej.n_nodos ?? ej.hotspots?.length}
              numeroGrafo={ej.numero}
              rapido={rapido}
            />
            {!esEscritorio && (
              <Lateral
                resumen={resumen}
                mejorHistorico={mejorHistorico}
                mejoraTotal={mejoraTotal}
                generaciones={generaciones.data}
                gen={gen}
                total={total}
                color={color}
                info={info}
                cerrada={cerrada}
                nodos={ej.hotspots}
              />
            )}
          </div>
          {esEscritorio && (
            <div className={s.columnaLateral}>
              <Lateral
                resumen={resumen}
                mejorHistorico={mejorHistorico}
                mejoraTotal={mejoraTotal}
                generaciones={generaciones.data}
                gen={gen}
                total={total}
                color={color}
                info={info}
                cerrada={cerrada}
                nodos={ej.hotspots}
              />
            </div>
          )}
        </div>
      )}

      {terminado && <Reproductor r={r} total={total} compacto={esMovil} />}
    </div>
  )
}

function Lateral({ resumen, mejorHistorico, mejoraTotal, generaciones, gen, total, color, info, cerrada, nodos }) {
  return (
    <aside className={s.lateral} aria-label="Evolución del agente">
      <div className={s.marcador}>
        <div>
          <p className={s.marcadorEtiqueta}>Generación</p>
          <p className={s.marcadorValor}>
            <span className="num">{fmtEntero(gen)}</span>
            <span className={s.marcadorTotal}> / {fmtEntero(total)}</span>
          </p>
        </div>
        <div>
          <p className={s.marcadorEtiqueta}>Mejor hasta ahora</p>
          <p className={s.marcadorValor}>
            <span className="num">{mejorHistorico ? fmtDistancia(mejorHistorico.mejor_fitness) : '—'}</span>
          </p>
          {mejorHistorico && (
            <p className={s.marcadorNota}>
              {mejorHistorico.numero === 0
                ? 'de la población inicial'
                : `en la generación ${fmtEntero(mejorHistorico.numero)}${mejoraTotal > 0 ? `, ${fmtPct(mejoraTotal)} más corta que al inicio` : ''}`}
            </p>
          )}
        </div>
      </div>
      <GraficaAptitud generaciones={generaciones} hasta={gen} color={color} />
      <MiniMapaRuta perm={resumen?.mejor_permutacion} info={info} color={color} cerrada={cerrada} nodos={nodos} />
    </aside>
  )
}