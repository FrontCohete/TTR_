import { Check, Scale } from 'lucide-react'
import { fmtDistancia } from '../../lib/formato.js'
import s from './ComparacionAG.module.css'

/** Las tres formas de medir de «la mejor de tres» (etapa 7) */
export const METRICAS = {
  recta: { letra: 'A', nombre: 'Línea recta', corto: 'línea recta' },
  calles: { letra: 'B', nombre: 'Calles con sentido', corto: 'calles con sentido' },
  calles_promedio: { letra: 'C', nombre: 'Calles, ida y vuelta promedio', corto: 'calles (promedio de ida y vuelta)' },
}

/** Cómo se suma la aptitud de una ruta con cada forma de medir (vista Rutas, función objetivo) */
export const TRAMOS_SEGUN_METRICA = {
  recta: 'la suma de los tramos en línea recta entre hotspots consecutivos',
  calles:
    'la suma de los tramos por calles entre hotspots consecutivos, respetando el sentido de las calles (ir de un hotspot a otro puede medir distinto que regresar)',
  calles_promedio:
    'la suma de los tramos por calles entre hotspots consecutivos, tomando de cada tramo el promedio de ida y vuelta',
}

/** +0.1 %, −5.3 % (una decimal siempre: las diferencias suelen ser chicas) */
const pct = (x) => {
  const v = Math.abs(x).toLocaleString('es-MX', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  return v === '0.0' ? '0.0 %' : `${x > 0 ? '+' : '−'}${v} %`
}

/**
 * «La mejor de tres»: el agente corrió el genético con A (línea recta), B (calles con sentido) y
 * C (calles, ida y vuelta promedio); las tres rutas se midieron por calles y ganó la más corta.
 * Agentes anteriores a la etapa 7 (sin comparación): solo dice con qué se optimizó.
 */
export default function ComparacionAG({ agente, compacto = false }) {
  if (!agente || agente.estado !== 'terminado') return null
  const metrica = METRICAS[agente.metrica] ?? METRICAS.recta
  const comp = agente.comparacion
  const variantes = comp?.variantes ?? []
  const conCalles = variantes.filter((v) => v.distancia_calles_m != null)

  if (!comp) {
    return (
      <div className={`${s.caja} ${compacto ? s.compacto : ''}`}>
        <p className={s.cabeza}>
          <Scale size={14} aria-hidden="true" /> Optimizado con <strong>{metrica.corto}</strong>
        </p>
        <p className={s.nota}>
          Este agente se calculó antes de comparar las formas de medir. Genera los agentes de nuevo para verla.
        </p>
      </div>
    )
  }

  if (conCalles.length < 2) {
    // Una sola forma de medir: la elegida en Analizar, o línea recta si no hubo distancias por calles
    const unica = variantes[0]
    const elegida = comp.medir && comp.medir !== 'mejor_de_tres'
    return (
      <div className={`${s.caja} ${compacto ? s.compacto : ''}`}>
        <p className={s.cabeza}>
          <Scale size={14} aria-hidden="true" /> Optimizado con <strong>{metrica.corto}</strong>
          {elegida && !comp.aviso && <span className={s.elegida}>elegida en Analizar</span>}
        </p>
        {unica && (
          <dl className={s.cifras}>
            <div>
              <dt>Por calles</dt>
              <dd className="num">
                {unica.distancia_calles_m != null ? fmtDistancia(unica.distancia_calles_m) : 'no disponible'}
              </dd>
            </div>
            <div>
              <dt>En línea recta</dt>
              <dd className="num">{fmtDistancia(unica.distancia_recta_m)}</dd>
            </div>
          </dl>
        )}
        {comp.aviso ? (
          <p className={s.nota}>{comp.aviso}</p>
        ) : (
          !compacto && (
            <p className={s.nota}>
              Solo se probó esta forma de medir, así que puede no ser la ruta más corta por calles. Con «Mejor de 3»
              se comparan las tres.
            </p>
          )
        )}
      </div>
    )
  }

  const a = variantes.find((v) => v.variante === 'A')
  return (
    <div className={`${s.caja} ${compacto ? s.compacto : ''}`}>
      <p className={s.cabeza}>
        <Scale size={14} aria-hidden="true" /> La mejor de tres · optimizado con <strong>{metrica.corto}</strong>
      </p>
      <table className={s.tabla}>
        <caption className="solo-lectores">
          Distancia por calles de la ruta que encontró el genético con cada forma de medir
        </caption>
        <thead>
          <tr>
            <th scope="col">Forma de medir</th>
            <th scope="col" className={s.numero}>
              Por calles
            </th>
            {!compacto && (
              <th scope="col" className={s.numero}>
                vs. A
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {variantes.map((v) => {
            const m = METRICAS[v.metrica]
            const dif = a && v.variante !== 'A' ? (v.distancia_calles_m / a.distancia_calles_m - 1) * 100 : null
            return (
              <tr key={v.variante} className={v.ganadora ? s.ganadora : ''}>
                <th scope="row">
                  <span className={s.letra} aria-hidden="true">
                    {v.variante}
                  </span>
                  <span className={s.nombre}>{m?.nombre ?? v.metrica}</span>
                  {v.ganadora && (
                    <span className={s.marca}>
                      <Check size={13} aria-hidden="true" />
                      <span className="solo-lectores"> (ganadora)</span>
                    </span>
                  )}
                </th>
                <td className={`${s.numero} num`}>{fmtDistancia(v.distancia_calles_m)}</td>
                {!compacto && (
                  <td className={`${s.numero} num ${s.dif}`}>{dif == null ? '—' : pct(dif)}</td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
      {!compacto && (
        <p className={s.nota}>
          Las tres rutas se miden igual: por calles, en su sentido más corto. La gráfica y las rutas de cada generación
          usan la forma de medir ganadora.
        </p>
      )}
    </div>
  )
}
