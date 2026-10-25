import { useId, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { ChevronDown, DatabaseZap, Trash2 } from 'lucide-react'
import { api } from '../../api/index.js'
import { useMantenimiento } from '../../api/consultas.js'
import { useSesion } from '../../store/sesion.js'
import { fmtEntero } from '../../lib/formato.js'
import Boton from '../../components/ui/Boton.jsx'
import Aviso from '../../components/ui/Aviso.jsx'
import s from './Mantenimiento.module.css'

const CIFRAS = [
  ['cargas', 'Datasets'],
  ['puntos', 'Puntos delictivos'],
  ['hotspots', 'Hotspots vigentes'],
  ['particiones', 'Particiones'],
  ['agentes', 'Agentes'],
  ['simulaciones', 'Simulaciones'],
]

const RESPALDO = 'pg_dump -U ttr_app -d ttr_clusteragent -F c -f database\\respaldo_antes_de_reiniciar.dump'

/**
 * Inicio › Mantenimiento: «Empezar de cero» (etapa 5.6).
 * Borra datasets, puntos, análisis, hotspots, particiones, grafos, agentes y simulaciones;
 * conserva la alcaldía, las colonias y el catálogo de delitos. Hay que escribir BORRAR.
 */
export default function Mantenimiento() {
  const [abierta, setAbierta] = useState(false)
  const [texto, setTexto] = useState('')
  const [hecho, setHecho] = useState(null)
  const idCuerpo = useId()
  const idCampo = useId()
  const clienteConsultas = useQueryClient()
  const reiniciarTodo = useSesion((st) => st.reiniciarTodo)
  const estado = useMantenimiento(abierta)
  const m = estado.data

  const reiniciar = useMutation({
    mutationFn: () => api.reiniciarBase(texto.trim()),
    onSuccess: async (r) => {
      setHecho(r)
      setTexto('')
      reiniciarTodo()
      await clienteConsultas.resetQueries()
    },
  })

  const vacia = m && Object.values(m.datos).every((v) => v === 0)
  const palabra = m?.confirmacion ?? 'BORRAR'
  const puede = m?.permitido && !m?.ocupado && !vacia && texto.trim() === palabra

  return (
    <section className={s.mant} aria-labelledby={`${idCuerpo}-titulo`}>
      <button
        type="button"
        className={s.cabeza}
        aria-expanded={abierta}
        aria-controls={idCuerpo}
        onClick={() => setAbierta((v) => !v)}
      >
        <span className={s.icono} aria-hidden="true">
          <DatabaseZap size={18} />
        </span>
        <span className={s.textos}>
          <span id={`${idCuerpo}-titulo`} className={s.titulo}>
            Mantenimiento
          </span>
          <span className={s.sub}>Empezar de cero para cargar otros datasets</span>
        </span>
        <ChevronDown size={18} className={`${s.flecha} ${abierta ? s.flechaAbierta : ''}`} aria-hidden="true" />
      </button>

      <AnimatePresence initial={false}>
        {abierta && (
          <motion.div
            id={idCuerpo}
            className={s.cuerpo}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.2, 0, 0, 1] }}
          >
            <div className={s.interior}>
              {hecho && (
                <Aviso tipo="ok" titulo="La base quedó vacía">
                  {hecho.mensaje} Se borraron {fmtEntero(hecho.borrado?.cargas ?? 0)} datasets,{' '}
                  {fmtEntero(hecho.borrado?.puntos ?? 0)} puntos y {fmtEntero(hecho.borrado?.agentes ?? 0)} agentes
                  {hecho.borrado?.espacio ? ` (${hecho.borrado.espacio})` : ''}.
                  {hecho.archivos?.resultados_archivados_en
                    ? ` Los JSON de resultados se movieron a ${hecho.archivos.resultados_archivados_en}.`
                    : ''}
                </Aviso>
              )}

              {estado.isPending && <p className={s.nota}>Consultando la base…</p>}
              {estado.isError && (
                <Aviso tipo="error" titulo="No se pudo consultar la base">
                  {estado.error.message}
                </Aviso>
              )}

              {m && (
                <>
                  <p className={s.explica}>
                    Borra todo lo que salió de los datasets: puntos, análisis HDBSCAN, hotspots, grafos, agentes y
                    simulaciones. Se conservan la alcaldía, {fmtEntero(m.se_conservan?.colonias ?? 0)} colonias y{' '}
                    {fmtEntero(m.se_conservan?.delitos ?? 0)} delitos con su gravedad.
                  </p>

                  <dl className={s.cifras}>
                    {CIFRAS.map(([clave, nombre]) => (
                      <div key={clave}>
                        <dt>{nombre}</dt>
                        <dd className="num">{fmtEntero(m.datos[clave] ?? 0)}</dd>
                      </div>
                    ))}
                    <div>
                      <dt>Espacio en la base</dt>
                      <dd className="num">{m.espacio}</dd>
                    </div>
                  </dl>

                  {!m.permitido ? (
                    <Aviso tipo="info" titulo="El reinicio está desactivado">
                      Para activarlo agrega <code className="dato">PERMITIR_REINICIO=true</code> en{' '}
                      <code className="dato">backend\.env</code> y reinicia el backend.
                    </Aviso>
                  ) : m.ocupado ? (
                    <Aviso tipo="info" titulo="Ahora no se puede">
                      {m.ocupado}
                    </Aviso>
                  ) : vacia ? (
                    <p className={s.nota}>La base ya está vacía: puedes cargar tus datasets arriba.</p>
                  ) : (
                    <form
                      className={s.formulario}
                      onSubmit={(e) => {
                        e.preventDefault()
                        if (puede) reiniciar.mutate()
                      }}
                    >
                      <p className={s.nota}>
                        Esto no se puede deshacer. Si quieres conservar lo actual, antes haz un respaldo desde la carpeta
                        _TTR_Dev:
                      </p>
                      <code className={`dato ${s.codigo}`}>{RESPALDO}</code>
                      <label htmlFor={idCampo} className={s.etiqueta}>
                        Escribe <strong>{palabra}</strong> para confirmar
                      </label>
                      <div className={s.fila}>
                        <input
                          id={idCampo}
                          className={s.campo}
                          value={texto}
                          onChange={(e) => setTexto(e.target.value)}
                          autoComplete="off"
                          spellCheck={false}
                          placeholder={palabra}
                        />
                        <Boton
                          variante="primario"
                          icono={Trash2}
                          disabled={!puede}
                          cargando={reiniciar.isPending}
                          onClick={() => puede && reiniciar.mutate()}
                        >
                          Empezar de cero
                        </Boton>
                      </div>
                      {reiniciar.isError && (
                        <Aviso tipo="error" titulo="No se pudo reiniciar">
                          {reiniciar.error.message}
                        </Aviso>
                      )}
                    </form>
                  )}
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
