-- Initialize TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create the timeseries database (separate from main)
SELECT 'CREATE DATABASE deeptrade_timeseries'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'deeptrade_timeseries')\gexec

-- Connect to timeseries DB and enable extension there too
\c deeptrade_timeseries
CREATE EXTENSION IF NOT EXISTS timescaledb;
