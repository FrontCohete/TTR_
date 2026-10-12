import { useMemo } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtDistancia, fmtEntero } from '../../lib/formato.js'
import s from './Rutas.module.css'

/**
 * Curva de aptitud: mejor, promedio y peor distancia por generación.
 * Se dibuja hasta la generación que se está reproduciendo.
 */
export default function GraficaAptitud({ generaciones, hasta, color }) {
  const datos = useMemo(
    () =>
      (generaciones ?? []).map((g) => ({
        gen: g.numero,
        mejor: g.mejor_fitness / 1000,
        promedio: g.fitness_promedio / 1000,
        peor: g.peor_fitness / 1000,
      })),
    [generaciones],
  )
  const visibles = useMemo(() => datos.slice(0, hasta + 1), [datos, hasta])
  const dominioY = useMemo(() => {
    if (!datos.length) return [0, 1]
    const min = Math.min(...datos.map((d) => d.mejor))
    const max = Math.max(...datos.map((d) => d.peor))
    return [Math.floor(min * 0.95), Math.ceil(max * 1.02)]
  }, [datos])
  const total = datos.length ? datos[datos.length - 1].gen : 0

  return (
    <figure className={s.grafica}>
      <figcaption className={s.graficaTitulo}>Aptitud por generación</figcaption>
      <ul className={s.graficaLeyenda}>
        <li>
          <span style={{ background: color }} /> Mejor
        </li>
        <li>
          <span className={s.lineaPromedio} /> Promedio
        </li>
        <li>
          <span style={{ background: '#A9AAB6' }} /> Peor
        </li>
      </ul>
      <div className={s.graficaArea}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={visibles} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="rgba(44,46,62,0.08)" vertical={false} />
            <XAxis
              dataKey="gen"
              type="number"
              domain={[0, Math.max(1, total)]}
              tick={{ fontSize: 11, fill: '#5F6276' }}
              tickLine={false}
              axisLine={{ stroke: 'rgba(44,46,62,0.2)' }}
              allowDecimals={false}
            />
            <YAxis
              domain={dominioY}
              tick={{ fontSize: 11, fill: '#5F6276' }}
              tickLine={false}
              axisLine={false}
              width={56}
              unit=" km"
              allowDecimals={false}
            />
            <Tooltip
              isAnimationActive={false}
              contentStyle={{
                background: '#2C2E3E',
                border: 'none',
                borderRadius: 8,
                color: '#FFF9F2',
                fontSize: 12,
                boxShadow: '0 8px 24px rgba(0,0,0,.2)',
              }}
              labelStyle={{ color: 'rgba(255,249,242,.7)', marginBottom: 4 }}
              itemStyle={{ color: '#FFF9F2', padding: 0 }}
              labelFormatter={(g) => `Generación ${fmtEntero(g)}`}
              formatter={(v, nombre) => [fmtDistancia(v * 1000), nombre]}
            />
            <Line
              type="monotone"
              dataKey="peor"
              name="Peor"
              stroke="#A9AAB6"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="promedio"
              name="Promedio"
              stroke="#34374C"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="mejor"
              name="Mejor"
              stroke={color}
              strokeWidth={2.25}
              dot={false}
              isAnimationActive={false}
            />
            <ReferenceLine x={hasta} stroke="#EE2B47" strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}
