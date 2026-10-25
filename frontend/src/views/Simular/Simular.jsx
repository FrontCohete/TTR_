import { useMemo, useRef, useState } from 'react'
import { motion } from 'motion/react'
import { ArrowLeft, Flag, House, LoaderCircle, Pause, Play, RotateCcw, Route } from 'lucide-react'
import { api } from '../../api/index.js'
import { useAnalisisVigente, useHotspots, useLimite, useRutas, useRutasCalles } from '../../api/consultas.js'
import { useSesion } from '../../store/sesion.js'
import { useTitulo } from '../../hooks/useTitulo.js'
import { useEsMovil } from '../../hooks/useMedia.js'
import { colorGrafo, textoSobre } from '../../lib/colores.js'
import { fmtDistancia, fmtEntero, fmtReloj, plural } from '../../lib/formato.js'
import MapaGAM from '../../components/mapa/MapaGAM.jsx'
import PanelAdaptable from '../../components/ui/PanelAdaptable.jsx'
import Boton from '../../components/ui/Boton.jsx'
import Segmentado from '../../components/ui/Segmentado.jsx'
import Aviso from '../../components/ui/Aviso.jsx'
import CapaAgente from './CapaAgente.jsx'
import { VELOCIDAD_KMH, posicionEn, useSimulacion } from './useSimulacion.js'
import s from './Simular.module.css'

/** +55.8 % */
const fmtPct = (x) => `${x > 0 ? '+' : ''}${x.toLocaleString('es-MX', { maximumFractionDigits: 1 })} %`
/** 46 min, 1 h 12 min */
const fmtMinutos = (seg) => {
  const m = Math.round(seg / 60)
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`
}
/** La ruta trae el trazo por calles (GET /ruta-calles) y no la línea recta (GET /ruta) */
const esPorCalles = (r) => r?.properties?.distancia_recta_m != null

export default function Simular() {
  useTitulo('Simular')
  const ejecuciones = useSesion((st) => st.ejecuciones)
  if (!ejecuciones.length) {
    return (
      <div className={s.vacio}>
        <div className={s.vacioCaja}>
          <span className={s.vacioIcono} aria-hidden="true">
            <Route size={26} />
          </span>
          <h1 className={s.vacioTitulo}>No hay rutas para simular</h1>
          <p className={s.vacioTexto}>
            Primero genera agentes en Analizar. Cuando el algoritmo genético termine, aquí verás a cada agente recorrer
            su ruta.
          </p>
          <Boton variante="primario" icono={ArrowLeft} a="/analizar">
            Ir a Analizar
          </Boton>
        </div>
      </div>
    )
  }
  return <VistaSimular ejecuciones={ejecuciones} />
}

function VistaSimular({ ejecuciones }) {
  const esMovil = useEsMovil()
  const limite = useLimite()
  const analisis = useAnalisisVigente()
  const hotspots = useHotspots(analisis.data?.id_analisis)
  const ids = ejecuciones.map((e) => e.id_ejecucion)
  const consultasRecta = useRutas(ids)
  const consultasCalles = useRutasCalles(ids)

  // Por cada agente: el trazo por calles; si el servidor de ruteo falló, la línea recta
  const rutas = consultasCalles.map((qc, i) => {
    const recta = consultasRecta[i]?.data ?? null
    if (qc.data) return qc.data
    if (qc.isError) return recta
    return null
  })
  const listas = rutas.every(Boolean)
  const error = consultasRecta.find((q) => q.isError)?.error
  const sinCalles = consultasCalles
    .map((q, i) => (q.isError ? { numero: ejecuciones[i].numero, mensaje: q.error?.message } : null))
    .filter(Boolean)
  const trazando = consultasCalles.some((q) => q.isPending)

  const [vista, setVista] = useState('todos')
  const visible = (ej) => vista === 'todos' || vista === ej.id_ejecucion

  const info = useMemo(() => {
    const m = new Map()
    hotspots.data?.features.forEach((f) => m.set(f.properties.id_hotspot, f.properties))
    return m
  }, [hotspots.data])

  const registradas = useRef(new Set())
  const rutasEstables = useMemo(() => (listas ? rutas : []), [listas, ...rutas]) // eslint-disable-line react-hooks/exhaustive-deps
  const sim = useSimulacion(rutasEstables, {
    alTerminarAgente: (i, distancia, duracion) => {
      const ej = ejecuciones[i]
      if (!ej || registradas.current.has(ej.id_ejecucion)) return
      registradas.current.add(ej.id_ejecucion)
      const recorrida = rutasEstables[i]?.properties?.distancia_m ?? distancia // por calles si lo hay
      api
        .registrarSimulacion({
          id_ejecucion: ej.id_ejecucion,
          distancia_total: Math.round(recorrida * 10) / 10,
          duracion_s: Math.round(duracion * 10) / 10,
        })
        .catch(() => registradas.current.delete(ej.id_ejecucion))
    },
  })

  const estados = useMemo(
    () =>
      sim.preparadas.map((p) => {
        if (!p) return null
        const pos = posicionEn(p, sim.recorrido)
        return { ...pos, fraccion: Math.min(1, sim.recorrido / (p.largo || 1)) }
      }),
    [sim.preparadas, sim.recorrido],
  )

  // Encuadre: todas las rutas, o solo la del agente elegido
  const encuadre = useMemo(() => {
    if (!listas) return undefined
    const pts = rutasEstables
      .filter((_, i) => vista === 'todos' || ejecuciones[i].id_ejecucion === vista)
      .flatMap((r) => r.geometry.coordinates)
    if (!pts.length) return undefined
    const lats = pts.map((p) => p[1])
    const lons = pts.map((p) => p[0])
    return [
      [Math.min(...lats), Math.min(...lons)],
      [Math.max(...lats), Math.max(...lons)],
    ]
  }, [listas, rutasEstables, vista, ejecuciones])

  const total = rutasEstables.reduce((a, r) => a + (r?.properties.distancia_m ?? 0), 0)
  const totalRecta = rutasEstables.reduce(
    (a, r) => a + (r?.properties.distancia_recta_m ?? r?.properties.distancia_m ?? 0),
    0,
  )
  const todasPorCalles = listas && rutasEstables.every(esPorCalles)
  const tiempoTotal = sim.largoMax / ((VELOCIDAD_KMH * 1000) / 3600)

  const resumen = (
    <div className={s.resumen}>
      <div className={s.resumenCabeza}>
        <h2 className={s.titulo}>Recorrido de {plural(ejecuciones.length, 'agente', 'agentes')}</h2>
      </div>
      {ejecuciones.length > 1 && (
        <Segmentado
          etiqueta="Agentes en el mapa"
          tamano="s"
          valor={vista}
          alCambiar={setVista}
          opciones={[
            { valor: 'todos', etiqueta: 'Todos' },
            ...ejecuciones.map((e) => ({ valor: e.id_ejecucion, etiqueta: `Agente ${e.numero}` })),
          ]}
        />
      )}
      <div className={s.controles}>
        <Boton
          variante="primario"
          icono={sim.corriendo ? Pause : Play}
          onClick={sim.alternar}
          disabled={!listas}
          className={s.botonPlay}
        >
          {sim.corriendo
            ? 'Pausar'
            : sim.terminado
              ? 'Repetir recorrido'
              : sim.recorrido > 0
                ? 'Continuar'
                : 'Iniciar recorrido'}
        </Boton>
        <Boton
          soloIcono
          icono={RotateCcw}
          onClick={sim.reiniciar}
          disabled={!listas || sim.recorrido === 0}
          title="Volver al punto de salida"
        >
          Reiniciar
        </Boton>
        <Segmentado
          etiqueta="Velocidad de la simulación"
          tamano="s"
          valor={sim.velocidad}
          alCambiar={sim.setVelocidad}
          opciones={[
            { valor: 1, etiqueta: '1×' },
            { valor: 2, etiqueta: '2×' },
            { valor: 4, etiqueta: '4×' },
          ]}
        />
      </div>
      <div className={s.reloj}>
        <div>
          <p className={s.relojEtiqueta}>Tiempo simulado</p>
          <p className={s.relojValor}>
            <span className="num">{fmtReloj(sim.tiempoSimulado)}</span>
            <span className={s.relojTotal}> / {fmtReloj(tiempoTotal)}</span>
          </p>
        </div>
        <p className={s.relojNota}>
          A {VELOCIDAD_KMH} km/h {todasPorCalles ? 'por calles' : 'en línea recta entre hotspots'}
        </p>
      </div>
      <input
        type="range"
        min={0}
        max={1000}
        value={Math.round(sim.progreso * 1000)}
        onChange={(e) => {
          sim.pausar()
          sim.irA(Number(e.target.value) / 1000)
        }}
        className={s.deslizador}
        style={{ '--avance': `${sim.progreso * 100}%` }}
        aria-label="Avance de la simulación"
        aria-valuetext={`${Math.round(sim.progreso * 100)}% del recorrido`}
        disabled={!listas}
      />
    </div>
  )

  const pie = (
    <>
      <Boton icono={ArrowLeft} a="/rutas">
        Rutas
      </Boton>
      <Boton
        variante="primario"
        icono={House}
        a="/"
        className={s.botonInicio}
        title="Cargar otro dataset o cambiar el número de grafos"
      >
        Inicio
      </Boton>
    </>
  )

  return (
    <div className={s.simular}>
      <h1 className="solo-lectores">Simular: agentes recorriendo sus rutas</h1>
      <div className={s.areaMapa}>
        <MapaGAM
          limite={limite.data}
          encuadre={encuadre}
          ajustarAlCambiar={vista}
          rellenoInferior={esMovil ? 280 : 0}
          relleno={esMovil ? [20, 20] : [48, 48]}
        >
          {listas &&
            rutasEstables.map((r, i) => {
              const ej = ejecuciones[i]
              if (!visible(ej)) return null
              return (
                <CapaAgente
                  key={`${ej.id_ejecucion}-${esPorCalles(r) ? 'calles' : 'recta'}`}
                  ruta={r}
                  preparada={sim.preparadas[i]}
                  numero={ej.numero}
                  color={colorGrafo(ej.numero, r.properties.color ?? ej.color)}
                  info={info}
                  sim={sim}
                  visitados={estados[i]?.visitados ?? 0}
                />
              )
            })}
        </MapaGAM>
        {!listas && !error && (
          <div className={s.cargandoMapa} role="status">
            <LoaderCircle size={14} className={s.giro} aria-hidden="true" />
            {trazando ? 'Trazando las rutas por calles…' : 'Cargando rutas…'}
          </div>
        )}
        {error && (
          <div className={s.errorFlotante}>
            <Aviso tipo="error" titulo="No se pudieron cargar las rutas">
              {error.message}
            </Aviso>
          </div>
        )}
      </div>

      <PanelAdaptable etiqueta="Panel de la simulación" resumen={resumen} pie={pie} alturaRecogida={344}>
        {sinCalles.length > 0 && listas && (
          <div className={s.final}>
            <Aviso
              tipo="info"
              titulo={
                sinCalles.length === ejecuciones.length
                  ? 'Rutas en línea recta'
                  : `${plural(sinCalles.length, 'agente', 'agentes')} en línea recta`
              }
            >
              No se pudo obtener el trazo por calles
              {sinCalles.length < ejecuciones.length
                ? ` del agente ${sinCalles.map((x) => x.numero).join(', ')}`
                : ''}
              . {sinCalles[0].mensaje}
            </Aviso>
          </div>
        )}
        {sim.terminado && (
          <div className={s.final}>
            <Aviso tipo="ok" titulo="Recorrido completo">
              {plural(ejecuciones.length, 'agente recorrió', 'agentes recorrieron')} {fmtDistancia(total)}{' '}
              {todasPorCalles
                ? `por calles en total (${fmtDistancia(totalRecta)} en línea recta, ${fmtPct((total / totalRecta - 1) * 100)}).`
                : 'en total.'}{' '}
              El más largo tardaría {fmtReloj(tiempoTotal)} a {VELOCIDAD_KMH} km/h.
            </Aviso>
          </div>
        )}
        <ul className={s.agentes}>
          {ejecuciones.map((ej, i) =>
            visible(ej) ? (
              <TarjetaAgente key={ej.id_ejecucion} ej={ej} ruta={rutasEstables[i]} estado={estados[i]} info={info} />
            ) : null,
          )}
        </ul>
        <p className={s.nota}>
          Cada agente recorre la ruta más corta que encontró su algoritmo genético. El orden de visita se calculó con
          distancias en línea recta; el dibujo sigue las calles reales (perfil en automóvil), por eso la distancia por
          calles es mayor.{' '}
          {rutasEstables.find(esPorCalles)?.properties.atribucion ?? ''}
        </p>
      </PanelAdaptable>
    </div>
  )
}

function TarjetaAgente({ ej, ruta, estado, info }) {
  const color = colorGrafo(ej.numero, ruta?.properties.color ?? ej.color)
  if (!ruta) {
    return (
      <li className={s.agente}>
        <span className={s.agenteNumero} style={{ background: color, color: textoSobre(color) }}>
          {ej.numero}
        </span>
        <span className={s.agenteCargando}>Trazando la ruta…</span>
      </li>
    )
  }
  const p = ruta.properties
  const calles = esPorCalles(ruta)
  const orden = p.hotspots ?? []
  const n = orden.length
  const visitados = estado?.visitados ?? 0
  const fin = estado?.fin
  const actual = Math.min(n - 1, Math.max(0, visitados - 1))
  const siguiente = visitados < n ? orden[visitados] : p.ruta_cerrada ? orden[0] : null
  const dActual = info.get(orden[actual])
  const dSiguiente = siguiente != null ? info.get(siguiente) : null
  const fraccion = estado?.fraccion ?? 0

  return (
    <li className={s.agente} style={{ '--c': color, '--tc': textoSobre(color) }}>
      <div className={s.agenteCabeza}>
        <span className={s.agenteNumero} style={{ background: color, color: textoSobre(color) }}>
          {ej.numero}
        </span>
        <div className={s.agenteTextos}>
          <p className={s.agenteNombre}>Agente {ej.numero}</p>
          <p className={s.agenteMeta}>
            {plural(n, 'hotspot', 'hotspots')}
            {p.generacion_mejor != null && `, ruta de la generación ${fmtEntero(p.generacion_mejor)}`}
          </p>
        </div>
        <p className={s.agenteDistancia}>{fmtDistancia(p.distancia_m)}</p>
      </div>
      <dl className={s.distancias}>
        <div>
          <dt>Línea recta (genético)</dt>
          <dd className="num">{fmtDistancia(calles ? p.distancia_recta_m : p.distancia_m)}</dd>
        </div>
        <div>
          <dt>Por calles</dt>
          <dd className="num">
            {calles ? (
              <>
                {fmtDistancia(p.distancia_m)}
                {p.diferencia_pct != null && <span className={s.diferencia}>{fmtPct(p.diferencia_pct)}</span>}
              </>
            ) : (
              <span className={s.noDisponible}>no disponible</span>
            )}
          </dd>
        </div>
        {calles && p.duracion_s != null && (
          <div>
            <dt>En auto, sin tráfico</dt>
            <dd className="num">{fmtMinutos(p.duracion_s)}</dd>
          </div>
        )}
      </dl>
      <div className={s.agenteBarra} aria-hidden="true">
        <motion.span initial={false} animate={{ scaleX: fraccion }} transition={{ duration: 0.12, ease: 'linear' }} />
      </div>
      <p className={s.agenteEstado} aria-live="polite">
        {fin ? (
          <>
            <Flag size={14} aria-hidden="true" /> Llegó
            {p.ruta_cerrada ? ' de vuelta al punto de salida' : ' al último hotspot'}
          </>
        ) : fraccion === 0 ? (
          <>Listo para salir de {dActual?.codigo}</>
        ) : (
          <>
            Va de <strong>{dActual?.codigo}</strong> a <strong>{dSiguiente?.codigo ?? '—'}</strong>
          </>
        )}
      </p>
      <ol className={s.estaciones} aria-label={`Orden de visita del agente ${ej.numero}`}>
        {orden.map((h, i) => {
          const d = info.get(h)
          const pasada = i < visitados
          return (
            <li
              key={h}
              className={`${s.estacion} ${pasada ? s.pasada : ''} ${i === actual && !fin && fraccion > 0 ? s.enCurso : ''}`}
              title={d ? `${d.codigo}${d.colonia ? `, ${d.colonia}` : ''}` : undefined}
            >
              {d ? String(d.etiqueta).padStart(2, '0') : '?'}
            </li>
          )
        })}
      </ol>
    </li>
  )
}
