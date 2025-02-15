-- Enable UUID extension
CREATE OR REPLACE FUNCTION create_uuid_extension()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA public;
END;
$$;

-- Create tables function
CREATE OR REPLACE FUNCTION create_tables(
    simulations_sql text,
    call_records_sql text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    EXECUTE simulations_sql;
    EXECUTE call_records_sql;
END;
$$;

-- Function to execute SQL statements
CREATE OR REPLACE FUNCTION exec(sql text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    EXECUTE sql;
END;
$$; 