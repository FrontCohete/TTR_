import { useMemo } from 'react'
import { Check, X } from 'lucide-react'
import Aviso from '../../components/ui/Aviso.jsx'
import { fmtEntero } from '../../lib/formato.js'
import s from './Inicio.module.css'

/** Columnas mínimas que exige la ingesta (deben coincidir con el backend) */
export const COLUMNAS_OBLIGATORIAS = ['fecha_hecho', 'hora_hecho', 'delito', 'alcaldia_hecho', 'latitud', 'longitud']

const esGam = (fila) =>
  /gustavo a\.? madero/i.test(String(fila.alcaldia_hecho ?? '')) ||
  /gustavo a\.? madero/i.test(String(fila.alcaldia_catalogo ?? ''))

const formatoCelda = (v) => {
  if (v == null || v === '') return <span className={s.celdaVacia}>vacío</span>
  if (typeof v === 'number') return Number.isInteger(v) ? v : v.toFixed(6).replace(/0+$/, '')
  if (typeof v === 'boolean') return v ? 'sí' : 'no'
  return String(v)
}

/** Validación de columnas + tabla con las primeras filas del archivo */
export default function VistaPrevia({ previa }) {
  const columnas = useMemo(() => {
    if (previa.columnas?.todas?.length) return previa.columnas.todas
    return Object.keys(previa.vista_previa?.[0] ?? {})
  }, [previa])
  const faltantes = previa.columnas?.faltantes ?? []
  const encontradas = new Set((previa.columnas?.encontradas ?? []).map((c) => c.toLowerCase()))
  const filas = previa.vista_previa ?? []
  const obligatorias = new Set(COLUMNAS_OBLIGATORIAS)

  // Los .xls (Excel 97-2003) se leen en el servidor; si no hay filas, se avisa en lugar de la tabla
  if (previa.vista_previa_disponible === false || (!filas.length && previa.formato === 'xls')) {
    return (
      <section className={s.previa} aria-labelledby="titulo-previa">
        <h2 id="titulo-previa" className={s.h2}>
          Vista previa
        </h2>
        <Aviso tipo="info" titulo="La vista previa de este .xls la genera el servidor">
          Con datos simulados no se abre el formato de Excel 97-2003. Con el backend conectado verás aquí las primeras
          filas y la validación de columnas. Puedes continuar con Analizar.
        </Aviso>
      </section>
    )
  }

  return (
    <section className={s.previa} aria-labelledby="titulo-previa">
      <header className={s.previaCabeza}>
        <div>
          <h2 id="titulo-previa" className={s.h2}>
            Vista previa
          </h2>
          <p className={s.subtexto}>
            Primeras {fmtEntero(filas.length)} de {fmtEntero(previa.filas_leidas)} filas
          </p>
        </div>
        <dl className={s.resumenCarga}>
          <div>
            <dt>Filas de Gustavo A. Madero</dt>
            <dd className="num">{fmtEntero(previa.resumen?.filas_gam)}</dd>
          </div>
          <div>
            <dt>Sin coordenadas</dt>
            <dd className="num">{fmtEntero(previa.resumen?.sin_coordenadas)}</dd>
          </div>
        </dl>
      </header>

      <div className={s.validacion}>
        <p className={s.validacionTitulo}>Columnas obligatorias</p>
        <ul className={s.chips}>
          {COLUMNAS_OBLIGATORIAS.map((c) => {
            const ok = encontradas.has(c) && !faltantes.includes(c)
            return (
              <li key={c} className={`${s.chip} ${ok ? s.chipOk : s.chipFalta}`}>
                {ok ? <Check size={14} aria-hidden="true" /> : <X size={14} aria-hidden="true" />}
                <span className="dato">{c}</span>
                <span className="solo-lectores">{ok ? 'encontrada' : 'falta'}</span>
              </li>
            )
          })}
        </ul>
      </div>

      {faltantes.length > 0 && (
        <Aviso
          tipo="error"
          titulo={`Faltan ${faltantes.length === 1 ? 'una columna obligatoria' : `${faltantes.length} columnas obligatorias`}`}
        >
          Agrega{' '}
          {faltantes.map((f, i) => (
            <span key={f}>
              {i > 0 && (i === faltantes.length - 1 ? ' y ' : ', ')}
              <code className="dato">{f}</code>
            </span>
          ))}{' '}
          al archivo y vuelve a cargarlo. Sin ellas no es posible ubicar los delitos en el mapa.
        </Aviso>
      )}

      <div
        className={s.tablaEnvoltura}
        tabIndex={0}
        role="region"
        aria-label="Tabla con las primeras filas del archivo"
      >
        <table className={s.tabla}>
          <thead>
            <tr>
              <th scope="col" className={s.colFila}>
                Fila
              </th>
              {columnas.map((c) => (
                <th key={c} scope="col" className={obligatorias.has(c) ? s.thObligatoria : undefined}>
                  <span className="dato">{c}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((f, i) => {
              const gam = esGam(f)
              return (
                <tr key={i} className={gam ? s.filaGam : undefined}>
                  <td className={s.colFila}>
                    <span className="dato">{i + 2}</span>
                    {gam && <span className={s.pildoraGam}>GAM</span>}
                  </td>
                  {columnas.map((c) => (
                    <td key={c} className={typeof f[c] === 'number' ? s.celdaNum : undefined}>
                      {formatoCelda(f[c])}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className={s.notaTabla}>
        La columna “Fila” es el número de fila en el archivo original. Las filas marcadas con GAM pertenecen a Gustavo
        A. Madero; el resto se descarta al procesar.
      </p>
    </section>
  )
}
