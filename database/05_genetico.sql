-- 05_genetico.sql · Etapa 5: algoritmo genético con élite.
-- Se aplica UNA vez, como ttr_app, después de un respaldo con pg_dump.
-- Decisiones: claude/DECISIONES_ETAPA5_GENETICO.md (16 de octubre de 2026).

BEGIN;

-- 1. La élite es un origen nuevo de individuo. Se quita el CHECK viejo de «origen», tenga el nombre que tenga.
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT conname FROM pg_constraint
    WHERE conrelid = 'individuo'::regclass AND contype = 'c' AND pg_get_constraintdef(oid) LIKE '%origen%'
  LOOP
    EXECUTE format('ALTER TABLE individuo DROP CONSTRAINT %I', r.conname);
  END LOOP;
END $$;
ALTER TABLE individuo
  ADD CONSTRAINT individuo_origen_check CHECK (origen IN ('aleatorio', 'cruce', 'mutacion', 'elite'));

-- 2. Columnas de ejecucion_ag. Las cinco primeras ya las agregó 02_ajustes.sql; IF NOT EXISTS no las toca.
ALTER TABLE ejecucion_ag ADD COLUMN IF NOT EXISTS ruta_cerrada     boolean NOT NULL DEFAULT true;
ALTER TABLE ejecucion_ag ADD COLUMN IF NOT EXISTS avance           int     NOT NULL DEFAULT 0;
ALTER TABLE ejecucion_ag ADD COLUMN IF NOT EXISTS generacion_mejor int;
ALTER TABLE ejecucion_ag ADD COLUMN IF NOT EXISTS duracion_s       double precision;
ALTER TABLE ejecucion_ag ADD COLUMN IF NOT EXISTS mensaje_error    text;
ALTER TABLE ejecucion_ag ADD COLUMN IF NOT EXISTS n_elite          int     NOT NULL DEFAULT 1;
ALTER TABLE ejecucion_ag ADD COLUMN IF NOT EXISTS rutas_borradas   boolean NOT NULL DEFAULT false;
ALTER TABLE ejecucion_ag DROP CONSTRAINT IF EXISTS ejecucion_ag_n_elite_check;
ALTER TABLE ejecucion_ag ADD CONSTRAINT ejecucion_ag_n_elite_check CHECK (n_elite >= 0 AND n_elite < tam_poblacion);

-- 3. El JSON de operaciones por generación (también de 02_ajustes.sql).
ALTER TABLE generacion ADD COLUMN IF NOT EXISTS operaciones jsonb;

COMMENT ON COLUMN ejecucion_ag.n_elite IS
  'Rutas que pasan intactas a la siguiente generación, en las últimas posiciones (origen elite). Fija en 1.';
COMMENT ON COLUMN ejecucion_ag.rutas_borradas IS
  'true cuando sus filas de individuo se borraron porque hay una corrida más nueva del mismo grafo. Se conservan ejecucion_ag y generacion.';

COMMIT;