import { GRAVEDAD, textoSobre } from '../../lib/colores.js'
import s from './Leyenda.module.css'

/**
 * Placa oscura de leyenda sobre el mapa.
 * Gravedad (rampa), ruido, hotspot y, si existe partición, los grafos con su número.
 */
export default function Leyenda({
  modoPuntos = 'puntos',
  mostrarPuntos = true,
  mostrarRuido = true,
  grafos,
  className = '',
}) {
  return (
    <div className={`${s.leyenda} ${className}`} aria-label="Leyenda del mapa" role="group">
      {mostrarPuntos && (
        <div className={s.bloque}>
          <p className={s.titulo}>
            {modoPuntos === 'densidad' ? 'Densidad ponderada por gravedad' : 'Gravedad del delito'}
          </p>
          {modoPuntos === 'densidad' ? (
            <div className={s.rampa}>
              <span className={s.degradado} />
              <span className={s.extremos}>
                <span>Menor</span>
                <span>Mayor</span>
              </span>
            </div>
          ) : (
            <ul className={s.lista}>
              {GRAVEDAD.slice(1).map((g) => (
                <li key={g.peso}>
                  <span className={s.punto} style={{ background: g.color }} />
                  {g.nombre}
                </li>
              ))}
              {mostrarRuido && (
                <li>
                  <span className={s.punto} style={{ background: '#6B6E82', opacity: 0.6 }} />
                  Ruido
                </li>
              )}
            </ul>
          )}
        </div>
      )}
      <div className={s.bloque}>
        {grafos?.length ? (
          <>
            <p className={s.titulo}>Grafos</p>
            <ul className={s.lista}>
              {grafos.map((g) => (
                <li key={g.numero}>
                  <span className={s.numero} style={{ background: g.color, color: textoSobre(g.color) }}>
                    {g.numero}
                  </span>
                  {g.n_nodos} hotspots
                </li>
              ))}
            </ul>
          </>
        ) : (
          <ul className={s.lista}>
            <li>
              <span className={s.estacion} />
              Hotspot (HDBSCAN)
            </li>
          </ul>
        )}
      </div>
    </div>
  )
}
