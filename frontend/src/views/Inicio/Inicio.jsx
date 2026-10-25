import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { ArrowRight, RotateCcw, ScanSearch } from 'lucide-react'
import { api, ApiError } from '../../api/index.js'
import { useAnalisisVigente, useCarga } from '../../api/consultas.js'
import { useSesion } from '../../store/sesion.js'
import { useTitulo } from '../../hooks/useTitulo.js'
import { fmtDelta, fmtEntero } from '../../lib/formato.js'
import Boton from '../../components/ui/Boton.jsx'
import Aviso from '../../components/ui/Aviso.jsx'
import ZonaCarga from './ZonaCarga.jsx'
import VistaPrevia from './VistaPrevia.jsx'
import ProgresoProceso from './ProgresoProceso.jsx'
import BaseAcumulada from './BaseAcumulada.jsx'
import Mantenimiento from './Mantenimiento.jsx'
import { COLUMNAS_OBLIGATORIAS } from './VistaPrevia.jsx'
import s from './Inicio.module.css'

const transicion = { duration: 0.26, ease: [0.2, 0, 0, 1] }

export default function Inicio() {
  useTitulo('Inicio')
  const navegar = useNavigate()
  const clienteConsultas = useQueryClient()
  const analisis = useAnalisisVigente()
  const {
    cargaPrevia,
    ponerCargaPrevia,
    quitarCargaPrevia,
    idCargaEnProceso,
    iniciarProceso,
    terminarProceso,
    olvidarResultados,
  } = useSesion()

  const [archivo, setArchivo] = useState(null)
  const [avanceLectura, setAvanceLectura] = useState(0)
  const [errorCarga, setErrorCarga] = useState(null)
  const [errorProceso, setErrorProceso] = useState(null)
  const nombreEnProceso = useRef(cargaPrevia?.nombre_archivo)

  // 1) Subir el archivo: el backend responde con la vista previa y la validación
  const subir = useMutation({
    mutationFn: (f) => api.subirCarga(f, { alProgreso: setAvanceLectura }),
    onMutate: () => {
      setErrorCarga(null)
      setAvanceLectura(0)
    },
    onSuccess: (respuesta) => ponerCargaPrevia(respuesta),
    onError: (e) => {
      const titulo =
        e instanceof ApiError && e.estado === 409
          ? 'Este archivo ya se había cargado'
          : e instanceof ApiError && e.estado === 422
            ? 'No se pudo usar el archivo'
            : 'No se pudo subir el archivo'
      setErrorCarga({ titulo, mensaje: e.message })
    },
  })

  // 2) Procesar: ingesta + HDBSCAN en segundo plano
  const procesar = useMutation({
    mutationFn: (id) => api.procesarCarga(id),
    onMutate: () => setErrorProceso(null),
    onSuccess: (_, id) => {
      nombreEnProceso.current = cargaPrevia?.nombre_archivo
      iniciarProceso(id)
    },
    onError: (e) => setErrorProceso(e.message),
  })

  // 3) Consultar el avance cada segundo hasta completar
  const carga = useCarga(idCargaEnProceso)
  const estadoCarga = carga.data?.estado

  useEffect(() => {
    if (!idCargaEnProceso || !estadoCarga) return
    if (estadoCarga === 'completado') {
      olvidarResultados()
      clienteConsultas.invalidateQueries({ queryKey: ['analisis'] })
      clienteConsultas.invalidateQueries({ queryKey: ['cargas'] })
      const t = setTimeout(() => {
        terminarProceso()
        navegar('/analizar')
      }, 1600)
      return () => clearTimeout(t)
    }
    if (estadoCarga === 'error') {
      setErrorProceso(carga.data.mensaje_error || 'El procesamiento falló.')
      clienteConsultas.invalidateQueries({ queryKey: ['cargas'] })
      terminarProceso()
    }
  }, [estadoCarga, idCargaEnProceso]) // eslint-disable-line react-hooks/exhaustive-deps

  const elegir = (f, motivo) => {
    setArchivo(f)
    setErrorProceso(null)
    if (motivo === 'tipo') {
      setErrorCarga({
        titulo: 'Formato no admitido',
        mensaje: `“${f.name}” no es un archivo admitido. Usa .csv, .xlsx o .xls.`,
      })
      return
    }
    quitarCargaPrevia()
    subir.mutate(f)
  }

  const quitar = () => {
    quitarCargaPrevia()
    setArchivo(null)
    setErrorCarga(null)
    setErrorProceso(null)
  }

  const procesando = idCargaEnProceso != null
  const faltantes = cargaPrevia?.columnas?.faltantes ?? []
  const listoParaAnalizar = cargaPrevia && faltantes.length === 0 && !procesando
  const completado = estadoCarga === 'completado'
  const a = analisis.data

  return (
    <div className={s.inicio}>
      <div className={s.rejilla}>
        <div className={s.principal}>
          <header className={s.encabezado}>
            <h1 className={s.h1}>Carga un dataset de víctimas</h1>
            <p className={s.intro}>
              Sube el archivo de víctimas de la FGJ de la CDMX (.csv, .xlsx o .xls). TTR_ conserva solo los puntos de
              Gustavo A. Madero, los suma a los que ya están en la base y vuelve a calcular los hotspots con HDBSCAN.
            </p>
          </header>

          <AnimatePresence mode="wait" initial={false}>
            {procesando || completado ? (
              <motion.div
                key="proceso"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={transicion}
              >
                <ProgresoProceso carga={carga.data} nombre={nombreEnProceso.current ?? carga.data?.nombre_archivo} />
                {completado && (
                  <Aviso
                    tipo="ok"
                    className={s.avisoListo}
                    titulo="Hotspots actualizados"
                    accion={
                      <Boton
                        tamano="s"
                        variante="primario"
                        iconoDerecha={ArrowRight}
                        onClick={() => {
                          terminarProceso()
                          navegar('/analizar')
                        }}
                      >
                        Ver análisis
                      </Boton>
                    }
                  >
                    {a && a.id_analisis === carga.data?.id_analisis
                      ? `${fmtEntero(a.n_hotspots)} hotspots en el análisis ${a.id_analisis}${a.n_hotspots_previo != null ? ` (${fmtDelta(a.n_hotspots - a.n_hotspots_previo)} respecto al anterior)` : ''}. Abriendo Analizar…`
                      : 'Abriendo Analizar…'}
                  </Aviso>
                )}
              </motion.div>
            ) : (
              <motion.div
                key="zona"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={transicion}
              >
                <ZonaCarga
                  alElegir={elegir}
                  leyendo={subir.isPending}
                  avance={avanceLectura}
                  archivo={archivo}
                  previa={cargaPrevia}
                  error={errorCarga}
                  alQuitar={quitar}
                  bloqueada={procesando}
                />
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence initial={false}>
            {cargaPrevia && !procesando && !completado && (
              <motion.div
                key="previa"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                transition={transicion}
              >
                <VistaPrevia previa={cargaPrevia} />
              </motion.div>
            )}
          </AnimatePresence>

          {!cargaPrevia && !procesando && !completado && (
            <div className={s.requisitos}>
              <p className={s.requisitosTitulo}>Columnas que debe tener el archivo</p>
              <ul className={s.chips}>
                {COLUMNAS_OBLIGATORIAS.map((c) => (
                  <li key={c} className={`${s.chip} ${s.chipNeutro}`}>
                    <span className="dato">{c}</span>
                  </li>
                ))}
              </ul>
              <p className={s.requisitosTexto}>
                Son las del conjunto “Víctimas en carpetas de investigación” de la FGJ, tal como se descargan del portal
                de datos abiertos.
              </p>
            </div>
          )}

          {errorProceso && (
            <Aviso
              tipo="error"
              titulo="El dataset no se pudo procesar"
              accion={
                <Boton tamano="s" icono={RotateCcw} onClick={quitar}>
                  Elegir otro archivo
                </Boton>
              }
            >
              {errorProceso}
            </Aviso>
          )}

          {!cargaPrevia && !procesando && !completado && <Mantenimiento />}
        </div>

        <BaseAcumulada analisis={a} bloqueada={procesando} />
      </div>

      <AnimatePresence initial={false}>
        {cargaPrevia && !procesando && !completado && (
          <motion.div
            key="acciones"
            className={s.barraAcciones}
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={transicion}
          >
            <p className={s.barraTexto}>
              {faltantes.length
                ? 'Corrige las columnas faltantes para poder analizar.'
                : cargaPrevia.resumen?.filas_gam == null
                  ? 'Los puntos de GAM de este archivo se sumarán a la base al analizar.'
                  : `Se sumarán hasta ${fmtEntero(cargaPrevia.resumen?.filas_gam)} puntos de GAM a la base${a ? ` (hoy: ${fmtEntero(a.n_puntos)}).` : '.'}`}
            </p>
            <div className={s.barraBotones}>
              <Boton variante="oscuro" onClick={quitar}>
                Quitar archivo
              </Boton>
              <Boton
                variante="primario"
                tamano="l"
                icono={ScanSearch}
                disabled={!listoParaAnalizar}
                cargando={procesar.isPending}
                onClick={() => procesar.mutate(cargaPrevia.id_carga)}
              >
                Analizar
              </Boton>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
