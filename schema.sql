-- Corporate Asset Management System
-- SQLite schema
-- Tables: employees, assets, assignments, returns, maintenance, audit_log

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS employees (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    department   TEXT NOT NULL,
    role         TEXT,
    phone        TEXT,
    joined_date  TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_tag     TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL CHECK (category IN ('laptop', 'phone', 'vehicle', 'equipment')),
    brand         TEXT,
    model         TEXT,
    serial_no     TEXT UNIQUE,
    purchase_date TEXT NOT NULL,
    purchase_cost REAL NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'available'
                  CHECK (status IN ('available', 'assigned', 'in_maintenance', 'retired')),
    location      TEXT,
    usage_hours   REAL NOT NULL DEFAULT 0,
    condition     TEXT NOT NULL DEFAULT 'good'
                  CHECK (condition IN ('excellent', 'good', 'fair', 'poor')),
    notes         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS assignments (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id             INTEGER NOT NULL REFERENCES assets(id),
    employee_id          INTEGER NOT NULL REFERENCES employees(id),
    assigned_date        TEXT NOT NULL,
    expected_return_date TEXT,
    returned_date        TEXT,
    status               TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'returned')),
    notes                TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS returns (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id       INTEGER NOT NULL REFERENCES assignments(id),
    asset_id            INTEGER NOT NULL REFERENCES assets(id),
    employee_id         INTEGER NOT NULL REFERENCES employees(id),
    return_date         TEXT NOT NULL,
    condition_on_return TEXT NOT NULL
                        CHECK (condition_on_return IN ('excellent', 'good', 'fair', 'poor', 'damaged')),
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS maintenance (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id         INTEGER NOT NULL REFERENCES assets(id),
    maintenance_date TEXT NOT NULL,
    maintenance_type TEXT NOT NULL
                     CHECK (maintenance_type IN ('preventive', 'corrective')),
    description      TEXT NOT NULL,
    cost             REAL NOT NULL DEFAULT 0,
    performed_by     TEXT,
    next_due_date    TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id   INTEGER,
    action      TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'admin',
    details     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);
CREATE INDEX IF NOT EXISTS idx_assignments_asset ON assignments(asset_id);
CREATE INDEX IF NOT EXISTS idx_assignments_employee ON assignments(employee_id);
CREATE INDEX IF NOT EXISTS idx_assignments_status ON assignments(status);
CREATE INDEX IF NOT EXISTS idx_maintenance_asset ON maintenance(asset_id);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
