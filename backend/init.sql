-- init.sql
-- Initialization script for PostgreSQL

-- Create a dedicated schema for the trading system
CREATE SCHEMA IF NOT EXISTS trading_schema;

-- Ensure timezone is set to UTC database-wide
ALTER DATABASE trading_db SET timezone TO 'UTC';
