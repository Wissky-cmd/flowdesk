#!/bin/sh
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=app_password="$APP_DB_PASSWORD" --set=ON_ERROR_STOP=1 <<'SQL'
CREATE ROLE flowdesk LOGIN PASSWORD :'app_password';
ALTER DATABASE flowdesk OWNER TO flowdesk;
ALTER SCHEMA public OWNER TO flowdesk;
SQL
