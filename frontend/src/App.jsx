import { lazy, Suspense } from 'react'
import { createBrowserRouter, createHashRouter, createMemoryRouter, RouterProvider } from 'react-router'
import Marco from './components/layout/Marco.jsx'
import Inicio from './views/Inicio/Inicio.jsx'
import CargandoVista from './components/ui/CargandoVista.jsx'
import NoEncontrado from './views/NoEncontrado.jsx'

// Las vistas con mapa y gráficas se cargan bajo demanda para que Inicio abra rápido.
const Analizar = lazy(() => import('./views/Analizar/Analizar.jsx'))
const Rutas = lazy(() => import('./views/Rutas/Rutas.jsx'))
const Simular = lazy(() => import('./views/Simular/Simular.jsx'))

const conEspera = (Vista) => (
  <Suspense fallback={<CargandoVista />}>
    <Vista />
  </Suspense>
)

const rutas = [
  {
    path: '/',
    element: <Marco />,
    children: [
      { index: true, element: <Inicio /> },
      { path: 'analizar', element: conEspera(Analizar) },
      { path: 'rutas', element: conEspera(Rutas) },
      { path: 'simular', element: conEspera(Simular) },
      { path: '*', element: <NoEncontrado /> },
    ],
  },
]

// VITE_ROUTER: "browser" (por defecto), "hash" (archivos estáticos) o "memory" (vista previa incrustada)
const tipoRouter = import.meta.env.VITE_ROUTER
const base = import.meta.env.BASE_URL.replace(/\/$/, '') || undefined
const router =
  tipoRouter === 'hash'
    ? createHashRouter(rutas)
    : tipoRouter === 'memory'
      ? createMemoryRouter(rutas)
      : createBrowserRouter(rutas, { basename: base })

export default function App() {
  return <RouterProvider router={router} />
}
