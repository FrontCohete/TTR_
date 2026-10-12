# TTR_ · Sistema de diseño

## Idea central

La aplicación es una **línea de transporte**: los datos viajan de Inicio a Simular como un tren por sus estaciones. Los hotspots son **estaciones** (círculo blanco con aro de color y su número), cada grafo es una **línea** con su color, y cada ruta del algoritmo genético se dibuja como el diagrama de una línea, con el orden de visita de izquierda a derecha. La referencia es la señalética de transporte de la Ciudad de México: placas oscuras, colores de línea y números legibles.

## Color

| Token | Valor | Uso |
|---|---|---|
| `--ttr-noche` | `#2C2E3E` | Barra superior, placas sobre el mapa, reproductor, base acumulada |
| `--ttr-pizarra` | `#34374C` | Texto secundario, superficies oscuras elevadas |
| `--ttr-senal` | `#EE2B47` | Hotspots, etapa activa, tramo recorrido, foco de teclado |
| `--senal-accion` | `#E3213E` | Relleno de botones principales (texto blanco a 4.6:1) |
| `--ttr-niebla` | `#F6F6F6` | Fondo de trabajo |
| `--ttr-papel` | `#FFF9F2` | Paneles y superficies de lectura |
| `--ttr-tinta` | `#000000` | Títulos, cifras y texto principal |

- El rojo de marca con texto blanco da 4.1:1, por debajo de WCAG AA para texto normal. Los botones usan `--senal-accion`, un tono casi idéntico que pasa (4.6:1). El rojo de marca se conserva intacto en trazos, íconos, marcadores y barras.
- Texto rojo pequeño sobre claro: `--senal-texto` `#C8102E`.
- Números sobre círculos de color: `textoSobre(color)` en `src/lib/colores.js` elige blanco o negro según el contraste.

### Grafos (1 a 5)

`#1F5FD0` azul · `#B87A00` ocre · `#13907A` turquesa · `#8E3B9E` violeta · `#4E6B1F` oliva. Validados para daltonismo en todas las parejas hasta 4 grafos; con 5 la pareja turquesa-oliva queda cerca, por eso **el número del grafo siempre acompaña al color** (estaciones, pestañas, leyenda, agentes). El rojo queda reservado para hotspots y acciones.

### Gravedad del delito (rampa de un solo tono)

No aplica `#9A9CAB` · Baja `#F5A3AF` · Media `#F06A7E` · Alta `#EE2B47` · Crítica `#A3122A`. El ruido de HDBSCAN va en gris pizarra translúcido.

## Tipografía

- **Overpass** (variable): toda la interfaz. Proviene de Highway Gothic, la letra de la señalización vial; encaja con la idea de rutas. Títulos 800, controles 700, texto 400–600.
- **Overpass Mono**: solo para datos y medidas (códigos `H-07`, distancias, columnas del xlsx, parámetros).
- Escala fija en rem: 11 · 12 · 13 · 15 (cuerpo) · 18 · 22 · 28 · 40.

## Componentes

- **Línea de etapas** (barra superior): 4 estaciones; el tramo recorrido en rojo se anima al cambiar de vista. Las estaciones se bloquean hasta que existe lo que necesitan, con el motivo como texto accesible.
- **Estación**: círculo blanco, aro de 3 px del color del grafo (rojo si no hay partición), número en mono. Activa = relleno de color.
- **Tira de ruta**: estaciones unidas por tramos; el regreso al inicio se dibuja punteado con flecha. En el cruce, relleno = gen del padre A, contorno oscuro = gen del padre B.
- **Flujo del AG**: tarjetas de acción unidas por conectores y un contenedor “Para cada generación” (gramática de Power Automate). La etapa activa lleva un marco rojo que se desliza entre tarjetas.
- **Panel adaptable**: columna derecha en tableta y escritorio; hoja inferior arrastrable en móvil, con el resumen y la acción principal siempre visibles.
- **Botón**: primario (rojo, una sola acción principal por vista), secundario, fantasma y oscuro (sobre cromo). Altos de 32, 40 y 48 px.
- **Control segmentado**: opciones excluyentes (N de grafos, modo de ejecución, velocidad); flechas del teclado para moverse.

## Movimiento

- Curva firma `cubic-bezier(0.2, 0, 0, 1)`; duraciones 140 / 240 / 420 ms.
- Momentos con movimiento: tramo de la línea de etapas, entrada de la vista, indicador del control segmentado, marco de la etapa activa, intercambio de estaciones en la mutación, agentes en Simular (requestAnimationFrame) y su onda.
- Nada se mueve solo para decorar. Con “reducir movimiento” activo en el sistema, las transiciones se vuelven instantáneas.

## Diseño responsivo

- Móvil < 768 px: una columna; paneles como hoja inferior; flujo del AG horizontal; reproductor fijo abajo.
- Tableta 768–1199 px: mapa + panel lateral; en Rutas, flujo + detalle y la gráfica debajo.
- Escritorio ≥ 1200 px: Rutas en tres columnas (flujo, detalle, evolución).

## Accesibilidad

- Contraste AA verificado con axe en las cuatro vistas.
- Todo control con ícono solo lleva nombre accesible; el color nunca va solo (ícono + texto, número + color).
- Foco visible rojo; enlace “Saltar al contenido”; un `h1` por vista.
- Teclado en Rutas: espacio reproduce o avanza, ← y → cambian de etapa.
