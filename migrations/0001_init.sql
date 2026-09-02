-- Aislamiento multi-tenant por Row Level Security.
--
-- El filtrado NO se hace en el repositorio: se hace en el motor. Un WHERE
-- olvidado en Python no puede filtrar datos de otro tenant porque la
-- politica se aplica antes.

CREATE TABLE tenants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gateways (
    id           TEXT NOT NULL,
    tenant_id    TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    site         TEXT NOT NULL,
    cert_serial  TEXT NOT NULL,
    -- huella del certificado cliente; permite revocar sin tocar la CA
    cert_sha256  TEXT NOT NULL,
    enrolled_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at   TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE assets (
    id         UUID PRIMARY KEY,
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    parent_id  UUID REFERENCES assets(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    UNIQUE (tenant_id, parent_id, name)
);

CREATE TABLE tags (
    id            UUID PRIMARY KEY,
    tenant_id     TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    asset_id      UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    data_type     TEXT NOT NULL,
    unit          TEXT NOT NULL,
    scale_factor  DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    scale_offset  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    range_low     DOUBLE PRECISION,
    range_high    DOUBLE PRECISION,
    deadband      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    modbus_unit   SMALLINT,
    modbus_reg    INTEGER,
    opcua_node_id TEXT,
    has_history   BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (tenant_id, asset_id, name),
    CHECK (range_low IS NULL OR range_high IS NULL OR range_low < range_high),
    CHECK (scale_factor <> 0),
    CHECK ((modbus_reg IS NOT NULL) <> (opcua_node_id IS NOT NULL))
);

CREATE TABLE audit_events (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event      TEXT NOT NULL,
    detail     JSONB NOT NULL DEFAULT '{}'::jsonb,
    at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Politicas RLS ---------------------------------------------------------

ALTER TABLE gateways     ENABLE ROW LEVEL SECURITY;
ALTER TABLE assets       ENABLE ROW LEVEL SECURITY;
ALTER TABLE tags         ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

-- FORCE: la politica se aplica tambien al propietario de la tabla.
-- Sin esto, el usuario dueno del esquema salta el aislamiento y el test
-- de integracion pasa en verde mientras produccion esta abierta.
ALTER TABLE gateways     FORCE ROW LEVEL SECURITY;
ALTER TABLE assets       FORCE ROW LEVEL SECURITY;
ALTER TABLE tags         FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_gateways ON gateways
    USING (tenant_id = current_setting('ferrogate.tenant_id', TRUE))
    WITH CHECK (tenant_id = current_setting('ferrogate.tenant_id', TRUE));

CREATE POLICY tenant_isolation_assets ON assets
    USING (tenant_id = current_setting('ferrogate.tenant_id', TRUE))
    WITH CHECK (tenant_id = current_setting('ferrogate.tenant_id', TRUE));

CREATE POLICY tenant_isolation_tags ON tags
    USING (tenant_id = current_setting('ferrogate.tenant_id', TRUE))
    WITH CHECK (tenant_id = current_setting('ferrogate.tenant_id', TRUE));

CREATE POLICY tenant_isolation_audit ON audit_events
    USING (tenant_id = current_setting('ferrogate.tenant_id', TRUE))
    WITH CHECK (tenant_id = current_setting('ferrogate.tenant_id', TRUE));

CREATE INDEX ON assets (tenant_id);
CREATE INDEX ON tags (tenant_id, asset_id);
CREATE INDEX ON audit_events (tenant_id, at DESC);

-- Anadidos para la verificacion de sobres firmados.
ALTER TABLE gateways ADD COLUMN cert_pem TEXT NOT NULL DEFAULT '';
-- Contador monotono anti-reenvio. Persistido: reiniciar la ingesta no
-- debe reabrir la ventana de replay.
ALTER TABLE gateways ADD COLUMN last_sequence BIGINT;

-- Eventos de seguridad PREVIOS a la autenticacion.
--
-- No lleva clave foranea a tenants ni RLS a proposito: registra intentos
-- de gateways no enrolados, con tenants que pueden no existir. Auditar
-- esos rechazos bajo el tenant reclamado es imposible (violaria la FK) y
-- ademas seria incorrecto: la identidad todavia no esta probada.
--
-- Aqui se guarda lo RECLAMADO, no lo verificado. Es la diferencia entre
-- "este tenant hizo X" y "alguien dijo ser este tenant e intento X".
CREATE TABLE security_events (
    id              BIGSERIAL PRIMARY KEY,
    claimed_tenant  TEXT,
    claimed_gateway TEXT,
    event           TEXT NOT NULL,
    detail          JSONB NOT NULL DEFAULT '{}'::jsonb,
    at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON security_events (at DESC);
CREATE INDEX ON security_events (claimed_tenant, at DESC);
