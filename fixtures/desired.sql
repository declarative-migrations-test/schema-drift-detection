CREATE SCHEMA app;

CREATE TABLE app.accounts (
    id text PRIMARY KEY,
    email text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT current_timestamp,
    CONSTRAINT accounts_status_check CHECK (status IN ('active', 'disabled'))
);

CREATE INDEX accounts_status_idx ON app.accounts (status) WHERE status = 'active';
