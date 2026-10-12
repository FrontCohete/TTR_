// Punto único de acceso a la API.
// Si usarDatosSimulados (src/config.js) es true, cada llamada se resuelve con los datos de src/mocks;
// si es false, se llama al backend real. Las vistas no saben (ni necesitan saber) cuál se usa.
import * as real from './real.js'
import { CONFIG } from '../config.js'

const desdeEntorno = import.meta.env.VITE_USE_MOCKS
export const USAR_MOCKS =
  desdeEntorno != null && desdeEntorno !== '' ? desdeEntorno === 'true' : CONFIG.usarDatosSimulados

let mocks = null
const cargarMocks = () => (mocks ??= import('../mocks/servidor.js'))

const nombres = Object.keys(real)

/** @type {typeof real} */
export const api = Object.fromEntries(
  nombres.map((nombre) => [
    nombre,
    USAR_MOCKS ? async (...args) => (await cargarMocks())[nombre](...args) : real[nombre],
  ]),
)

export { ApiError } from './cliente.js'
