import { House } from 'lucide-react'
import Boton from '../components/ui/Boton.jsx'
import { useTitulo } from '../hooks/useTitulo.js'

export default function NoEncontrado() {
  useTitulo('Página no encontrada')
  return (
    <div style={{ display: 'grid', placeItems: 'center', height: '100%', padding: 24 }}>
      <div style={{ maxWidth: 420, textAlign: 'center', display: 'grid', gap: 12, justifyItems: 'center' }}>
        <h1 style={{ fontSize: 'var(--t-2xl)' }}>Esta estación no existe</h1>
        <p style={{ color: 'var(--texto-2)' }}>
          La dirección no corresponde a ninguna vista de TTR_. Vuelve a Inicio para continuar.
        </p>
        <Boton variante="primario" icono={House} a="/">
          Ir a Inicio
        </Boton>
      </div>
    </div>
  )
}
