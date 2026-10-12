-- =====================================================================
-- 03_resumen_carga.sql · TTR_ClusterAgent
-- Guarda el resumen de la limpieza de cada carga: filas descartadas por
-- motivo, edades anuladas, delitos desconocidos y la regla A + P.
-- Se puede ejecutar más de una vez sin error (IF NOT EXISTS).
-- =====================================================================
SET client_encoding = 'UTF8';
\set ON_ERROR_STOP on

BEGIN;

ALTER TABLE carga_dataset
    ADD COLUMN IF NOT EXISTS resumen_limpieza jsonb;

COMMENT ON COLUMN carga_dataset.resumen_limpieza IS
    'Resumen de la limpieza: descartes por motivo, edades anuladas, delitos desconocidos y regla A + P';

COMMIT;

SELECT column_name AS columna, data_type AS tipo
  FROM information_schema.columns
 WHERE table_name = 'carga_dataset' AND column_name = 'resumen_limpieza';