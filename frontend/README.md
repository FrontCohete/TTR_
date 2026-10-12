# TTR_ · Frontend

Interfaz web de **TTR_ClusterAgent**: carga de datasets de la FGJ (.csv, .xlsx o .xls), hotspots de Gustavo A. Madero con HDBSCAN, partición en grafos con Louvain, reproducción paso a paso del algoritmo genético y simulación de los agentes recorriendo sus rutas.

- **React 19 + Vite 8** (JavaScript)
- **React Router 8**: vistas `/`, `/analizar`, `/rutas`, `/simular`
- **TanStack Query 5**: datos del servidor, caché y consulta periódica del avance
- **Leaflet + react-leaflet**: mapa (OpenStreetMap/CARTO, sin clave)
- **Turf**: geometría (envolventes, distancias); servirá para el ruteo por calles
- **Recharts**: curva de aptitud del algoritmo genético
- **Motion**: animaciones (respetan “reducir movimiento” del sistema)
- **Zustand**: estado de la sesión (lo que se decide entre vistas)
- **lucide-react**: íconos; **Overpass** como tipografía (incluida, funciona sin internet)

---

## 1. Requisitos (una sola vez)

1. Instala **Node.js LTS** (versión 22.22 o más reciente) desde <https://nodejs.org>.
2. Cierra y vuelve a abrir VS Code para que la terminal reconozca Node.
3. Verifica en la **terminal de PowerShell** (el prompt empieza con `PS C:\...>`):

```powershell
node --version
npm --version
```

Deben mostrar un número de versión cada uno (por ejemplo `v24.x.x` y `11.x.x`).

## 2. Instalar dependencias (una sola vez)

En la **terminal de PowerShell**, desde la carpeta del proyecto:

```powershell
cd "C:\Users\Cohete_owo\OneDrive - Instituto Politecnico Nacional\Desktop\_TTR_Dev\frontend"
npm install
```

Se crea la carpeta `node_modules` (miles de archivos). Si OneDrive se pone lento o marca archivos bloqueados, pausa la sincronización mientras instalas o mueve `_TTR_Dev` a `C:\dev\`.

## 3. Correr la interfaz

En la **terminal de PowerShell**, dentro de `frontend`:

```powershell
npm run dev
```

Abre <http://localhost:5173> en el navegador. Para detenerla: `Ctrl + C` en la terminal.

Mientras no exista el backend, la interfaz usa **datos simulados** (verás la etiqueta “Datos simulados” arriba a la derecha). Los mapas, colonias, puntos y hotspots de los datos simulados son **reales**: salen de `database/fuentes` y de los CSV de la FGJ 2022–2024; lo simulado es el comportamiento del servidor (tiempos, identificadores, estados).

## 4. Conectar el backend de FastAPI

1. Arranca FastAPI en el puerto 8000 (en otra terminal, con `(.venv)` activo).
2. Abre el archivo **`frontend/src/config.js`** en el editor y cambia:

```js
usarDatosSimulados: false,
```

3. Guarda el archivo. Vite recarga la página solo; si no, detén y vuelve a correr `npm run dev`.

Vite reenvía todo lo que empiece con `/api` a `http://localhost:8000`, así que no hace falta configurar CORS en desarrollo.

## 5. Generar la versión final

```powershell
npm run build
```

El resultado queda en `frontend/dist` (ya está en `.gitignore`). Para probarla: `npm run preview`.

---

## Estructura

```
frontend/
├── index.html                 título, descripción y metadatos
├── vite.config.js             proxy /api → FastAPI
├── .env.example               variables opcionales (VITE_USE_MOCKS, VITE_API_URL, VITE_ROUTER)
├── DESIGN.md                  sistema de diseño (colores, tipografía, movimiento)
└── src/
    ├── config.js              usarDatosSimulados: true | false
    ├── main.jsx               arranque: React Query + Motion
    ├── App.jsx                rutas de las 4 vistas
    ├── api/
    │   ├── cliente.js         fetch con manejo de errores de FastAPI
    │   ├── real.js            un método por endpoint del contrato (§7)
    │   ├── index.js           elige backend real o simulado
    │   └── consultas.js       hooks de TanStack Query
    ├── mocks/                 servidor simulado (se puede borrar cuando exista el backend)
    │   ├── servidor.js        implementa el contrato en el navegador
    │   ├── genetico.js        algoritmo genético de referencia con registro de operaciones
    │   ├── leerXlsx.js        lee encabezado y primeras filas de un xlsx
    │   ├── leerCsv.js         lo mismo para CSV (los .xls los lee solo el backend)
    │   └── data/              GeoJSON y JSON reales precalculados
    ├── store/sesion.js        N de grafos, parámetros del AG, agentes lanzados
    ├── components/
    │   ├── layout/            barra superior, línea de etapas, logotipo
    │   ├── mapa/              mapa base, capa de puntos (canvas), hotspots, leyenda
    │   └── ui/                botón, control segmentado, interruptor, panel adaptable…
    ├── views/
    │   ├── Inicio/            carga, vista previa, progreso, base acumulada
    │   ├── Analizar/          mapa + panel (partición, capas, hotspots, parámetros)
    │   ├── Rutas/             flujo de 7 etapas, detalle, reproductor, gráfica
    │   └── Simular/           animación de agentes y reloj simulado
    ├── lib/                   formatos es-MX, colores, geometría
    └── styles/                tokens.css, global.css, mapa.css
```

## Notas para el backend (coordinación con el contrato §7)

La interfaz funciona con el contrato tal como está. Estos campos **opcionales** mejoran lo que se muestra; si el backend no los envía, la interfaz no falla:

| Endpoint | Campo | Para qué |
|---|---|---|
| `POST /api/cargas` | `columnas.todas` | Orden original de columnas en la vista previa |
| `GET /api/cargas` | `nombre_archivo` en cada carga | Historial en Inicio |
| `GET /api/analisis/vigente/hotspots` | `properties.colonia` | Nombre del lugar junto al código `H-07` |
| `GET /api/agentes/{id}` | `avance` (0–100) mientras corre | Barra de “Calculando…” |
| `GET /api/agentes/{id}` | `generacion_mejor` | “Ruta de la generación N” en Simular |
| `GET /api/generaciones/{id}/individuos` | `torneos[].hijo`, `cruces[].aplicado`, `mutaciones[].tipo` | Relacionar cada operación con su hijo |
| `GET /api/agentes/{id}/ruta` | `properties.hotspots`, `ruta_cerrada`, `generacion_mejor` | Orden de visita y regreso al inicio |
| `POST /api/agentes` | `parametros.ruta_cerrada` | Decisión abierta: ruta cerrada o abierta |

Convenciones que la interfaz asume:

- En `operaciones.torneos` hay **dos torneos por hijo**, en orden: `torneos[2i]` da el padre A y `torneos[2i+1]` el padre B del hijo `i`.
- `padres`, `participantes` y `ganador` son **posiciones** en la generación anterior; `hijo` e `individuo` son posiciones en la generación actual.
- Las distancias van en **metros**; las coordenadas sueltas en `[longitud, latitud]`.
- Colores de grafo recomendados (los mismos de `src/lib/colores.js`): `#1F5FD0`, `#B87A00`, `#13907A`, `#8E3B9E`, `#4E6B1F`.
- `POST /api/cargas` debe aceptar **.csv, .xlsx y .xls** (campo `archivo`). En pandas: `read_csv` (probar `utf-8` y, si falla, `latin-1`), `read_excel(engine="openpyxl")` para .xlsx y `read_excel(engine="xlrd")` para .xls (agregar `xlrd` a `requirements.txt`). La respuesta puede incluir `formato` (`"csv"`, `"xlsx"` o `"xls"`).
- El modo simulado nombra el error 409 cuando el nombre de archivo ya se cargó; el backend real usa la huella SHA-256.

## Mapa sin internet

Si las teselas de OpenStreetMap/CARTO no cargan, el mapa dibuja las 179 colonias como mapa base y lo avisa. Para usar otro proveedor (Mapbox, MapTiler) basta cambiar `TESELAS` en `src/components/mapa/MapaGAM.jsx`.
