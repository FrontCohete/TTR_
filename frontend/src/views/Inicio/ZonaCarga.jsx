import { useDropzone } from 'react-dropzone'
import { motion } from 'motion/react'
import { FileSpreadsheet, FolderOpen, RefreshCw, X } from 'lucide-react'
import Boton from '../../components/ui/Boton.jsx'
import Aviso from '../../components/ui/Aviso.jsx'
import { fmtBytes, fmtEntero } from '../../lib/formato.js'
import { useMedia } from '../../hooks/useMedia.js'
import s from './Inicio.module.css'

const TIPOS = {
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'application/vnd.ms-excel': ['.xls', '.csv'],
  'text/csv': ['.csv'],
}

/**
 * Zona para arrastrar o elegir el archivo (.csv, .xlsx o .xls).
 * Estados: vacía · arrastrando · leyendo (con avance) · archivo listo · error.
 */
export default function ZonaCarga({ alElegir, leyendo, avance, archivo, previa, error, alQuitar, bloqueada }) {
  const tactil = useMedia('(pointer: coarse)')
  const { getRootProps, getInputProps, isDragActive, isDragReject, open } = useDropzone({
    accept: TIPOS,
    multiple: false,
    noClick: true,
    noKeyboard: true,
    disabled: leyendo || bloqueada,
    onDrop: (aceptados, rechazados) => {
      if (aceptados[0]) alElegir(aceptados[0])
      else if (rechazados[0]) alElegir(rechazados[0].file, 'tipo')
    },
  })

  if (previa && !leyendo) {
    return (
      <div className={s.archivoListo}>
        <span className={s.archivoIcono} aria-hidden="true">
          <FileSpreadsheet size={22} />
        </span>
        <div className={s.archivoDatos}>
          <p className={s.archivoNombre}>{previa.nombre_archivo}</p>
          <p className={s.archivoMeta}>
            {previa.filas_leidas != null
              ? `${fmtEntero(previa.filas_leidas)} filas${previa.hoja ? ` en la hoja “${previa.hoja}”` : ''}`
              : `Archivo ${(previa.formato ?? '').toUpperCase()}`}
            {archivo ? `, ${fmtBytes(archivo.size)}` : ''}
          </p>
        </div>
        {!bloqueada && (
          <div className={s.archivoAcciones}>
            <input {...getInputProps()} />
            <Boton tamano="s" variante="fantasma" icono={RefreshCw} onClick={open}>
              Cambiar
            </Boton>
            <Boton tamano="s" variante="fantasma" icono={X} soloIcono onClick={alQuitar}>
              Quitar archivo
            </Boton>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className={s.zonaEnvoltura}>
      <div
        {...getRootProps({
          className: `${s.zona} ${isDragActive ? s.zonaActiva : ''} ${isDragReject ? s.zonaRechazo : ''}`,
        })}
      >
        <input {...getInputProps()} aria-label="Elegir archivo CSV o Excel" />
        {leyendo ? (
          <div className={s.zonaLectura} role="status" aria-live="polite">
            <FileSpreadsheet size={28} aria-hidden="true" className={s.zonaIconoLectura} />
            <p className={s.zonaTitulo}>Leyendo {archivo?.name}</p>
            <div className={s.barraLectura} aria-hidden="true">
              <motion.span
                className={s.barraLecturaRelleno}
                initial={false}
                animate={{ scaleX: Math.max(0.03, avance) }}
                transition={{ duration: 0.2, ease: 'linear' }}
              />
            </div>
            <p className={s.zonaPista}>{Math.round(avance * 100)}% · validando columnas y contando filas de GAM</p>
          </div>
        ) : (
          <>
            <motion.span
              className={s.zonaIcono}
              aria-hidden="true"
              animate={{ y: isDragActive ? -4 : 0, scale: isDragActive ? 1.06 : 1 }}
              transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
            >
              <FileSpreadsheet size={28} />
            </motion.span>
            <p className={s.zonaTitulo}>
              {isDragActive
                ? 'Suelta el archivo para leerlo'
                : tactil
                  ? 'Elige el archivo de víctimas de la FGJ'
                  : 'Arrastra aquí el archivo de víctimas de la FGJ'}
            </p>
            {!tactil && <p className={s.zonaPista}>o</p>}
            <Boton variante="secundario" icono={FolderOpen} onClick={open} disabled={bloqueada}>
              Elegir archivo
            </Boton>
            <p className={s.zonaPista}>Un archivo a la vez: .csv, .xlsx o .xls. Las filas repetidas se descartan.</p>
          </>
        )}
      </div>
      {error && (
        <Aviso tipo="error" titulo={error.titulo}>
          {error.mensaje}
        </Aviso>
      )}
    </div>
  )
}
