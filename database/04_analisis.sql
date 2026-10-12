-- 04_analisis.sql · Etapa 3 (HDBSCAN): criterios con que se hizo cada análisis
-- Se aplica desde la carpeta backend con:
--   psql -U ttr_app -d ttr_clusteragent -f ..\database\04_analisis.sql
SET client_encoding = 'UTF8';
\set ON_ERROR_STOP on
BEGIN;

ALTER TABLE analisis_hdbscan
    ADD COLUMN peso_minimo           smallint NOT NULL DEFAULT 2
                                     CHECK (peso_minimo BETWEEN 1 AND 4),
    ADD COLUMN fecha_desde           date,
    ADD COLUMN min_cluster_size_base int CHECK (min_cluster_size_base >= 2),
    ADD COLUMN hotspots_minimos      int CHECK (hotspots_minimos >= 0);

-- Ya no usamos haversine: las coordenadas se proyectan a UTM 14N (metros)
ALTER TABLE analisis_hdbscan ALTER COLUMN metrica SET DEFAULT 'euclidiana_utm';

COMMENT ON COLUMN analisis_hdbscan.peso_minimo IS
    'Gravedad mínima de los puntos analizados (2 = Media, Alta y Crítica)';
COMMENT ON COLUMN analisis_hdbscan.fecha_desde IS
    'Solo hechos con fecha_hecho desde este día; NULL = sin filtro de fecha';
COMMENT ON COLUMN analisis_hdbscan.min_cluster_size_base IS
    'min_cluster_size configurado (150)';
COMMENT ON COLUMN analisis_hdbscan.min_cluster_size IS
    'min_cluster_size usado; menor que el base solo si se activó el mínimo de hotspots';
COMMENT ON COLUMN analisis_hdbscan.hotspots_minimos IS
    'Mínimo de seguridad de hotspots (50)';
COMMENT ON COLUMN hotspot.lat_centroide IS
    'Latitud del medoide: la víctima real más central del hotspot (posición del nodo)';
COMMENT ON COLUMN hotspot.lon_centroide IS
    'Longitud del medoide: la víctima real más central del hotspot (posición del nodo)';

COMMIT;