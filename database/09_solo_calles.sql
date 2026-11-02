-- 09_solo_calles.sql · Versión solo-calles (1 nov 2026): mutación mixta e inserción, y pulido final.
-- Se aplica UNA vez, como ttr_app, desde la carpeta _TTR_Dev (después del 07):
--     psql -U ttr_app -d ttr_clusteragent -f database\09_solo_calles.sql
-- No borra datos. Se puede volver a correr sin problema.
--
-- 1. op_mutacion admite 'mixta' (inversión o inserción, la de por omisión) e 'insercion'.
-- 2. pulido: el resultado del pulido final de cada agente
--    {antes_m, despues_m, invertida, movimientos: [{segmento: [id_hotspot…], entre: [id, id], ahorro_m}]}.
-- Los agentes viejos se quedan como están (metrica = 'recta', pulido = null).

BEGIN;

ALTER TABLE ejecucion_ag DROP CONSTRAINT IF EXISTS ejecucion_ag_op_mutacion_check;
ALTER TABLE ejecucion_ag ADD CONSTRAINT ejecucion_ag_op_mutacion_check
    CHECK (op_mutacion IN ('mixta', 'inversion', 'insercion', 'swap'));

ALTER TABLE ejecucion_ag ADD COLUMN IF NOT EXISTS pulido jsonb;

COMMENT ON COLUMN ejecucion_ag.pulido IS
  'Pulido final (or-opt con sentido) de la mejor ruta del genético: antes_m, despues_m, invertida y movimientos.';
COMMENT ON COLUMN ejecucion_ag.mejor_distancia IS
  'Metros por calles con sentido de la ruta guardada (ya pulida). En línea recta: distancia_recta_m.';

COMMIT;
