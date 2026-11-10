-- Runs once on an empty, EazyShop-only volume. Never run against another cluster.
\getenv dev_password EAZYSHOP_DEV_PASSWORD
\getenv test_password EAZYSHOP_TEST_PASSWORD
CREATE ROLE eazyshop_dev LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'dev_password';
CREATE ROLE eazyshop_test LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'test_password';
CREATE DATABASE eazyshop_dev OWNER eazyshop_dev;
CREATE DATABASE eazyshop_test OWNER eazyshop_test;
REVOKE ALL ON DATABASE eazyshop_dev, eazyshop_test, postgres FROM PUBLIC;
-- Django's keepdb runner reads database-existence metadata via the maintenance DB.
GRANT CONNECT ON DATABASE postgres TO eazyshop_test;
\connect eazyshop_dev
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO eazyshop_dev;
\connect eazyshop_test
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO eazyshop_test;
ALTER ROLE eazyshop_test SET lock_timeout = '10s';
ALTER ROLE eazyshop_test SET statement_timeout = '60s';
