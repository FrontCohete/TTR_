import { ArrowRight, CircleAlert, CircleCheck, LoaderCircle } from 'lucide-react'
import SiluetaGAM from '../../components/mapa/SiluetaGAM.jsx'
import Boton from '../../components/ui/Boton.jsx'
import { useCargas, useColonias, useHotspots, useLimite } from '../../api/consultas.js'
import { fmtEntero, fmtFecha, fmtDelta } from '../../lib/formato.js'
import s from './Inicio.module.css'

const ICONO_ESTADO = {
  completado: { Icono: CircleCheck, texto: 'Procesado' },
  error: { Icono: CircleAlert, texto: 'Con error' },
  procesando: { Icono: LoaderCircle, texto: 'Procesando' },
}

/** Placa oscura con lo que ya hay en la base: silueta con hotspots, cifras e historial */
export default function BaseAcumulada({ analisis, bloqueada }) {
  const limite = useLimite()
  const colonias = useColonias()
  const hotspots = useHotspots(analisis?.id_analisis)
  const cargas = useCargas()
  const lista = cargas.data ?? []
  const diferencia =
    analisis && analisis.n_hotspots_previo != null ? analisis.n_hotspots - analisis.n_hotspots_previo : null

  return (
    <aside className={s.base} aria-labelledby="titulo-base">
      <div className={s.baseCabeza}>
        <h2 id="titulo-base" className={s.baseTitulo}>
          Base acumulada
        </h2>
        {analisis && <span className={s.baseAnalisis}>Análisis {analisis.id_analisis} vigente</span>}
      </div>

      <div className={s.baseMapa}>
        <SiluetaGAM
          limite={limite.data}
          colonias={colonias.data}
          hotspots={hotspots.data}
          alto={260}
          titulo={analisis ? `Gustavo A. Madero con ${analisis.n_hotspots} hotspots del análisis vigente` : undefined}
        />
      </div>

      {analisis ? (
        <dl className={s.baseCifras}>
          <div>
            <dt>Puntos delictivos</dt>
            <dd className="num">{fmtEntero(analisis.n_puntos)}</dd>
          </div>
          <div>
            <dt>Hotspots</dt>
            <dd className="num">
              {fmtEntero(analisis.n_hotspots)}
              {diferencia != null && <span className={s.baseDelta}>{fmtDelta(diferencia)}</span>}
            </dd>
          </div>
          <div>
            <dt>Cargas</dt>
            <dd className="num">{fmtEntero(lista.filter((c) => c.estado === 'completado').length)}</dd>
          </div>
        </dl>
      ) : (
        <p className={s.baseVacia}>
          La base aún no tiene puntos. El primer dataset que proceses crea el análisis inicial.
        </p>
      )}

      {lista.length > 0 && (
        <div className={s.historial}>
          <h3 className={s.historialTitulo}>Historial de cargas</h3>
          <ul>
            {lista.slice(0, 4).map((c) => {
              const e = ICONO_ESTADO[c.estado] ?? ICONO_ESTADO.completado
              return (
                <li key={c.id_carga} className={s.historialFila}>
                  <e.Icono
                    size={16}
                    aria-hidden="true"
                    className={`${s.historialIcono} ${s[`est_${c.estado}`] ?? ''}`}
                  />
                  <div className={s.historialTexto}>
                    <span className={s.historialLinea}>
                      <span className={s.historialNombre}>{c.nombre_archivo}</span>
                      <span className={s.historialFecha}>{fmtFecha(c.fecha_carga)}</span>
                    </span>
                    <span className={s.historialMeta}>
                      {c.estado === 'error'
                        ? c.mensaje_error || 'No se pudo procesar'
                        : `${fmtEntero(c.puntos_gam_nuevos)} puntos nuevos de GAM`}
                      <span className="solo-lectores"> ({e.texto})</span>
                    </span>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {analisis && !bloqueada && (
        <Boton variante="oscuro" iconoDerecha={ArrowRight} a="/analizar" anchoCompleto>
          Ver el análisis vigente
        </Boton>
      )}
    </aside>
  )
}
