-- 08_forma_de_medir.sql · Etapa 7: la persona elige en Analizar con qué medir las distancias.
-- Se aplica UNA vez, como ttr_app, desde la carpeta _TTR_Dev:
--     psql -U ttr_app -d ttr_clusteragent -f database\08_forma_de_medir.sql
-- No borra datos. Se puede volver a correr sin problema.
--
-- medir = lo que se PIDIÓ:   mejor_de_tres (A, B y C; gana la más corta por calles) · recta (solo A)
--                            · calles (solo B) · calles_promedio (solo C)
-- metrica = con qué se optimizó la ruta guardada (la ganadora, o la única).

BEGIN;

ALTER TABLE ejecucion_ag ADD COLUMN IF NOT EXISTS medir varchar(20) NOT NULL DEFAULT 'mejor_de_tres';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ejecucion_ag_medir_check') THEN
        ALTER TABLE ejecucion_ag ADD CONSTRAINT ejecucion_ag_medir_check
            CHECK (medir IN ('mejor_de_tres', 'recta', 'calles', 'calles_promedio'));
    END IF;
END $$;

-- los agentes de antes de la etapa 7 (sin comparación) se calcularon solo en línea recta
UPDATE ejecucion_ag SET medir = 'recta' WHERE comparacion IS NULL AND medir = 'mejor_de_tres';

COMMENT ON COLUMN ejecucion_ag.medir IS
  'Forma de medir pedida en Analizar: mejor_de_tres (A, B y C), recta (A), calles (B) o calles_promedio (C).';

COMMIT;
