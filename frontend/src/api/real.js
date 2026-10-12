// Endpoints reales del backend (contrato de la API, README §7).
// Cada función devuelve exactamente lo que responde FastAPI.
import { solicitar, subirArchivo } from './cliente.js'

// ---------- Vista Inicio ----------
export const subirCarga = (archivo, opciones) => subirArchivo('/cargas', archivo, opciones)
export const procesarCarga = (idCarga) => solicitar(`/cargas/${idCarga}/procesar`, { metodo: 'POST' })
export const obtenerCarga = (idCarga) => solicitar(`/cargas/${idCarga}`)
export const listarCargas = () => solicitar('/cargas')

// ---------- Vista Analizar ----------
export const obtenerLimite = () => solicitar('/mapa/limite')
export const obtenerColonias = () => solicitar('/mapa/colonias')
export const obtenerAnalisisVigente = () => solicitar('/analisis/vigente')
export const obtenerPuntos = () => solicitar('/analisis/vigente/puntos?formato=ligero')
export const obtenerHotspots = () => solicitar('/analisis/vigente/hotspots')
export const crearParticion = (nGrafos) => solicitar('/particiones', { metodo: 'POST', cuerpo: { n_grafos: nGrafos } })
export const obtenerHotspotsParticion = (idParticion) => solicitar(`/particiones/${idParticion}/hotspots`)

// ---------- Vista Rutas ----------
export const crearAgentes = (idParticion, parametros) =>
  solicitar('/agentes', { metodo: 'POST', cuerpo: { id_particion: idParticion, parametros } })
export const obtenerAgente = (idEjecucion) => solicitar(`/agentes/${idEjecucion}`)
export const obtenerGeneraciones = (idEjecucion) => solicitar(`/agentes/${idEjecucion}/generaciones`)
export const obtenerIndividuos = (idGeneracion) => solicitar(`/generaciones/${idGeneracion}/individuos`)

// ---------- Vista Simular ----------
export const obtenerRuta = (idEjecucion) => solicitar(`/agentes/${idEjecucion}/ruta`)
export const registrarSimulacion = (cuerpo) => solicitar('/simulaciones', { metodo: 'POST', cuerpo })
