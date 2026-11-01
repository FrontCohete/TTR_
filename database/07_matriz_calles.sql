-- 07_matriz_calles.sql · Etapa 7 «la mejor de tres», fase 1.
-- Se aplica UNA vez, como ttr_app, desde la carpeta _TTR_Dev:
--     psql -U ttr_app -d ttr_clusteragent -f database\07_matriz_calles.sql
-- No borra datos. Se puede volver a correr sin problema (IF NOT EXISTS).
--
-- 1. matriz_calles: las distancias por calles (OSRM «table») entre TODOS los hotspots de un análisis.
--    Se piden una sola vez por análisis y se reutilizan en todas las tandas de agentes y en todas
--    las particiones N = 1…5. Se borra sola con su análisis (ON DELETE CASCADE) o con «Empezar de cero».
-- 2. ejecucion_ag: con qué forma de medir ganó cada agente y la comparación de las tres.
--    Los agentes que ya existen se optimizaron en línea recta: quedan con metrica = 'recta'.

BEGIN;

CREATE TABLE IF NOT EXISTS matriz_calles (
    id_analisis          bigint            PRIMARY KEY REFERENCES analisis_hdbscan (id_analisis) ON DELETE CASCADE,
    ids                  jsonb             NOT NULL,
    distancias_m         jsonb             NOT NULL,
    duraciones_s         jsonb             NOT NULL,
    sin_camino           integer           NOT NULL DEFAULT 0 CHECK (sin_camino >= 0),
    proveedor            varchar(80)       NOT NULL,
    perfil               varchar(20)       NOT NULL DEFAULT 'driving',
    duracion_consulta_s  double precision  CHECK (duracion_consulta_s >= 0),
    fecha                timestamptz       NOT NULL DEFAULT now()
);

COMMENT ON TABLE matriz_calles IS
  'Distancias y tiempos por calles (OSRM table) entre todos los hotspots de un análisis. Ida y vuelta pueden ser distintas.';
COMMENT ON COLUMN matriz_calles.ids IS 'id_hotspot de cada fila/columna, en orden de etiqueta.';
COMMENT ON COLUMN matriz_calles.distancias_m IS 'Matriz n × n en metros: fila = origen, columna = destino. null = OSRM no encontró camino.';
COMMENT ON COLUMN matriz_calles.sin_camino IS 'Pares sin camino; al usarlos se penalizan con 10 × la distancia en línea recta.';

ALTER TABLE ejecucion_ag
    ADD COLUMN IF NOT EXISTS metrica            varchar(20)       NOT NULL DEFAULT 'recta',
    ADD COLUMN IF NOT EXISTS distancia_recta_m  double precision,
    ADD COLUMN IF NOT EXISTS comparacion        jsonb;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ejecucion_ag_metrica_check') THEN
        ALTER TABLE ejecucion_ag ADD CONSTRAINT ejecucion_ag_metrica_check
            CHECK (metrica IN ('recta', 'calles', 'calles_promedio'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ejecucion_ag_distancia_recta_check') THEN
        ALTER TABLE ejecucion_ag ADD CONSTRAINT ejecucion_ag_distancia_recta_check
            CHECK (distancia_recta_m >= 0);
    END IF;
END $$;

-- agentes anteriores: se optimizaron y midieron en línea recta
UPDATE ejecucion_ag SET distancia_recta_m = mejor_distancia
WHERE distancia_recta_m IS NULL AND mejor_distancia IS NOT NULL AND metrica = 'recta';

COMMENT ON COLUMN ejecucion_ag.metrica IS
  'Forma de medir con la que se optimizó la ruta ganadora: recta (A), calles con sentido (B) o calles_promedio (C).';
COMMENT ON COLUMN ejecucion_ag.distancia_recta_m IS 'Largo de la ruta ganadora en línea recta (haversine).';
COMMENT ON COLUMN ejecucion_ag.comparacion IS
  '[{variante, metrica, km_calles, km_recta, generacion_mejor, segundos, ganadora}] de las tres corridas (A, B, C).';

COMMIT;
