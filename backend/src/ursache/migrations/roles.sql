-- Idempotent schemas, roles and grants. Run as the migration (owner) role, which must be the
-- same role that runs Alembic: ALTER DEFAULT PRIVILEGES applies to objects it creates later.
-- Passwords are not set here; `ursache db-roles` sets them from the *_DATABASE_URL settings.

CREATE SCHEMA IF NOT EXISTS plant;
CREATE SCHEMA IF NOT EXISTS kb;
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS eval;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ursache_app') THEN
        CREATE ROLE ursache_app LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ursache_agent') THEN
        CREATE ROLE ursache_agent LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ursache_eval') THEN
        CREATE ROLE ursache_eval LOGIN;
    END IF;
END
$$;

ALTER ROLE ursache_agent SET statement_timeout = '5s';
ALTER ROLE ursache_agent SET default_transaction_read_only = on;

REVOKE ALL ON SCHEMA plant, kb, app, eval FROM PUBLIC;

-- ursache_app: read/write plant, kb, app; nothing in eval
GRANT USAGE ON SCHEMA plant, kb, app TO ursache_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA plant, kb, app TO ursache_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA plant, kb, app TO ursache_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA plant, kb, app
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ursache_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA plant, kb, app
    GRANT USAGE, SELECT ON SEQUENCES TO ursache_app;
REVOKE ALL ON SCHEMA eval FROM ursache_app;
REVOKE ALL ON ALL TABLES IN SCHEMA eval FROM ursache_app;

-- ursache_agent: SELECT on plant and kb only
GRANT USAGE ON SCHEMA plant, kb TO ursache_agent;
GRANT SELECT ON ALL TABLES IN SCHEMA plant, kb TO ursache_agent;
ALTER DEFAULT PRIVILEGES IN SCHEMA plant, kb GRANT SELECT ON TABLES TO ursache_agent;
REVOKE ALL ON SCHEMA app, eval FROM ursache_agent;
REVOKE ALL ON ALL TABLES IN SCHEMA app, eval FROM ursache_agent;

-- ursache_eval: read everything
GRANT USAGE ON SCHEMA plant, kb, app, eval TO ursache_eval;
GRANT SELECT ON ALL TABLES IN SCHEMA plant, kb, app, eval TO ursache_eval;
ALTER DEFAULT PRIVILEGES IN SCHEMA plant, kb, app, eval GRANT SELECT ON TABLES TO ursache_eval;
