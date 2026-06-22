CREATE TABLE IF NOT EXISTS licitaciones (
  id SERIAL PRIMARY KEY,
  numero TEXT,
  nomenclatura TEXT,
  entidad TEXT,
  fecha_publicacion TIMESTAMP,
  reiniciado_desde TEXT,
  objeto_de_contratacion TEXT,
  descripcion TEXT,
  codigo_snip TEXT,
  codigo_cui TEXT,
  monto TEXT,
  moneda TEXT,
  version_seace TEXT,
  departamento TEXT,
  scraped_at TIMESTAMP DEFAULT NOW(),
  UNIQUE (nomenclatura, entidad, fecha_publicacion)
);

CREATE TABLE IF NOT EXISTS cronograma (
  id SERIAL PRIMARY KEY,
  licitacion_id INTEGER REFERENCES licitaciones(id) ON DELETE CASCADE,
  etapa TEXT,
  lugar TEXT,
  fecha_inicio TEXT,
  fecha_fin TEXT
);

CREATE TABLE IF NOT EXISTS documentos (
  id SERIAL PRIMARY KEY,
  licitacion_id INTEGER REFERENCES licitaciones(id) ON DELETE CASCADE,
  nro TEXT,
  etapa TEXT,
  documento TEXT,
  uuid TEXT UNIQUE,
  filename TEXT,
  tamanio TEXT,
  local_path TEXT,
  page_count INTEGER,
  file_size_mb NUMERIC(10,2),
  fecha_publicacion TEXT,
  exceeds_claude_limit BOOLEAN DEFAULT NULL
);

COMMENT ON COLUMN documentos.exceeds_claude_limit IS
'True if the file exceeds 22 MB or 100 pages (safe threshold for Claude API with base64 overhead). NULL = data not available (row created before this column existed).';

CREATE TABLE IF NOT EXISTS convocatoria (
  id SERIAL PRIMARY KEY,
  licitacion_id INTEGER REFERENCES licitaciones(id) ON DELETE CASCADE,
  nomenclatura TEXT,
  n_convocatoria TEXT,
  tipo_compra TEXT,
  normativa TEXT,
  version_seace TEXT,
  entidad_convocante TEXT,
  direccion_legal TEXT,
  pagina_web TEXT,
  telefono TEXT,
  objeto_contratacion TEXT,
  descripcion_objeto TEXT,
  monto TEXT,
  fecha_publicacion TEXT
);

CREATE TABLE IF NOT EXISTS entidad_contratante (
  id SERIAL PRIMARY KEY,
  licitacion_id INTEGER REFERENCES licitaciones(id) ON DELETE CASCADE,
  ruc TEXT,
  entidad TEXT
);

CREATE TABLE IF NOT EXISTS extracciones (
  id             SERIAL PRIMARY KEY,
  licitacion_id  INTEGER REFERENCES licitaciones(id) ON DELETE CASCADE,
  nomenclatura   VARCHAR(100) NOT NULL,
  extraccion     JSONB NOT NULL,
  modelo         VARCHAR(60),
  doc_tipo       VARCHAR(20),
  estado         VARCHAR(30) NOT NULL DEFAULT 'pending',
  fecha          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  validation_issues JSONB,
  CONSTRAINT uq_extracciones_licitacion UNIQUE (licitacion_id)
);

CREATE INDEX IF NOT EXISTS idx_extracciones_nomenclatura ON extracciones(nomenclatura);
CREATE INDEX IF NOT EXISTS idx_extracciones_estado ON extracciones(estado);

