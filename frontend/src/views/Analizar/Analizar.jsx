import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { useMutation } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { FileSpreadsheet, LoaderCircle, MapPinned } from 'lucide-react'
import { api } from '../../api/index.js'
import { useAnalisisVigente, useColonias, useHotspots, useLimite, usePuntos } from '../../api/consultas.js'
import { useSesion } from '../../store/sesion.js'
import { useTitulo } from '../../hooks/useTitulo.js'
import { useEsMovil } from '../../hooks/useMedia.js'
import { fmtEntero } from '../../lib/formato.js'
import MapaGAM from '../../components/mapa/MapaGAM.jsx'
import CapaPuntos from '../../components/mapa/CapaPuntos.jsx'
import CapaHotspots from '../../components/mapa/CapaHotspots.jsx'
import { CapaColonias, CapaZonasGrafo } from '../../components/mapa/CapasExtra.jsx'
import Leyenda from '../../components/mapa/Leyenda.jsx'
import Boton from '../../components/ui/Boton.jsx'
import Aviso from '../../components/ui/Aviso.jsx'
import PanelAnalisis from './PanelAnalisis.jsx'
import s from './Analizar.module.css'

const CAPAS_INICIALES = { puntos: true, modo: 'puntos', ruido: true, areas: true, colonias: false, zonas: true }

export default function Analizar() {
  useTitulo('Analizar')
  const navegar = useNavigate()
  const esMovil = useEsMovil()
  const analisis = useAnalisisVigente()
  const a = analisis.data
  const limite = useLimite()
  const hotspots = useHotspots(a?.id_analisis)
  const [capas, setCapas] = useState(CAPAS_INICIALES)
  const puntos = usePuntos(a?.id_analisis, capas.puntos)
  const colonias = useColonias(capas.colonias)
  const [seleccionado, setSeleccionado] = useState(null)
  const [mapa, setMapa] = useState(null)
  const [leyendaAbierta, setLeyendaAbierta] = useState(false)

  const { particion, ponerParticion, nGrafos, parametros, ponerEjecuciones } = useSesion()
  const particionVigente = particion && a && particion.id_analisis === a.id_analisis ? particion : null

  const grafoDe = useMemo(() => {
    const m = new Map()
    particionVigente?.grafos.forEach((g) => g.hotspots.forEach((h) => m.set(h, { numero: g.numero, color: g.color })))
    return m
  }, [particionVigente])

  const repartir = useMutation({
    mutationFn: (n) => api.crearParticion(n),
    onSuccess: (p) => ponerParticion({ ...p, id_analisis: a.id_analisis }),
  })

  const generar = useMutation({
    mutationFn: async () => {
      let p = particionVigente
      if (!p || p.n_grafos !== nGrafos) {
        p = { ...(await api.crearParticion(nGrafos)), id_analisis: a.id_analisis }
        ponerParticion(p)
      }
      const r = await api.crearAgentes(p.id_particion, parametros)
      const porGrafo = new Map(p.grafos.map((g) => [g.id_grafo, g]))
      const ejecuciones = r.ejecuciones.map((e) => {
        const g = porGrafo.get(e.id_grafo)
        return {
          id_ejecucion: e.id_ejecucion,
          id_grafo: e.id_grafo,
          numero: e.numero,
          color: g?.color,
          n_nodos: g?.n_nodos,
          hotspots: g?.hotspots,
        }
      })
      ponerEjecuciones(ejecuciones, p.id_particion)
      return ejecuciones
    },
    onSuccess: () => navegar('/rutas'),
  })

  const elegirHotspot = (id) => {
    setSeleccionado(id)
    if (id != null && mapa && hotspots.data) {
      const f = hotspots.data.features.find((x) => x.properties.id_hotspot === id)
      if (f) {
        const [lon, lat] = f.properties.centroide
        mapa.flyTo([lat, lon], Math.max(mapa.getZoom(), 14.5), { duration: 0.6 })
      }
    }
  }

  if (analisis.isError) {
    const sinAnalisis = analisis.error?.estado === 404
    return (
      <div className={s.vacio}>
        <div className={s.vacioCaja}>
          <span className={s.vacioIcono} aria-hidden="true">
            <MapPinned size={26} />
          </span>
          <h1 className={s.vacioTitulo}>{sinAnalisis ? 'Todavía no hay hotspots' : 'No se pudo abrir el análisis'}</h1>
          <p className={s.vacioTexto}>
            {sinAnalisis
              ? 'El mapa se llena cuando procesas el primer dataset. Carga un archivo de víctimas (.csv, .xlsx o .xls) en Inicio y pulsa Analizar.'
              : analisis.error?.message}
          </p>
          <Boton variante="primario" icono={FileSpreadsheet} a="/">
            Cargar un dataset
          </Boton>
        </div>
      </div>
    )
  }

  const cargandoPuntos = capas.puntos && puntos.isFetching && !puntos.data
  const grafosLeyenda = particionVigente?.grafos.map((g) => ({ numero: g.numero, color: g.color, n_nodos: g.n_nodos }))

  return (
    <div className={s.analizar}>
      <h1 className="solo-lectores">Analizar: hotspots de Gustavo A. Madero</h1>
      <div className={s.areaMapa}>
        <MapaGAM
          limite={limite.data}
          alListo={setMapa}
          rellenoInferior={esMovil ? 150 : 0}
          relleno={esMovil ? [16, 16] : [32, 32]}
        >
          {capas.puntos && puntos.data && (
            <CapaPuntos datos={puntos.data.datos} modo={capas.modo} mostrarRuido={capas.ruido} />
          )}
          {capas.colonias && <CapaColonias colonias={colonias.data} />}
          {capas.zonas && particionVigente && <CapaZonasGrafo hotspots={hotspots.data} particion={particionVigente} />}
          {hotspots.data && (
            <CapaHotspots
              hotspots={hotspots.data}
              grafoDe={grafoDe}
              seleccionado={seleccionado}
              alSeleccionar={setSeleccionado}
              mostrarAreas={capas.areas}
            />
          )}
        </MapaGAM>

        <AnimatePresence>
          {(cargandoPuntos || hotspots.isLoading || analisis.isLoading) && (
            <motion.div
              className={s.cargandoMapa}
              role="status"
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              <LoaderCircle size={14} className={s.giro} aria-hidden="true" />
              {analisis.isLoading || hotspots.isLoading
                ? 'Cargando análisis…'
                : `Dibujando ${fmtEntero(a?.n_puntos)} puntos…`}
            </motion.div>
          )}
        </AnimatePresence>

        <div className={s.leyendaLugar}>
          {esMovil && (
            <button
              type="button"
              className={s.botonLeyenda}
              aria-expanded={leyendaAbierta}
              onClick={() => setLeyendaAbierta((v) => !v)}
            >
              Leyenda
            </button>
          )}
          {(!esMovil || leyendaAbierta) && (
            <Leyenda
              modoPuntos={capas.modo}
              mostrarPuntos={capas.puntos}
              mostrarRuido={capas.ruido}
              grafos={grafosLeyenda}
            />
          )}
        </div>

        {(repartir.isError || generar.isError) && (
          <div className={s.errorFlotante}>
            <Aviso tipo="error" titulo="No se pudo completar la acción">
              {(repartir.error || generar.error)?.message}
            </Aviso>
          </div>
        )}
      </div>

      <PanelAnalisis
        analisis={a}
        hotspots={hotspots.data}
        capas={capas}
        alCambiarCapas={(c) => setCapas((v) => ({ ...v, ...c }))}
        seleccionado={seleccionado}
        alElegirHotspot={elegirHotspot}
        particion={particionVigente}
        grafoDe={grafoDe}
        repartir={repartir}
        generar={generar}
      />
    </div>
  )
}
