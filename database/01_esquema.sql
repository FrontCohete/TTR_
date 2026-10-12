SET client_encoding = 'UTF8';
\set ON_ERROR_STOP on

BEGIN;


CREATE TABLE alcaldia (
    id_alcaldia  serial       PRIMARY KEY,
    nombre       varchar(60)  NOT NULL UNIQUE,
    geom         geometry(MultiPolygon, 4326) NOT NULL
);

CREATE TABLE colonia (
    id_colonia     serial        PRIMARY KEY,
    id_alcaldia    int           NOT NULL REFERENCES alcaldia (id_alcaldia),
    nombre         varchar(150)  NOT NULL,
    clave_oficial  varchar(20)   UNIQUE,
    geom           geometry(MultiPolygon, 4326) NOT NULL
);

CREATE TABLE cat_delito (
    id_delito          serial        PRIMARY KEY,
    nombre             varchar(255)  NOT NULL UNIQUE,
    categoria_oficial  varchar(120)  NOT NULL,
    grupo              varchar(80)   NOT NULL,
    gravedad           varchar(10)   NOT NULL
        CHECK (gravedad IN ('Crítica', 'Alta', 'Media', 'Baja', 'No aplica')),
    peso_gravedad      smallint      NOT NULL
        CHECK (peso_gravedad BETWEEN 0 AND 4)
);

CREATE TABLE carga_dataset (
    id_carga           bigserial     PRIMARY KEY,
    nombre_archivo     varchar(255)  NOT NULL,
    hash_archivo       char(64)      NOT NULL UNIQUE,
    fecha_carga        timestamptz   NOT NULL DEFAULT now(),
    filas_leidas       int           NOT NULL CHECK (filas_leidas >= 0),
    filas_validas      int           CHECK (filas_validas >= 0),
    puntos_gam_nuevos  int           CHECK (puntos_gam_nuevos >= 0),
    puntos_duplicados  int           CHECK (puntos_duplicados >= 0),
    estado             varchar(20)   NOT NULL DEFAULT 'recibido'
        CHECK (estado IN ('recibido', 'procesando', 'completado', 'error')),
    mensaje_error      text
);

CREATE TABLE punto_delictivo (
    id_punto          bigserial     PRIMARY KEY,
    id_carga          bigint        NOT NULL REFERENCES carga_dataset (id_carga),
    id_delito         int           NOT NULL REFERENCES cat_delito (id_delito),
    id_colonia        int           REFERENCES colonia (id_colonia),
    colonia_texto     varchar(150),
    fecha_hecho       date          NOT NULL,
    hora_hecho        time,
    fecha_inicio      date,
    sexo              varchar(15),
    edad              smallint      CHECK (edad BETWEEN 0 AND 100),
    tipo_persona      varchar(10),
    calidad_juridica  varchar(40),
    competencia       varchar(30),
    latitud           double precision NOT NULL CHECK (latitud  BETWEEN -90  AND 90),
    longitud          double precision NOT NULL CHECK (longitud BETWEEN -180 AND 180),
    -- Se calcula sola a partir de latitud y longitud: nunca se desincroniza
    geom              geometry(Point, 4326)
        GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitud, latitud), 4326)) STORED,
    -- La llena el trigger trg_punto_ubicacion
    dentro_gam        boolean       NOT NULL DEFAULT false,
    hash_registro     char(64)      NOT NULL UNIQUE
);


CREATE TABLE analisis_hdbscan (
    id_analisis         bigserial     PRIMARY KEY,
    id_carga_origen     bigint        NOT NULL REFERENCES carga_dataset (id_carga),
    id_analisis_previo  bigint        REFERENCES analisis_hdbscan (id_analisis) ON DELETE SET NULL,
    fecha               timestamptz   NOT NULL DEFAULT now(),
    min_cluster_size    int           NOT NULL CHECK (min_cluster_size >= 2),
    min_samples         int           CHECK (min_samples >= 1),
    metrica             varchar(20)   NOT NULL DEFAULT 'haversine',
    n_puntos            int           NOT NULL CHECK (n_puntos >= 0),
    n_hotspots          int           NOT NULL CHECK (n_hotspots >= 0),
    n_ruido             int           NOT NULL CHECK (n_ruido >= 0),
    duracion_s          double precision CHECK (duracion_s >= 0),
    resultado_json      jsonb,
    vigente             boolean       NOT NULL DEFAULT false
);

CREATE TABLE analisis_carga (
    id_analisis  bigint  NOT NULL REFERENCES analisis_hdbscan (id_analisis) ON DELETE CASCADE,
    id_carga     bigint  NOT NULL REFERENCES carga_dataset (id_carga),
    PRIMARY KEY (id_analisis, id_carga)
);

CREATE TABLE hotspot (
    id_hotspot           bigserial     PRIMARY KEY,
    id_analisis          bigint        NOT NULL REFERENCES analisis_hdbscan (id_analisis) ON DELETE CASCADE,
    etiqueta             int           NOT NULL CHECK (etiqueta >= 0),
    codigo               varchar(10)   NOT NULL,
    lat_centroide        double precision NOT NULL CHECK (lat_centroide BETWEEN -90  AND 90),
    lon_centroide        double precision NOT NULL CHECK (lon_centroide BETWEEN -180 AND 180),
    geom                 geometry(Point, 4326)
        GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon_centroide, lat_centroide), 4326)) STORED,
    geom_area            geometry(Polygon, 4326),
    n_puntos             int           NOT NULL CHECK (n_puntos > 0),
    persistencia         double precision,
    radio_m              double precision CHECK (radio_m >= 0),
    delito_predominante  varchar(255),
    indice_gravedad      double precision CHECK (indice_gravedad BETWEEN 0 AND 4),
    UNIQUE (id_analisis, etiqueta),
    UNIQUE (id_analisis, codigo)
);

CREATE TABLE membresia_hotspot (
    id_analisis   bigint  NOT NULL REFERENCES analisis_hdbscan (id_analisis) ON DELETE CASCADE,
    id_punto      bigint  NOT NULL REFERENCES punto_delictivo (id_punto) ON DELETE CASCADE,
    id_hotspot    bigint  REFERENCES hotspot (id_hotspot) ON DELETE CASCADE,  -- NULL = ruido
    probabilidad  double precision CHECK (probabilidad BETWEEN 0 AND 1),
    PRIMARY KEY (id_analisis, id_punto)
);

CREATE TABLE particion_louvain (
    id_particion  bigserial    PRIMARY KEY,
    id_analisis   bigint       NOT NULL REFERENCES analisis_hdbscan (id_analisis) ON DELETE CASCADE,
    n_grafos      smallint     NOT NULL CHECK (n_grafos BETWEEN 1 AND 5),
    resolucion    double precision CHECK (resolucion > 0),
    modularidad   double precision,
    semilla       int,
    grafos_json   jsonb,
    fecha         timestamptz  NOT NULL DEFAULT now(),
    vigente       boolean      NOT NULL DEFAULT false
);

CREATE TABLE grafo (
    id_grafo      bigserial   PRIMARY KEY,
    id_particion  bigint      NOT NULL REFERENCES particion_louvain (id_particion) ON DELETE CASCADE,
    numero        smallint    NOT NULL CHECK (numero BETWEEN 1 AND 5),
    n_nodos       int         NOT NULL CHECK (n_nodos >= 0),
    n_aristas     int         NOT NULL CHECK (n_aristas >= 0),
    color         varchar(7)  CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    UNIQUE (id_particion, numero),
    UNIQUE (id_grafo, id_particion)   -- permite la llave compuesta de nodo_grafo
);

CREATE TABLE nodo_grafo (
    id_particion  bigint  NOT NULL,
    id_hotspot    bigint  NOT NULL REFERENCES hotspot (id_hotspot) ON DELETE CASCADE,
    id_grafo      bigint  NOT NULL,
    PRIMARY KEY (id_particion, id_hotspot),   -- un hotspot, un solo grafo por partición
    -- garantiza que el grafo pertenezca a la misma partición
    FOREIGN KEY (id_grafo, id_particion)
        REFERENCES grafo (id_grafo, id_particion) ON DELETE CASCADE
);

CREATE TABLE arista (
    id_grafo     bigint  NOT NULL REFERENCES grafo (id_grafo) ON DELETE CASCADE,
    id_origen    bigint  NOT NULL REFERENCES hotspot (id_hotspot) ON DELETE CASCADE,
    id_destino   bigint  NOT NULL REFERENCES hotspot (id_hotspot) ON DELETE CASCADE,
    distancia_m  double precision NOT NULL CHECK (distancia_m >= 0),
    PRIMARY KEY (id_grafo, id_origen, id_destino),
    CHECK (id_origen <> id_destino)
);

CREATE TABLE ejecucion_ag (
    id_ejecucion     bigserial    PRIMARY KEY,
    id_grafo         bigint       NOT NULL REFERENCES grafo (id_grafo) ON DELETE CASCADE,
    tam_poblacion    int          NOT NULL CHECK (tam_poblacion > 1),
    n_generaciones   int          NOT NULL CHECK (n_generaciones > 0),
    tam_torneo       int          NOT NULL CHECK (tam_torneo >= 2),
    prob_cruce       double precision NOT NULL CHECK (prob_cruce    BETWEEN 0 AND 1),
    prob_mutacion    double precision NOT NULL CHECK (prob_mutacion BETWEEN 0 AND 1),
    op_cruce         varchar(10)  NOT NULL CHECK (op_cruce IN ('OX', 'PMX')),
    op_mutacion      varchar(10)  NOT NULL CHECK (op_mutacion IN ('swap', 'inversion')),
    semilla          int,
    mejor_distancia  double precision CHECK (mejor_distancia >= 0),
    ruta_optima      jsonb,
    estado           varchar(20)  NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'ejecutando', 'terminado', 'error')),
    fecha            timestamptz  NOT NULL DEFAULT now(),
    CHECK (tam_torneo <= tam_poblacion)
);

CREATE TABLE generacion (
    id_generacion      bigserial  PRIMARY KEY,
    id_ejecucion       bigint     NOT NULL REFERENCES ejecucion_ag (id_ejecucion) ON DELETE CASCADE,
    numero             int        NOT NULL CHECK (numero >= 0),
    mejor_fitness      double precision NOT NULL,
    fitness_promedio   double precision NOT NULL,
    peor_fitness       double precision NOT NULL,
    mejor_permutacion  jsonb      NOT NULL,
    UNIQUE (id_ejecucion, numero),
    CHECK (mejor_fitness <= fitness_promedio AND fitness_promedio <= peor_fitness)
);

CREATE TABLE individuo (
    id_individuo   bigserial    PRIMARY KEY,
    id_generacion  bigint       NOT NULL REFERENCES generacion (id_generacion) ON DELETE CASCADE,
    posicion       int          NOT NULL CHECK (posicion >= 0),
    permutacion    jsonb        NOT NULL,
    distancia      double precision NOT NULL CHECK (distancia >= 0),
    origen         varchar(15)  NOT NULL CHECK (origen IN ('aleatorio', 'cruce', 'mutacion')),
    id_padre_1     bigint       REFERENCES individuo (id_individuo) ON DELETE SET NULL,
    id_padre_2     bigint       REFERENCES individuo (id_individuo) ON DELETE SET NULL,
    UNIQUE (id_generacion, posicion)
);

CREATE TABLE simulacion (
    id_simulacion    bigserial    PRIMARY KEY,
    id_ejecucion     bigint       NOT NULL REFERENCES ejecucion_ag (id_ejecucion) ON DELETE CASCADE,
    fecha            timestamptz  NOT NULL DEFAULT now(),
    distancia_total  double precision CHECK (distancia_total >= 0),
    duracion_s       double precision CHECK (duracion_s >= 0)
);

CREATE UNIQUE INDEX ux_analisis_un_vigente
    ON analisis_hdbscan ((true)) WHERE vigente;

CREATE UNIQUE INDEX ux_particion_una_vigente
    ON particion_louvain (id_analisis) WHERE vigente;

CREATE INDEX ix_alcaldia_geom        ON alcaldia        USING gist (geom);
CREATE INDEX ix_colonia_geom         ON colonia         USING gist (geom);
CREATE INDEX ix_punto_geom           ON punto_delictivo USING gist (geom);
CREATE INDEX ix_hotspot_geom         ON hotspot         USING gist (geom);
CREATE INDEX ix_hotspot_geom_area    ON hotspot         USING gist (geom_area);
CREATE INDEX ix_colonia_alcaldia       ON colonia           (id_alcaldia);
CREATE INDEX ix_punto_carga            ON punto_delictivo   (id_carga);
CREATE INDEX ix_punto_delito           ON punto_delictivo   (id_delito);
CREATE INDEX ix_punto_colonia          ON punto_delictivo   (id_colonia);
CREATE INDEX ix_punto_dentro_gam       ON punto_delictivo   (id_punto) WHERE dentro_gam;
CREATE INDEX ix_analisis_carga_origen  ON analisis_hdbscan  (id_carga_origen);
CREATE INDEX ix_analisis_previo        ON analisis_hdbscan  (id_analisis_previo);
CREATE INDEX ix_analisis_carga_carga   ON analisis_carga    (id_carga);
CREATE INDEX ix_membresia_punto        ON membresia_hotspot (id_punto);
CREATE INDEX ix_membresia_hotspot      ON membresia_hotspot (id_hotspot);
CREATE INDEX ix_particion_analisis     ON particion_louvain (id_analisis);
CREATE INDEX ix_nodo_grafo_grafo       ON nodo_grafo        (id_grafo, id_particion);
CREATE INDEX ix_nodo_grafo_hotspot     ON nodo_grafo        (id_hotspot);
CREATE INDEX ix_arista_origen          ON arista            (id_origen);
CREATE INDEX ix_arista_destino         ON arista            (id_destino);
CREATE INDEX ix_ejecucion_grafo        ON ejecucion_ag      (id_grafo);
CREATE INDEX ix_individuo_padre1       ON individuo         (id_padre_1);
CREATE INDEX ix_individuo_padre2       ON individuo         (id_padre_2);
CREATE INDEX ix_simulacion_ejecucion   ON simulacion        (id_ejecucion);
CREATE FUNCTION fn_punto_ubicacion() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_geom geometry := ST_SetSRID(ST_MakePoint(NEW.longitud, NEW.latitud), 4326);
BEGIN
    NEW.dentro_gam := EXISTS (
        SELECT 1 FROM alcaldia a
        WHERE a.nombre = 'Gustavo A. Madero'
          AND ST_Intersects(a.geom, v_geom)
    );

    IF NEW.id_colonia IS NULL THEN
        SELECT c.id_colonia INTO NEW.id_colonia
        FROM colonia c
        WHERE ST_Intersects(c.geom, v_geom)
        LIMIT 1;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_punto_ubicacion
    BEFORE INSERT OR UPDATE OF latitud, longitud ON punto_delictivo
    FOR EACH ROW EXECUTE FUNCTION fn_punto_ubicacion();

COMMENT ON TABLE alcaldia          IS 'Límite territorial de GAM para el mapa y la validación espacial';
COMMENT ON TABLE colonia           IS 'Catálogo de colonias de GAM con su polígono';
COMMENT ON TABLE cat_delito        IS 'Catálogo de delitos con bien jurídico y gravedad';
COMMENT ON TABLE carga_dataset     IS 'Cada archivo xlsx subido; origen de la trazabilidad';
COMMENT ON TABLE punto_delictivo   IS 'Una víctima en GAM con coordenadas; acumula todas las cargas';
COMMENT ON TABLE analisis_hdbscan  IS 'Una ejecución de HDBSCAN; solo una vigente';
COMMENT ON TABLE analisis_carga    IS 'Cargas incluidas en cada análisis';
COMMENT ON TABLE hotspot           IS 'Hotspots etiquetados de cada análisis';
COMMENT ON TABLE membresia_hotspot IS 'Hotspot de cada punto en cada análisis; NULL = ruido';
COMMENT ON TABLE particion_louvain IS 'Ejecución de Louvain con N grafos (1 a 5)';
COMMENT ON TABLE grafo             IS 'Cada uno de los N grafos de una partición';
COMMENT ON TABLE nodo_grafo        IS 'Hotspots que forman cada grafo';
COMMENT ON TABLE arista            IS 'Distancia entre pares de hotspots; entrada de la función objetivo';
COMMENT ON TABLE ejecucion_ag      IS 'Corrida del algoritmo genético sobre un grafo (un agente)';
COMMENT ON TABLE generacion        IS 'Resumen de cada generación del algoritmo genético';
COMMENT ON TABLE individuo         IS 'Cada permutación de cada generación';
COMMENT ON TABLE simulacion        IS 'Cada simulación del recorrido de un agente';

COMMIT;

SELECT count(*) AS tablas_creadas
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
  AND table_name <> 'spatial_ref_sys';