#!/usr/bin/env bash
# Runs once, on first start of an empty data volume. `make roles` re-applies the same SQL.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /ursache/roles.sql

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_pw="$URSACHE_APP_PASSWORD" \
  -v agent_pw="$URSACHE_AGENT_PASSWORD" \
  -v eval_pw="$URSACHE_EVAL_PASSWORD" <<'SQL'
ALTER ROLE ursache_app PASSWORD :'app_pw';
ALTER ROLE ursache_agent PASSWORD :'agent_pw';
ALTER ROLE ursache_eval PASSWORD :'eval_pw';
SQL
