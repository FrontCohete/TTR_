-- =====================================================================
-- 02_ajustes.sql · TTR_ClusterAgent
-- Ajustes para la integración con el frontend (README_INTEGRACION §5).
-- Se aplica SOBRE la base creada con 01_esquema.sql y no modifica datos.
-- Se puede ejecutar más de una vez sin error (IF NOT EXISTS).
-- =====================================================================
SET client_encoding = 'UTF8';
\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------
-- Vista Inicio: progreso y formato de cada carga
-- ---------------------------------------------------------------------
ALTER TABLE carga_dataset
    ADD COLUMN IF NOT EXISTS etapa   varchar(20)
        CHECK (etapa IN ('limpieza', 'insercion', 'hdbscan')),
    ADD COLUMN IF NOT EXISTS avance  smallint NOT NULL DEFAULT 0
        CHECK (avance BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS formato varchar(5)
        CHECK (formato IN ('csv', 'xlsx', 'xls'));

-- ---------------------------------------------------------------------
-- Vista Analizar: colonia más frecuente de cada hotspot
-- ---------------------------------------------------------------------
ALTER TABLE hotspot
    ADD COLUMN IF NOT EXISTS colonia varchar(150);

-- ---------------------------------------------------------------------
-- Vista Rutas: datos de cada agente y detalle de cada generación
-- ---------------------------------------------------------------------
ALTER TABLE ejecucion_ag
    ADD COLUMN IF NOT EXISTS ruta_cerrada     boolean  NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS avance           smallint NOT NULL DEFAULT 0
        CHECK (avance BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS generacion_mejor int
        CHECK (generacion_mejor >= 0),
    ADD COLUMN IF NOT EXISTS duracion_s       double precision
        CHECK (duracion_s >= 0),
    ADD COLUMN IF NOT EXISTS mensaje_error    text;

ALTER TABLE generacion
    ADD COLUMN IF NOT EXISTS operaciones jsonb;

-- ---------------------------------------------------------------------
-- Documentación dentro de la base (aparece en el diccionario de datos)
-- ---------------------------------------------------------------------
COMMENT ON TABLE  carga_dataset IS 'Cada archivo subido (.csv, .xlsx o .xls); origen de la trazabilidad';
COMMENT ON COLUMN carga_dataset.etapa   IS 'Paso activo del procesamiento: limpieza, insercion o hdbscan';
COMMENT ON COLUMN carga_dataset.avance  IS 'Porcentaje de avance del procesamiento (0 a 100)';
COMMENT ON COLUMN carga_dataset.formato IS 'Formato del archivo: csv, xlsx o xls';
COMMENT ON COLUMN hotspot.colonia       IS 'Colonia más frecuente entre los puntos del hotspot';
COMMENT ON COLUMN ejecucion_ag.ruta_cerrada     IS 'true: la ruta regresa al hotspot de origen';
COMMENT ON COLUMN ejecucion_ag.avance           IS 'Porcentaje de generaciones calculadas (0 a 100)';
COMMENT ON COLUMN ejecucion_ag.generacion_mejor IS 'Generación donde apareció la mejor ruta histórica';
COMMENT ON COLUMN ejecucion_ag.duracion_s       IS 'Segundos que tardó la corrida completa';
COMMENT ON COLUMN ejecucion_ag.mensaje_error    IS 'Motivo del fallo cuando estado = error';
COMMENT ON COLUMN generacion.operaciones IS 'Torneos, cruces y mutaciones que formaron esta generación; NULL en la generación 0';

COMMIT;

-- ---------------------------------------------------------------------
-- Comprobación: las 12 columnas nuevas
-- ---------------------------------------------------------------------
SELECT table_name AS tabla, column_name AS columna, data_type AS tipo, column_default AS por_defecto
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (table_name, column_name) IN (
      ('carga_dataset', 'etapa'), ('carga_dataset', 'avance'), ('carga_dataset', 'formato'),
      ('hotspot', 'colonia'),
      ('ejecucion_ag', 'ruta_cerrada'), ('ejecucion_ag', 'avance'), ('ejecucion_ag', 'generacion_mejor'),
      ('ejecucion_ag', 'duracion_s'), ('ejecucion_ag', 'mensaje_error'),
      ('generacion', 'operaciones'))
ORDER BY table_name, ordinal_position;