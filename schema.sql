CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    plan TEXT NOT NULL,
    object_limit INTEGER NOT NULL CHECK (object_limit > 0),
    api_token TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS objects (
    id INTEGER PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS seals (
    id INTEGER PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    object_id INTEGER NOT NULL,
    number TEXT NOT NULL,
    installed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    removed_at TEXT,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, object_id) REFERENCES objects(tenant_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_current_seal
ON seals(tenant_id, object_id) WHERE removed_at IS NULL;

CREATE TABLE IF NOT EXISTS inspections (
    id INTEGER PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    seal_id INTEGER NOT NULL,
    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    result TEXT NOT NULL CHECK (result IN ('intact', 'broken', 'missing')),
    note TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (tenant_id, seal_id) REFERENCES seals(tenant_id, id)
);
