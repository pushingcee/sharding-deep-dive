-- Initialize pg_stat_statements extension for monitoring
-- This script runs automatically when the container starts

-- Create the extension
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Verify the extension is loaded
SELECT * FROM pg_available_extensions WHERE name = 'pg_stat_statements';