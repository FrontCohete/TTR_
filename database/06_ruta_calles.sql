-- 06_ruta_calles.sql · Etapa 6: trazo por calles de cada agente (vista Simular).
-- Se aplica UNA vez, como ttr_app. No toca datos existentes.
-- El genético decide el orden en línea recta; aquí se guarda el dibujo por calles que devolvió OSRM,
-- para no volver a pedirlo. Se borra solo con su agente (ON DELETE CASCADE) o con «Empezar de cero».

BEGIN;

CREATE TABLE IF NOT EXISTS ruta_calles (
    id_ejecucion     bigint            PRIMARY KEY REFERENCES ejecucion_ag (id_ejecucion) ON DELETE CASCADE,
    proveedor        varchar(80)       NOT NULL,
    perfil           varchar(20)       NOT NULL DEFAULT 'driving',
    distancia_m      double precision  NOT NULL CHECK (distancia_m >= 0),
    duracion_s       double precision  CHECK (duracion_s >= 0),
    geometria        jsonb             NOT NULL,
    tramos           jsonb             NOT NULL,
    indices_paradas  jsonb             NOT NULL,
    fecha            timestamptz       NOT NULL DEFAULT now()
);

COMMENT ON TABLE ruta_calles IS
  'Recorrido por calles (OSRM) de la ruta óptima de cada agente. Solo para dibujar en Simular; el orden lo decide el genético.';
COMMENT ON COLUMN ruta_calles.geometria IS 'Vértices [[lon, lat], …] del recorrido completo por calles.';
COMMENT ON COLUMN ruta_calles.indices_paradas IS 'Índice en geometria de cada parada (incluido el regreso al inicio).';
COMMENT ON COLUMN ruta_calles.tramos IS '[{distancia_m, duracion_s}] de cada tramo entre paradas consecutivas.';

COMMIT;
