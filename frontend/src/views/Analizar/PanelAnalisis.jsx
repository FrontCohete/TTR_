import { useMemo, useState } from 'react'
import { Dna, House, Layers, ListOrdered, Network, RotateCcw, Split, Waypoints } from 'lucide-react'
import PanelAdaptable from '../../components/ui/PanelAdaptable.jsx'
import Seccion from '../../components/ui/Seccion.jsx'
import Segmentado from '../../components/ui/Segmentado.jsx'
import Interruptor from '../../components/ui/Interruptor.jsx'
import Boton from '../../components/ui/Boton.jsx'
import { MAX_GRAFOS, useSesion } from '../../store/sesion.js'
import { SENAL, colorGravedad, nombreGravedad, textoSobre } from '../../lib/colores.js'
import { fmtDelta, fmtEntero, fmtFechaHora, fmtPct, fmt2, plural } from '../../lib/formato.js'
import s from './Analizar.module.css'

export default function PanelAnalisis({
  analisis: a,
  hotspots,
  capas,
  alCambiarCapas,
  seleccionado,
  alElegirHotspot,
  particion,
  grafoDe,
  repartir,
  generar,
}) {
  const { nGrafos, ponerNGrafos } = useSesion()
  const diferencia = a && a.n_hotspots_previo != null ? a.n_hotspots - a.n_hotspots_previo : null
  const textoGenerar = nGrafos === 1 ? 'Generar agente' : `Generar ${nGrafos} agentes`

  const resumen = (
    <div className={s.resumen}>
      <div className={s.resumenCabeza}>
        <h2 className={s.resumenTitulo}>{a ? `Análisis ${a.id_analisis}` : 'Análisis'}</h2>
        {a && <span className={s.resumenFecha}>{fmtFechaHora(a.fecha)}</span>}
      </div>
      <dl className={s.cifras}>
        <div>
          <dt>Hotspots</dt>
          <dd>
            <span className="num">{a ? fmtEntero(a.n_hotspots) : '—'}</span>
            {diferencia != null && (
              <span className={s.delta} title={`El análisis anterior tenía ${a.n_hotspots_previo} hotspots`}>
                {fmtDelta(diferencia)}
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt>Puntos</dt>
          <dd className="num">{a ? fmtEntero(a.n_puntos) : '—'}</dd>
        </div>
        <div>
          <dt>Ruido</dt>
          <dd className="num">{a ? fmtPct(a.n_ruido / a.n_puntos) : '—'}</dd>
        </div>
      </dl>
    </div>
  )

  const pie = (
    <>
      <Boton icono={House} a="/" title="Volver a Inicio para cargar otro dataset">
        Inicio
      </Boton>
      <Boton
        variante="primario"
        icono={Waypoints}
        className={s.botonGenerar}
        cargando={generar.isPending}
        disabled={!a || !hotspots}
        onClick={() => generar.mutate()}
      >
        {generar.isPending ? 'Generando…' : textoGenerar}
      </Boton>
    </>
  )

  return (
    <PanelAdaptable etiqueta="Panel del análisis" resumen={resumen} pie={pie} alturaRecogida={176}>
      {a && (
        <p className={s.parametrosHdbscan}>
          HDBSCAN con <span className="dato">min_cluster_size {a.min_cluster_size}</span> y{' '}
          <span className="dato">min_samples {a.min_samples}</span>
        </p>
      )}

      <Seccion titulo="Repartir en grafos" icono={Network}>
        <p className={s.ayuda}>
          Louvain agrupa los hotspots cercanos en comunidades. Cada grafo será la ruta de un agente.
        </p>
        <div className={s.campo}>
          <span className={s.etiquetaCampo} id="etq-ngrafos">
            Número de grafos
          </span>
          <Segmentado
            etiqueta="Número de grafos"
            anchoCompleto
            valor={nGrafos}
            alCambiar={ponerNGrafos}
            opciones={Array.from({ length: MAX_GRAFOS }, (_, i) => ({ valor: i + 1, etiqueta: String(i + 1) }))}
          />
          <span className={s.pistaCampo}>Máximo {MAX_GRAFOS} grafos.</span>
        </div>
        <Boton
          icono={Split}
          anchoCompleto
          cargando={repartir.isPending}
          onClick={() => repartir.mutate(nGrafos)}
          disabled={!a}
        >
          {particion && particion.n_grafos === nGrafos
            ? 'Repartir de nuevo'
            : `Repartir en ${plural(nGrafos, 'grafo', 'grafos')}`}
        </Boton>
        {particion && (
          <div className={s.resultadoParticion} aria-live="polite">
            <div className={s.resultadoCabeza}>
              <span>
                {plural(particion.n_grafos, 'grafo', 'grafos')} (partición {particion.id_particion})
              </span>
              <span className={s.modularidad} title="Qué tan separadas quedan las comunidades (0 a 1)">
                Modularidad <span className="num">{fmt2(particion.modularidad)}</span>
              </span>
            </div>
            <ul className={s.listaGrafos}>
              {particion.grafos.map((g) => (
                <li key={g.id_grafo}>
                  <span className={s.numeroGrafo} style={{ background: g.color, color: textoSobre(g.color) }}>
                    {g.numero}
                  </span>
                  <span className={s.nombreGrafo}>Grafo {g.numero}</span>
                  <span className={s.nodosGrafo}>{plural(g.n_nodos, 'hotspot', 'hotspots')}</span>
                </li>
              ))}
            </ul>
            {particion.n_grafos !== nGrafos && (
              <p className={s.notaCambio}>
                Elegiste {plural(nGrafos, 'grafo', 'grafos')}: al generar se repartirá de nuevo.
              </p>
            )}
          </div>
        )}
      </Seccion>

      <ParametrosAG />

      <Seccion titulo="Capas del mapa" icono={Layers}>
        <Interruptor
          etiqueta="Puntos delictivos"
          descripcion={
            capas.modo === 'densidad'
              ? 'Mapa de calor ponderado por gravedad'
              : 'Un punto por víctima, color por gravedad'
          }
          activo={capas.puntos}
          alCambiar={(v) => alCambiarCapas({ puntos: v })}
        />
        {capas.puntos && (
          <div className={s.subcontrol}>
            <Segmentado
              etiqueta="Forma de mostrar los puntos"
              tamano="s"
              valor={capas.modo}
              alCambiar={(v) => alCambiarCapas({ modo: v })}
              opciones={[
                { valor: 'puntos', etiqueta: 'Puntos' },
                { valor: 'densidad', etiqueta: 'Densidad' },
              ]}
            />
          </div>
        )}
        <Interruptor
          etiqueta="Ruido"
          descripcion="Puntos que HDBSCAN no asignó a ningún hotspot"
          activo={capas.ruido}
          deshabilitado={!capas.puntos}
          alCambiar={(v) => alCambiarCapas({ ruido: v })}
        />
        <Interruptor etiqueta="Áreas de hotspot" activo={capas.areas} alCambiar={(v) => alCambiarCapas({ areas: v })} />
        <Interruptor
          etiqueta="Zonas de cada grafo"
          descripcion={particion ? 'Envolvente de los hotspots de cada grafo' : 'Disponible después de repartir'}
          activo={capas.zonas}
          deshabilitado={!particion}
          alCambiar={(v) => alCambiarCapas({ zonas: v })}
        />
        <Interruptor
          etiqueta="Colonias"
          descripcion="179 colonias oficiales de GAM"
          activo={capas.colonias}
          alCambiar={(v) => alCambiarCapas({ colonias: v })}
        />
      </Seccion>

      <ListaHotspots hotspots={hotspots} grafoDe={grafoDe} seleccionado={seleccionado} alElegir={alElegirHotspot} />
    </PanelAdaptable>
  )
}

function ListaHotspots({ hotspots, grafoDe, seleccionado, alElegir }) {
  const [orden, setOrden] = useState('puntos')
  const filas = useMemo(() => {
    const lista = (hotspots?.features ?? []).map((f) => f.properties)
    return lista.sort((x, y) =>
      orden === 'puntos'
        ? y.n_puntos - x.n_puntos
        : orden === 'gravedad'
          ? y.indice_gravedad - x.indice_gravedad
          : x.etiqueta - y.etiqueta,
    )
  }, [hotspots, orden])
  const maxPuntos = Math.max(1, ...filas.map((f) => f.n_puntos))

  return (
    <Seccion titulo="Hotspots" icono={ListOrdered} nota={hotspots ? `${filas.length}` : undefined}>
      <div className={s.ordenLista}>
        <span className={s.etiquetaCampo}>Ordenar por</span>
        <Segmentado
          etiqueta="Ordenar hotspots por"
          tamano="s"
          valor={orden}
          alCambiar={setOrden}
          opciones={[
            { valor: 'puntos', etiqueta: 'Puntos' },
            { valor: 'gravedad', etiqueta: 'Gravedad' },
            { valor: 'codigo', etiqueta: 'Código' },
          ]}
        />
      </div>
      <ul className={s.listaHotspots}>
        {filas.map((p) => {
          const g = grafoDe.get(p.id_hotspot)
          const color = g?.color ?? SENAL
          const activo = seleccionado === p.id_hotspot
          return (
            <li key={p.id_hotspot}>
              <button
                type="button"
                className={`${s.filaHotspot} ${activo ? s.filaActiva : ''}`}
                aria-pressed={activo}
                onClick={() => alElegir(activo ? null : p.id_hotspot)}
              >
                <span className={s.estacionLista} style={{ borderColor: color }}>
                  {String(p.etiqueta).padStart(2, '0')}
                </span>
                <span className={s.textoHotspot}>
                  <span className={s.codigoHotspot}>
                    {p.codigo}
                    {g && <span className="solo-lectores">, grafo {g.numero}</span>}
                  </span>
                  <span className={s.coloniaHotspot}>{p.colonia ?? p.delito_predominante}</span>
                </span>
                <span className={s.medidasHotspot}>
                  <span className={`${s.puntosHotspot} num`}>{fmtEntero(p.n_puntos)}</span>
                  <span className={s.barraHotspot} aria-hidden="true">
                    <span
                      style={{
                        width: `${(p.n_puntos / maxPuntos) * 100}%`,
                        background: colorGravedad(p.indice_gravedad),
                      }}
                    />
                  </span>
                  <span className="solo-lectores">gravedad {nombreGravedad(p.indice_gravedad)}</span>
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </Seccion>
  )
}

function CampoNumero({ etiqueta, valor, alCambiar, min, max, paso = 1, ayuda }) {
  return (
    <label className={s.campoNumero}>
      <span className={s.etiquetaCampo}>{etiqueta}</span>
      <input
        type="number"
        inputMode="decimal"
        className={s.entrada}
        value={valor}
        min={min}
        max={max}
        step={paso}
        onChange={(e) => {
          const v = e.target.value === '' ? '' : Number(e.target.value)
          alCambiar(v)
        }}
        onBlur={(e) => {
          let v = Number(e.target.value)
          if (Number.isNaN(v)) v = min
          alCambiar(Math.min(max, Math.max(min, v)))
        }}
      />
      {ayuda && <span className={s.pistaCampo}>{ayuda}</span>}
    </label>
  )
}

function ParametrosAG() {
  const { parametros: p, ponerParametros, restablecerParametros } = useSesion()
  return (
    <Seccion
      titulo="Algoritmo genético"
      icono={Dna}
      plegable
      abiertaInicial={false}
      nota={`${p.tam_poblacion} × ${p.n_generaciones}`}
    >
      <p className={s.ayuda}>Se aplican a todos los agentes. Los valores por defecto funcionan bien para empezar.</p>
      <div className={s.rejillaCampos}>
        <CampoNumero
          etiqueta="Población"
          valor={p.tam_poblacion}
          min={4}
          max={500}
          alCambiar={(v) => ponerParametros({ tam_poblacion: v })}
        />
        <CampoNumero
          etiqueta="Generaciones"
          valor={p.n_generaciones}
          min={1}
          max={2000}
          alCambiar={(v) => ponerParametros({ n_generaciones: v })}
        />
        <CampoNumero
          etiqueta="Tamaño del torneo"
          valor={p.tam_torneo}
          min={2}
          max={Math.max(2, Number(p.tam_poblacion) || 2)}
          alCambiar={(v) => ponerParametros({ tam_torneo: v })}
        />
        <CampoNumero
          etiqueta="Semilla"
          valor={p.semilla}
          min={0}
          max={999999}
          alCambiar={(v) => ponerParametros({ semilla: v })}
        />
        <CampoNumero
          etiqueta="Prob. de cruce"
          valor={p.prob_cruce}
          min={0}
          max={1}
          paso={0.05}
          alCambiar={(v) => ponerParametros({ prob_cruce: v })}
        />
        <CampoNumero
          etiqueta="Prob. de mutación"
          valor={p.prob_mutacion}
          min={0}
          max={1}
          paso={0.01}
          alCambiar={(v) => ponerParametros({ prob_mutacion: v })}
        />
      </div>
      <div className={s.campo}>
        <span className={s.etiquetaCampo}>Cruce por permutación</span>
        <Segmentado
          etiqueta="Operador de cruce"
          tamano="s"
          valor={p.op_cruce}
          alCambiar={(v) => ponerParametros({ op_cruce: v })}
          opciones={[
            { valor: 'OX', etiqueta: 'OX (orden)' },
            { valor: 'PMX', etiqueta: 'PMX (mapeo)' },
          ]}
        />
      </div>
      <div className={s.campo}>
        <span className={s.etiquetaCampo}>Mutación por permutación</span>
        <Segmentado
          etiqueta="Operador de mutación"
          tamano="s"
          valor={p.op_mutacion}
          alCambiar={(v) => ponerParametros({ op_mutacion: v })}
          opciones={[
            { valor: 'swap', etiqueta: 'Intercambio' },
            { valor: 'inversion', etiqueta: 'Inversión' },
          ]}
        />
      </div>
      <Interruptor
        etiqueta="Regresar al punto de partida"
        descripcion={
          p.ruta_cerrada
            ? 'Ruta cerrada: el agente vuelve al primer hotspot'
            : 'Ruta abierta: termina en el último hotspot'
        }
        activo={!!p.ruta_cerrada}
        alCambiar={(v) => ponerParametros({ ruta_cerrada: v })}
      />
      <Boton tamano="s" variante="fantasma" icono={RotateCcw} onClick={restablecerParametros}>
        Restablecer valores
      </Boton>
    </Seccion>
  )
}
