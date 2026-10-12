import { useEffect, useRef } from 'react'
import L from 'leaflet'
import simpleheat from 'simpleheat'
import { useMap } from 'react-leaflet'
import { GRAVEDAD } from '../../lib/colores.js'

/**
 * Capa de puntos delictivos dibujada en un solo <canvas>.
 * Dibujar ~63 mil marcadores de Leaflet sería lentísimo; aquí se proyectan una vez
 * a coordenadas de píxel (zoom 0) y en cada movimiento solo se escalan.
 *
 * datos: filas [lon, lat, peso_gravedad, id_hotspot | null] (GET /analisis/vigente/puntos?formato=ligero)
 * modo: "puntos" (color por gravedad) o "densidad" (mapa de calor ponderado por gravedad)
 */
const CanvasPuntos = L.Layer.extend({
  initialize(opciones) {
    L.setOptions(this, opciones)
    this._proyectados = null
  },

  ponerDatos(datos) {
    this._datos = datos
    this._proyectados = null
    this._redibujar()
  },

  ponerOpciones(opciones) {
    L.setOptions(this, opciones)
    this._redibujar()
  },

  onAdd(map) {
    this._map = map
    const canvas = (this._canvas = L.DomUtil.create('canvas', 'ttr-capa-puntos'))
    canvas.style.pointerEvents = 'none'
    const animado = map.options.zoomAnimation && L.Browser.any3d
    L.DomUtil.addClass(canvas, `leaflet-zoom-${animado ? 'animated' : 'hide'}`)
    map.getPane(this.options.pane || 'overlayPane').appendChild(canvas)
    map.on('moveend resize', this._reiniciar, this)
    if (animado) map.on('zoomanim', this._animarZoom, this)
    this._reiniciar()
  },

  onRemove(map) {
    L.DomUtil.remove(this._canvas)
    map.off('moveend resize', this._reiniciar, this)
    map.off('zoomanim', this._animarZoom, this)
  },

  _animarZoom(e) {
    const escala = this._map.getZoomScale(e.zoom)
    const desplazamiento = this._map._latLngBoundsToNewLayerBounds(this._map.getBounds(), e.zoom, e.center).min
    L.DomUtil.setTransform(this._canvas, desplazamiento, escala)
  },

  _reiniciar() {
    const map = this._map
    if (!map) return
    const esquina = map.containerPointToLayerPoint([0, 0])
    L.DomUtil.setPosition(this._canvas, esquina)
    const tam = map.getSize()
    const dpr = window.devicePixelRatio || 1
    this._canvas.width = tam.x * dpr
    this._canvas.height = tam.y * dpr
    this._canvas.style.width = `${tam.x}px`
    this._canvas.style.height = `${tam.y}px`
    this._redibujar()
  },

  _proyectar() {
    const datos = this._datos
    const n = datos.length
    const xs = new Float64Array(n)
    const ys = new Float64Array(n)
    const crs = this._map.options.crs
    for (let i = 0; i < n; i++) {
      const p = crs.latLngToPoint(L.latLng(datos[i][1], datos[i][0]), 0)
      xs[i] = p.x
      ys[i] = p.y
    }
    this._proyectados = { xs, ys }
  },

  _redibujar() {
    const map = this._map
    if (!map || !this._canvas) return
    const ctx = this._canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, this._canvas.width, this._canvas.height)
    if (!this._datos?.length) return
    if (!this._proyectados) this._proyectar()

    const { xs, ys } = this._proyectados
    const datos = this._datos
    const zoom = map.getZoom()
    const escala = 2 ** zoom
    const origen = map.getPixelBounds().min
    const ancho = this._canvas.width / dpr
    const alto = this._canvas.height / dpr
    const { modo, mostrarRuido, mostrarAgrupados } = this.options

    if (modo === 'densidad') {
      // Mapa de calor ponderado por gravedad: se agregan los puntos por celdas para acelerar.
      const radio = Math.max(6, Math.min(26, 3 * (zoom - 9)))
      const celda = radio / 2
      const celdas = new Map()
      for (let i = 0; i < datos.length; i++) {
        const esRuido = datos[i][3] == null
        if ((esRuido && !mostrarRuido) || (!esRuido && !mostrarAgrupados)) continue
        const x = xs[i] * escala - origen.x
        const y = ys[i] * escala - origen.y
        if (x < -radio || y < -radio || x > ancho + radio || y > alto + radio) continue
        const k = `${Math.floor(x / celda)}|${Math.floor(y / celda)}`
        const peso = 0.4 + datos[i][2] * 0.4
        const c = celdas.get(k)
        if (c) {
          c[0] += x * peso
          c[1] += y * peso
          c[2] += peso
        } else celdas.set(k, [x * peso, y * peso, peso])
      }
      const puntos = []
      let max = 0
      for (const [sx, sy, w] of celdas.values()) {
        puntos.push([sx / w, sy / w, w])
        if (w > max) max = w
      }
      // simpleheat trabaja en píxeles reales del canvas: se escalan coordenadas y radio por dpr
      const calor = simpleheat(this._canvas)
      calor
        .data(puntos.map(([x, y, w]) => [x * dpr, y * dpr, w]))
        .max(Math.max(1, max * 0.55))
        .radius(radio * dpr, radio * 0.9 * dpr)
        .gradient({ 0.25: '#F5A3AF', 0.5: '#F06A7E', 0.75: '#EE2B47', 1: '#A3122A' })
      calor.draw(0.08)
      return
    }

    // Modo puntos: un color por nivel de gravedad, el ruido en gris
    const lado = zoom >= 16 ? 4 : zoom >= 15 ? 3.2 : zoom >= 14 ? 2.6 : zoom >= 13 ? 2 : 1.6
    const mitad = lado / 2
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    const grupos = [[], [], [], [], [], []] // 0..4 gravedad, 5 ruido
    for (let i = 0; i < datos.length; i++) {
      const esRuido = datos[i][3] == null
      if (esRuido && !mostrarRuido) continue
      if (!esRuido && !mostrarAgrupados) continue
      const x = xs[i] * escala - origen.x
      const y = ys[i] * escala - origen.y
      if (x < -4 || y < -4 || x > ancho + 4 || y > alto + 4) continue
      grupos[esRuido ? 5 : datos[i][2]].push(x, y)
    }
    const dibujarGrupo = (coords, color, alfa) => {
      ctx.globalAlpha = alfa
      ctx.fillStyle = color
      for (let j = 0; j < coords.length; j += 2) ctx.fillRect(coords[j] - mitad, coords[j + 1] - mitad, lado, lado)
    }
    dibujarGrupo(grupos[5], '#6B6E82', zoom >= 14 ? 0.32 : 0.22)
    for (let g = 0; g <= 4; g++) dibujarGrupo(grupos[g], GRAVEDAD[g].color, zoom >= 14 ? 0.85 : 0.62)
    ctx.globalAlpha = 1
  },
})

export default function CapaPuntos({
  datos,
  modo = 'puntos',
  mostrarRuido = true,
  mostrarAgrupados = true,
  pane = 'puntos',
}) {
  const map = useMap()
  const capa = useRef(null)

  useEffect(() => {
    const c = new CanvasPuntos({ modo, mostrarRuido, mostrarAgrupados, pane })
    capa.current = c
    c.addTo(map)
    return () => {
      c.remove()
      capa.current = null
    }
  }, [map, pane]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    capa.current?.ponerDatos(datos ?? [])
  }, [datos])

  useEffect(() => {
    capa.current?.ponerOpciones({ modo, mostrarRuido, mostrarAgrupados })
  }, [modo, mostrarRuido, mostrarAgrupados])

  return null
}
