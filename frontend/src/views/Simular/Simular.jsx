import { useMemo, useRef } from 'react'
import { motion } from 'motion/react'
import { ArrowLeft, Flag, House, LoaderCircle, Pause, Play, RotateCcw, Route } from 'lucide-react'
import { api } from '../../api/index.js'
import { useAnalisisVigente, useHotspots, useLimite, useRutas } from '../../api/consultas.js'
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
  const consultas = useRutas(ejecuciones.map((e) => e.id_ejecucion))
  const rutas = consultas.map((q) => q.data ?? null)
  const listas = rutas.every(Boolean)
  const error = consultas.find((q) => q.isError)?.error

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
      api
        .registrarSimulacion({
          id_ejecucion: ej.id_ejecucion,
          distancia_total: Math.round(distancia * 10) / 10,
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
        return { ...pos, fraccion: Math.min(1, sim.recorrido / p.largo) }
      }),
    [sim.preparadas, sim.recorrido],
  )

  const encuadre = useMemo(() => {
    if (!listas) return undefined
    const pts = rutasEstables.flatMap((r) => r.geometry.coordinates)
    const lats = pts.map((p) => p[1])
    const lons = pts.map((p) => p[0])
    return [
      [Math.min(...lats), Math.min(...lons)],
      [Math.max(...lats), Math.max(...lons)],
    ]
  }, [listas, rutasEstables])

  const total = rutasEstables.reduce((a, r) => a + (r?.properties.distancia_m ?? 0), 0)
  const tiempoTotal = sim.largoMax / ((VELOCIDAD_KMH * 1000) / 3600)

  const resumen = (
    <div className={s.resumen}>
      <div className={s.resumenCabeza}>
        <h2 className={s.titulo}>Recorrido de {plural(ejecuciones.length, 'agente', 'agentes')}</h2>
      </div>
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
        <p className={s.relojNota}>A {VELOCIDAD_KMH} km/h en línea recta entre hotspots</p>
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
          rellenoInferior={esMovil ? 280 : 0}
          relleno={esMovil ? [20, 20] : [48, 48]}
        >
          {listas &&
            rutasEstables.map((r, i) => {
              const ej = ejecuciones[i]
              return (
                <CapaAgente
                  key={ej.id_ejecucion}
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
            <LoaderCircle size={14} className={s.giro} aria-hidden="true" /> Cargando rutas…
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

      <PanelAdaptable etiqueta="Panel de la simulación" resumen={resumen} pie={pie} alturaRecogida={304}>
        {sim.terminado && (
          <div className={s.final}>
            <Aviso tipo="ok" titulo="Recorrido completo">
              {plural(ejecuciones.length, 'agente recorrió', 'agentes recorrieron')} {fmtDistancia(total)} en total. El
              más largo tardaría {fmtReloj(tiempoTotal)} a {VELOCIDAD_KMH} km/h.
            </Aviso>
          </div>
        )}
        <ul className={s.agentes}>
          {ejecuciones.map((ej, i) => (
            <TarjetaAgente key={ej.id_ejecucion} ej={ej} ruta={rutasEstables[i]} estado={estados[i]} info={info} />
          ))}
        </ul>
        <p className={s.nota}>
          Cada agente recorre la ruta más corta que encontró su algoritmo genético. Por ahora los trayectos son en línea
          recta entre hotspots; el ruteo por calles podrá agregarse después sin cambiar esta vista.
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
        <span className={s.agenteCargando}>Cargando ruta…</span>
      </li>
    )
  }
  const orden = ruta.properties.hotspots ?? []
  const n = orden.length
  const visitados = estado?.visitados ?? 0
  const fin = estado?.fin
  const actual = Math.min(n - 1, Math.max(0, visitados - 1))
  const siguiente = visitados < n ? orden[visitados] : ruta.properties.ruta_cerrada ? orden[0] : null
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
            {ruta.properties.generacion_mejor != null &&
              `, ruta de la generación ${fmtEntero(ruta.properties.generacion_mejor)}`}
          </p>
        </div>
        <p className={s.agenteDistancia}>{fmtDistancia(ruta.properties.distancia_m)}</p>
      </div>
      <div className={s.agenteBarra} aria-hidden="true">
        <motion.span initial={false} animate={{ scaleX: fraccion }} transition={{ duration: 0.12, ease: 'linear' }} />
      </div>
      <p className={s.agenteEstado} aria-live="polite">
        {fin ? (
          <>
            <Flag size={14} aria-hidden="true" /> Llegó
            {ruta.properties.ruta_cerrada ? ' de vuelta al punto de salida' : ' al último hotspot'}
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
